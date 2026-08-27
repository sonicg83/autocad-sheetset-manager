import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from dst_manager.domain.editing import (
    EditingError,
    SuffixOptions,
    derive_document_structure,
)
from dst_manager.domain.models import (
    CustomPropertyDefinition,
    DerivedDocument,
    DerivedSubset,
    LayoutReference,
    PropertyDefinitionDiff,
    Sheet,
    Subset,
    Workspace,
)


class PlanningError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_UNSAFE_NAME = re.compile(r"[<>/\\\":;?*|=\r\n\x00-\x1f]")
_ORDINAL = re.compile(r"^(.*?)[(（]([一二三四五六七八九十百]+)[)）]$")
_DERIVED_RANGE_PREFIX = re.compile(r"^(?P<prefix>.*?)(?P<range>\d+(?:-\d+)?)\s+")
_HEX_HANDLE = re.compile(r"^[0-9A-Fa-f]+$")

CadOperation = Literal["none", "rename_only", "rebuild"]

def derive_layout_name(number: str, title: str) -> str:
    name = f"{number.strip()} {title.strip()}".strip()
    if not name or len(name) > 255 or _UNSAFE_NAME.search(name):
        raise PlanningError("LAYOUT_NAME_INVALID", f"布局名无效：{name!r}")
    return name


def _display_number(number: str) -> str:
    return str(int(number)) if number.isdigit() else number


def _title_group(titles: list[str]) -> tuple[str, str]:
    matches = [_ORDINAL.fullmatch(title.strip()) for title in titles]
    if all(matches) and len({match.group(1) for match in matches if match}) == 1:
        base = matches[0].group(1)
        return base, f"{base}({matches[0].group(2)})-({matches[-1].group(2)})" if len(matches) > 1 else titles[0]
    if len(set(titles)) == 1:
        return titles[0], titles[0]
    return f"{titles[0]}-{titles[-1]}", f"{titles[0]}-{titles[-1]}"


def derive_subset_and_dwg_name(existing: Path, sheets: list[Sheet]) -> tuple[str, Path]:
    if not sheets:
        raise PlanningError("EMPTY_SUBSET", "空子集不能派生命名")
    base_title, file_title = _title_group([sheet.title for sheet in sheets])
    first, last = sheets[0].number, sheets[-1].number
    number_range = first if len(sheets) == 1 else f"{first}-{last}"
    display_range = _display_number(first) if len(sheets) == 1 else f"{_display_number(first)}-{_display_number(last)}"
    prefix_match = _DERIVED_RANGE_PREFIX.match(existing.stem)
    prefix = prefix_match.group("prefix") if prefix_match else ""
    subset_name = f"{display_range} {base_title}"
    file_name = f"{prefix}{number_range} {file_title}.dwg"
    if _UNSAFE_NAME.search(file_name) or len(file_name) > 240:
        raise PlanningError("DWG_FILE_NAME_INVALID", f"派生DWG文件名无效：{file_name}")
    return subset_name, existing.with_name(file_name)


def new_acsm_id(base_revision: str, command_index: int, suffix: str = "sheet") -> str:
    value = uuid.uuid5(uuid.NAMESPACE_URL, f"dst-manager:{base_revision}:{command_index}:{suffix}")
    return "g" + str(value).upper()


def build_structural_plan(
    workspace: Workspace,
    commands: list[dict[str, Any]],
    suffix_options: SuffixOptions | None = None,
) -> dict[str, Any]:
    try:
        derived = derive_document_structure(
            workspace.document,
            commands,
            suffix_options or SuffixOptions(True, 1),
        )
    except EditingError as exc:
        raise PlanningError(exc.code, str(exc)) from exc

    _validate_derived_object_ids(derived)

    original_subsets = {subset.acsm_id: subset for subset in workspace.document.subsets}
    cardinality_frontier_index = _cardinality_frontier(workspace.document.subsets, derived.subsets)
    groups = []
    subset_operations = []
    final_targets: list[str] = []
    transitions: list[dict[str, str | None]] = []
    planned_subset_ids: list[str] = []
    for index, subset in enumerate(derived.subsets):
        original = original_subsets.get(subset.acsm_id)
        original_layouts = {
            sheet.acsm_id: sheet.layout.layout_name
            for sheet in original.sheets
        } if original is not None else {}
        layouts = []
        names: set[str] = set()
        for sheet in subset.sheets:
            name = sheet.layout.layout_name
            if name.casefold() in names:
                raise PlanningError("DUPLICATE_LAYOUT_NAME", f"目标DWG内布局名重复：{name}")
            names.add(name.casefold())
            source = derived.layout_sources[sheet.acsm_id]
            layouts.append(
                {
                    "sheet_id": sheet.acsm_id,
                    "number": sheet.number,
                    "title": sheet.title,
                    "custom_properties": sheet.custom_properties,
                    "source_type": source["type"],
                    "source_file": source["file"],
                    "source_layout": source["layout"],
                    "target_layout": name,
                    "original_layout": original_layouts.get(sheet.acsm_id),
                },
            )
        operation = "rebuild" if original is not None else "create"
        source_target = _subset_target_file(original) if original is not None else None
        if operation == "rebuild" and not source_target:
            raise PlanningError("SOURCE_TARGET_MISSING", f"子集缺少现有目标DWG：{subset.acsm_id}")
        target = _final_target_path(workspace, subset, operation)
        subset.target_file = str(target)
        subset.source_target_file = source_target or ""
        final_targets.append(str(target))
        in_cardinality_scope = cardinality_frontier_index is not None and index >= cardinality_frontier_index
        cad_operation = _cad_operation(
            original,
            subset,
            derived.layout_sources,
            in_frontier_scope=in_cardinality_scope,
            source_target=source_target,
            target=target,
        )
        subset_operations.append(
            {
                "subset_id": subset.acsm_id,
                "cad_operation": cad_operation,
                "target_file": str(target),
                "in_cardinality_scope": in_cardinality_scope,
            },
        )
        transitions.append(
            {
                "subset_id": subset.acsm_id,
                "operation": operation,
                "source": source_target,
                "target": str(target),
            },
        )
        if cad_operation == "none":
            continue
        source_snapshot = source_target or (layouts[0]["source_file"] if layouts else "")
        if not source_snapshot:
            raise PlanningError("LAYOUT_SOURCE_INVALID", f"子集缺少重建基础文件：{subset.acsm_id}")
        planned_subset_ids.append(subset.acsm_id)
        group = {
            "subset_id": subset.acsm_id,
            "subset_name": subset.display_name,
            "operation": operation,
            "cad_operation": cad_operation,
            "source_target_file": source_target,
            "source_snapshot": str(Path(source_snapshot).expanduser().resolve()),
            "target_file": str(target),
            "layouts": layouts,
        }
        if operation == "create":
            group["expected_baseline"] = None
        groups.append(group)
    if len(final_targets) != len({target.casefold() for target in final_targets}):
        raise PlanningError("DWG_TARGET_COLLISION", "多个子集派生出相同的目标DWG文件名")
    final_subset_ids = {subset.acsm_id for subset in derived.subsets}
    deleted_subsets = [
        {"subset_id": subset.acsm_id, "target_file": target}
        for subset in workspace.document.subsets
        if subset.acsm_id not in final_subset_ids and (target := _subset_target_file(subset))
    ]
    old_sources_by_key: dict[str, str] = {}
    for subset in workspace.document.subsets:
        if source := _subset_target_file(subset):
            resolved = str(Path(source).expanduser().resolve())
            old_sources_by_key.setdefault(resolved.casefold(), resolved)
    final_targets_by_key = {target.casefold(): target for target in final_targets}
    reused_keys = old_sources_by_key.keys() & final_targets_by_key.keys()
    delete_keys = old_sources_by_key.keys() - final_targets_by_key.keys()
    for group in groups:
        group["target_reuses_source"] = group["operation"] == "create" and group["target_file"].casefold() in reused_keys
    return {
        "groups": groups,
        "cardinality_frontier": (
            {
                "index": cardinality_frontier_index,
                "subset_id": (
                    derived.subsets[cardinality_frontier_index].acsm_id
                    if cardinality_frontier_index < len(derived.subsets)
                    else None
                ),
            }
            if cardinality_frontier_index is not None
            else None
        ),
        "subset_operations": subset_operations,
        "deleted_subsets": deleted_subsets,
        "path_graph": {
            "old_sources": list(old_sources_by_key.values()),
            "final_targets": final_targets,
            "reused_targets": [final_targets_by_key[key] for key in sorted(reused_keys)],
            "delete_targets": [old_sources_by_key[key] for key in sorted(delete_keys)],
            "transitions": transitions,
        },
        "affected_subset_ids": planned_subset_ids,
        "derived_document": _serialize_derived_document(derived),
    }


def _cardinality_frontier(original: list[Subset], derived: list[DerivedSubset]) -> int | None:
    final_index = {subset.acsm_id: index for index, subset in enumerate(derived)}
    candidates: list[int] = []
    for index, subset in enumerate(derived):
        before = next((item for item in original if item.acsm_id == subset.acsm_id), None)
        if before is None or len(before.sheets) != len(subset.sheets):
            candidates.append(index)
    for original_index, subset in enumerate(original):
        if subset.acsm_id in final_index:
            continue
        following = next(
            (final_index[item.acsm_id] for item in original[original_index + 1 :] if item.acsm_id in final_index),
            len(derived),
        )
        candidates.append(following)
    return min(candidates) if candidates else None


def _cad_operation(
    original: Subset | None,
    derived: DerivedSubset,
    layout_sources: Mapping[str, dict[str, str]],
    *,
    in_frontier_scope: bool,
    source_target: str | None,
    target: Path,
) -> CadOperation:
    if original is None:
        return "rebuild"
    same_ids = [sheet.acsm_id for sheet in original.sheets] == [sheet.acsm_id for sheet in derived.sheets]
    try:
        handle_values = [
            int(sheet.layout.handle, 16)
            for sheet in original.sheets
            if _HEX_HANDLE.fullmatch(sheet.layout.handle) is not None
        ]
        stable_handles = (
            len(handle_values) == len(original.sheets)
            and all(value != 0 for value in handle_values)
            and len(set(handle_values)) == len(handle_values)
        )
    except (TypeError, ValueError):
        stable_handles = False
    same_sources = False
    if same_ids:
        same_sources = True
        for before, after in zip(original.sheets, derived.sheets, strict=True):
            source = layout_sources.get(after.acsm_id)
            if (
                source is None
                or source.get("type") != "existing_snapshot"
                or Path(str(source.get("file", ""))).resolve()
                != Path(before.layout.resolved_path or before.layout.file_name).resolve()
                or source.get("layout") != before.layout.layout_name
            ):
                same_sources = False
                break
    if not same_ids or not stable_handles or not same_sources:
        return "rebuild"
    changed = _subset_changed(original, derived, source_target or "", target)
    return "rename_only" if changed or in_frontier_scope else "none"


def _validate_derived_object_ids(derived: DerivedDocument) -> None:
    seen: set[str] = set()
    for subset in derived.subsets:
        for object_id in [subset.acsm_id, *(sheet.acsm_id for sheet in subset.sheets)]:
            key = object_id.casefold()
            if key in seen:
                raise PlanningError("DUPLICATE_ACSM_ID", f"派生结构包含重复 AcSm ID：{object_id}")
            seen.add(key)


def derived_document_from_plan(plan: dict[str, Any]) -> DerivedDocument:
    """从已确认的可序列化计划恢复最终结构，不重新执行业务派生。"""
    try:
        raw = plan["derived_document"]
        subsets = []
        for subset in raw["subsets"]:
            sheets = []
            for sheet in subset["sheets"]:
                layout = sheet["layout"]
                resolved_path = layout.get("resolved_path")
                sheets.append(
                    Sheet(
                        sheet["acsm_id"],
                        sheet["number"],
                        sheet["title"],
                        LayoutReference(
                            layout["file_name"],
                            layout["relative_file_name"],
                            layout["layout_name"],
                            layout["handle"],
                            Path(resolved_path) if resolved_path else None,
                            layout.get("resolution_source"),
                        ),
                        dict(sheet["custom_properties"]),
                    ),
                )
            subsets.append(
                DerivedSubset(
                    subset["acsm_id"],
                    subset["title"],
                    subset["number_range"],
                    subset["display_name"],
                    sheets,
                    subset["source_target_file"],
                    subset["target_file"],
                ),
            )
        property_diff = PropertyDefinitionDiff(
            [_property_definition_from_dict(item) for item in raw["property_diff"]["added"]],
            [_property_definition_from_dict(item) for item in raw["property_diff"]["skipped"]],
        )
        return DerivedDocument(
            subsets,
            list(raw["affected_subset_ids"]),
            property_diff,
            {sheet_id: dict(source) for sheet_id, source in raw["layout_sources"].items()},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanningError("DERIVED_DOCUMENT_INVALID", "执行计划缺少有效的最终派生结构") from exc


def metadata_commands_for_derived_document(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """提取不参与结构派生、但必须与结构结果同批写入的元数据更新。"""
    result: list[dict[str, Any]] = []
    for command in commands:
        if command.get("type") == "update_sheet" and ({"number", "title"} & command.keys()):
            raise PlanningError("COMMAND_UNSUPPORTED", "不支持直接更新图号或图纸标题")
        if command.get("type") == "update_sheet_set":
            result.append(command)
        elif command.get("type") == "update_sheet" and "custom_properties" in command:
            result.append(
                {
                    "type": "update_sheet",
                    "sheet_id": command.get("sheet_id"),
                    "custom_properties": command["custom_properties"],
                },
            )
    return result


def _property_definition_from_dict(item: dict[str, str]) -> CustomPropertyDefinition:
    return CustomPropertyDefinition(item["type"], item["name"], item["default_value"])


def _serialize_derived_document(derived: DerivedDocument) -> dict[str, Any]:
    return {
        "subsets": [
            {
                "acsm_id": subset.acsm_id,
                "title": subset.title,
                "number_range": subset.number_range,
                "display_name": subset.display_name,
                "source_target_file": subset.source_target_file,
                "target_file": subset.target_file,
                "sheets": [
                    {
                        "acsm_id": sheet.acsm_id,
                        "number": sheet.number,
                        "title": sheet.title,
                        "custom_properties": dict(sheet.custom_properties),
                        "layout": {
                            "file_name": sheet.layout.file_name,
                            "relative_file_name": sheet.layout.relative_file_name,
                            "layout_name": sheet.layout.layout_name,
                            "handle": sheet.layout.handle,
                            "resolved_path": str(sheet.layout.resolved_path) if sheet.layout.resolved_path else None,
                            "resolution_source": sheet.layout.resolution_source,
                        },
                    }
                    for sheet in subset.sheets
                ],
            }
            for subset in derived.subsets
        ],
        "affected_subset_ids": list(derived.affected_subset_ids),
        "property_diff": {
            "added": [
                {"type": item.type, "name": item.name, "default_value": item.default_value}
                for item in derived.property_diff.added
            ],
            "skipped": [
                {"type": item.type, "name": item.name, "default_value": item.default_value}
                for item in derived.property_diff.skipped
            ],
        },
        "layout_sources": {sheet_id: dict(source) for sheet_id, source in derived.layout_sources.items()},
    }


def _subset_target_file(subset: Subset | None) -> str | None:
    if subset is None:
        return None
    for sheet in subset.sheets:
        target = sheet.layout.resolved_path or sheet.layout.file_name
        if target:
            return str(Path(target).expanduser().resolve())
    return None


def _final_target_path(workspace: Workspace, subset: DerivedSubset, operation: str) -> Path:
    if operation == "create":
        target = workspace.root / Path(subset.target_file).name
    else:
        target = Path(subset.target_file)
    target = target.expanduser().resolve()
    root = workspace.root.resolve()
    if root not in target.parents:
        raise PlanningError("DWG_TARGET_OUTSIDE_WORKSPACE", f"目标DWG越出工作区：{target}")
    return target


def _subset_changed(
    original: Subset,
    derived: DerivedSubset,
    source_target: str,
    target: Path,
) -> bool:
    if Path(source_target).resolve() != target.resolve() or original.name != derived.display_name:
        return True
    if len(original.sheets) != len(derived.sheets):
        return True
    for before, after in zip(original.sheets, derived.sheets, strict=True):
        if (
            before.acsm_id,
            before.number,
            before.title,
            before.layout.layout_name,
            before.custom_properties,
        ) != (
            after.acsm_id,
            after.number,
            after.title,
            after.layout.layout_name,
            after.custom_properties,
        ):
            return True
    return False
