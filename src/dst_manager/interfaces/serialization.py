import re
from dataclasses import asdict
from typing import Any

from dst_manager.domain.editing import property_definitions_from_document

_NUMBER_RANGE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s+(.+?)\s*$")


def workspace_json(workspace) -> dict[str, Any]:
    property_definitions = [
        asdict(definition)
        for definition in property_definitions_from_document(workspace.document)
    ]
    return {
        "id": workspace.id,
        "root": str(workspace.root),
        "dst_path": str(workspace.dst_path),
        "revision_id": workspace.revision_id,
        "sheet_set": {
            "database_id": workspace.document.database_id,
            "name": workspace.document.name,
            "custom_properties": workspace.document.custom_properties,
            "property_definitions": property_definitions,
            "sheet_count": len(workspace.document.sheets),
            "subset_count": len(workspace.document.subsets),
            "subsets": [
                {
                    "id": subset.acsm_id,
                    "name": subset.name,
                    "title": _subset_title(subset.name),
                    "number_range": _number_range(subset.sheets),
                    "display_name": _display_name(subset.name, subset.sheets),
                    "order": subset.order,
                    "sheets": [
                        {
                            "id": sheet.acsm_id,
                            "number": sheet.number,
                            "title": sheet.title,
                            "custom_properties": sheet.custom_properties,
                            "layout": {
                                **asdict(sheet.layout),
                                "resolved_path": str(sheet.layout.resolved_path) if sheet.layout.resolved_path else None,
                            },
                        }
                        for sheet in subset.sheets
                    ],
                }
                for subset in workspace.document.subsets
            ],
        },
        "diagnostics": [asdict(issue) for issue in workspace.document.diagnostics],
        "dst_validation": _repair_report_dict(workspace.document.repair_report),
        "unreferenced_dwgs": [str(path) for path in workspace.unreferenced_dwgs],
    }


def _repair_report_dict(report) -> dict[str, Any]:
    """修复报告序列化为稳定字段；无报告视为 VALID（向后兼容）。"""
    if report is None:
        return {"status": "VALID", "actions": [], "blocking_issues": []}
    return {
        "status": report.status,
        "actions": [asdict(action) for action in report.actions],
        "blocking_issues": [asdict(issue) for issue in report.blocking_issues],
    }


def _subset_title(name: str) -> str:
    match = _NUMBER_RANGE.fullmatch(name.strip())
    return match.group(3).strip() if match else name.strip()


def _number_range(sheets) -> str:
    if not sheets:
        return ""
    return sheets[0].number if len(sheets) == 1 else f"{sheets[0].number}-{sheets[-1].number}"


def _display_name(name: str, sheets) -> str:
    return f"{_number_range(sheets)} {_subset_title(name)}".strip()
