"""无状态摘要与语义 diff 辅助模块（v0.3.2 Task 0 自 service.py 拆分）。

本模块只承载纯函数：不依赖 `DstManagerService` 实例状态（不触碰 database、
settings、publisher 等），输入即输出。摘要（`summarize_*`）、语义 diff
（`build_semantic_diff`）、操作摘要（`operation_digest`）与并行估算辅助
（`parallel_makespan`）在此独立成模块，供各功能域模块与编排入口引用。
"""

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dst_manager.domain.editing import property_definitions_from_document
from dst_manager.domain.models import Workspace
from dst_manager.infrastructure.acsm_xml import AcsmValidationError
from dst_manager.infrastructure.filesystem.publisher import file_sha256


def build_semantic_diff(
    workspace: Workspace,
    commands: list[dict[str, Any]],
    execution_intent: dict[str, Any] | None,
) -> dict[str, Any]:
    before = summarize_current_structure(workspace)
    after = (
        summarize_derived_structure(execution_intent["derived_document"])
        if execution_intent is not None
        else before
    )
    return {
        "sheet_set": summarize_sheet_set_changes(workspace, commands),
        "structure": {"before": before, "after": after},
        "properties": summarize_property_changes(workspace, commands),
        "dwgs": summarize_dwg_changes(workspace, execution_intent),
    }


def summarize_sheet_set_changes(
    workspace: Workspace,
    commands: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result = []
    for command in commands:
        if command["type"] != "update_sheet_set" or "name" not in command:
            continue
        after = command["name"]
        if after != workspace.document.name:
            result.append(
                {
                    "field": "name",
                    "before": workspace.document.name,
                    "after": after,
                },
            )
    return result


def summarize_current_structure(workspace: Workspace) -> list[dict[str, Any]]:
    result = []
    for subset_position, subset in enumerate(sorted(workspace.document.subsets, key=lambda item: item.order), 1):
        sheets = []
        for sheet_position, sheet in enumerate(subset.sheets, 1):
            drawing = sheet.layout.resolved_path or sheet.layout.file_name
            sheets.append(sheet_summary(sheet_position, sheet.acsm_id, sheet.number, sheet.title, str(drawing or ""), sheet.layout.layout_name))
        number_range = ""
        if sheets:
            number_range = sheets[0]["number"] if len(sheets) == 1 else f"{sheets[0]['number']}-{sheets[-1]['number']}"
        title = subset.name
        if number_range and subset.name.startswith(f"{number_range} "):
            title = subset.name[len(number_range) + 1:]
        result.append(
            {
                "position": subset_position,
                "id": subset.acsm_id,
                "title": title,
                "number_range": number_range,
                "display_name": subset.name,
                "dwg_file": sheets[0]["dwg_file"] if sheets else "",
                "sheets": sheets,
            },
        )
    return result


def summarize_derived_structure(document: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for subset_position, subset in enumerate(document.get("subsets", []), 1):
        drawing = str(subset.get("target_file", ""))
        sheets = [
            sheet_summary(
                sheet_position,
                sheet["acsm_id"],
                sheet["number"],
                sheet["title"],
                drawing,
                sheet["layout"]["layout_name"],
            )
            for sheet_position, sheet in enumerate(subset.get("sheets", []), 1)
        ]
        result.append(
            {
                "position": subset_position,
                "id": subset["acsm_id"],
                "title": subset["title"],
                "number_range": subset["number_range"],
                "display_name": subset["display_name"],
                "dwg_file": drawing,
                "sheets": sheets,
            },
        )
    return result


def sheet_summary(position: int, sheet_id: str, number: str, title: str, drawing: str, layout: str) -> dict[str, Any]:
    suffix_match = re.search(r"\s+\(([^()]*)\)$", title)
    return {
        "position": position,
        "id": sheet_id,
        "number": number,
        "title": title,
        "suffix": suffix_match.group(1) if suffix_match else "",
        "dwg_file": drawing,
        "layout_name": layout,
    }


def summarize_property_changes(workspace: Workspace, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        definitions = {
            (definition.type, definition.name.casefold()): definition
            for definition in property_definitions_from_document(workspace.document)
        }
    except AcsmValidationError:
        definitions = {}
    sheet_by_id = {sheet.acsm_id: sheet for sheet in workspace.document.sheets}
    result = []
    for command in commands:
        command_type = command["type"]
        if command_type in {"add_custom_property", "delete_custom_property"}:
            property_type = command["property_type"]
            name = command["name"]
            previous = definitions.get((property_type, name.casefold()))
            after = None
            if command_type == "add_custom_property":
                after = {
                    "type": property_type,
                    "name": name,
                    "default_value": command.get("default_value", ""),
                }
            result.append(
                {
                    "action": "add" if command_type == "add_custom_property" else "delete",
                    "type": property_type,
                    "name": name,
                    "before": asdict(previous) if previous is not None else None,
                    "after": after,
                    "affected_sheet_count": len(workspace.document.sheets) if property_type == "sheet" else 0,
                },
            )
        elif command_type == "update_sheet":
            sheet = sheet_by_id.get(command.get("sheet_id"))
            for name, value in command.get("custom_properties", {}).items():
                result.append(
                    {
                        "action": "update",
                        "type": "sheet",
                        "name": name,
                        "before": sheet.custom_properties.get(name) if sheet else None,
                        "after": value,
                        "affected_sheet_count": 1 if sheet else 0,
                    },
                )
        elif command_type == "update_sheet_set":
            for name, value in command.get("custom_properties", {}).items():
                result.append(
                    {
                        "action": "update",
                        "type": "sheetset",
                        "name": name,
                        "before": workspace.document.custom_properties.get(name),
                        "after": value,
                        "affected_sheet_count": 0,
                    },
                )
    return result


def summarize_dwg_changes(workspace: Workspace, execution_intent: dict[str, Any] | None) -> list[dict[str, Any]]:
    if execution_intent is None:
        return []
    before_by_id = {item["id"]: item for item in summarize_current_structure(workspace)}
    after_by_id = {item["id"]: item for item in summarize_derived_structure(execution_intent["derived_document"])}
    result = []
    for group in execution_intent.get("groups", []):
        subset_id = group["subset_id"]
        before = before_by_id.get(subset_id)
        after = after_by_id.get(subset_id)
        result.append(
            {
                "action": group["operation"],
                "subset_id": subset_id,
                "before": None if before is None else {"file": before["dwg_file"], "layouts": [sheet["layout_name"] for sheet in before["sheets"]]},
                "after": None if after is None else {"file": after["dwg_file"], "layouts": [sheet["layout_name"] for sheet in after["sheets"]]},
            },
        )
    for deleted in execution_intent.get("deleted_subsets", []):
        subset_id = deleted["subset_id"]
        before = before_by_id.get(subset_id)
        result.append(
            {
                "action": "delete",
                "subset_id": subset_id,
                "before": {"file": deleted["target_file"], "layouts": [sheet["layout_name"] for sheet in before["sheets"]]} if before else {"file": deleted["target_file"], "layouts": []},
                "after": None,
            },
        )
    return result


def operation_digest(
    *,
    operation_type: str,
    workspace_id: str,
    base_revision_id: str,
    normalized_input: dict[str, Any],
    semantic_diff: dict[str, Any],
    target_baselines: dict[str, Any],
    cad_version: str | None = None,
    source_baselines: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "schema_version": 1,
        "operation_type": operation_type,
        "workspace_id": workspace_id,
        "base_revision_id": base_revision_id,
        "normalized_input": normalized_input,
        "semantic_diff": semantic_diff,
        "target_baselines": target_baselines,
        "cad_version": cad_version,
        "source_baselines": source_baselines or [],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parallel_makespan(durations: list[int], concurrency: int) -> int:
    if not durations or concurrency <= 0:
        return 0
    slots = [0] * concurrency
    for duration in durations:
        slot = min(range(concurrency), key=slots.__getitem__)
        slots[slot] += duration
    return max(slots)


def attach_expected_file_hashes(workspace: Workspace, execution_intent: dict[str, Any]) -> None:
    paths = {
        workspace.dst_path.resolve(),
        *(Path(path).resolve() for path in execution_intent.get("path_graph", {}).get("old_sources", [])),
        *(Path(path).resolve() for path in execution_intent.get("path_graph", {}).get("final_targets", [])),
    }
    for group in execution_intent.get("groups", []):
        paths.add(Path(group["source_snapshot"]).resolve())
        paths.update(Path(layout["source_file"]).resolve() for layout in group.get("layouts", []))
    source_baselines = {
        Path(baseline["path"]).resolve(): baseline
        for baseline in execution_intent.get("source_baselines", [])
    }
    expected = {
        str(path): (
            source_baselines[path]["sha256"]
            if path in source_baselines
            else file_sha256(path) if path.is_file() else None
        )
        for path in sorted(paths, key=lambda item: str(item).casefold())
    }
    execution_intent["expected_file_hashes"] = expected
    execution_intent["expected_file_identities"] = {
        str(path): source_baselines[path]["identity"]
        for path in sorted(source_baselines, key=lambda item: str(item).casefold())
    }
