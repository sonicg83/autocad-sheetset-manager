import re
import uuid
from pathlib import Path
from typing import Any

from dst_manager.domain.editing import (
    EditingError,
    SuffixOptions,
    derive_document_structure,
)
from dst_manager.domain.models import Sheet, Workspace


class PlanningError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_UNSAFE_NAME = re.compile(r"[<>/\\\":;?*|=\r\n\x00-\x1f]")
_ORDINAL = re.compile(r"^(.*?)[(（]([一二三四五六七八九十百]+)[)）]$")


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
    prefix_match = re.match(r"^(.*?-)(?=\d)", existing.stem)
    prefix = prefix_match.group(1) if prefix_match else ""
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

    groups = []
    for subset in derived.subsets:
        if subset.acsm_id not in derived.affected_subset_ids:
            continue
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
                },
            )
        groups.append(
            {
                "subset_id": subset.acsm_id,
                "subset_name": subset.display_name,
                "source_target_file": subset.source_target_file,
                "target_file": subset.target_file,
                "layouts": layouts,
            },
        )
    final_targets = [group["target_file"].casefold() for group in groups]
    if len(final_targets) != len(set(final_targets)):
        raise PlanningError("DWG_TARGET_COLLISION", "多个子集派生出相同的目标DWG文件名")
    return {"groups": groups, "deleted_subsets": [], "affected_subset_ids": derived.affected_subset_ids}
