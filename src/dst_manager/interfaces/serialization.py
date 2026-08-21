import re
from dataclasses import asdict
from typing import Any

_NUMBER_RANGE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s+(.+?)\s*$")


def workspace_json(workspace) -> dict[str, Any]:
    property_definitions = [
        {"type": "sheetset", "name": name, "default_value": value}
        for name, value in workspace.document.custom_properties.items()
    ]
    sheet_property_names: set[str] = set()
    for sheet in workspace.document.sheets:
        for name, value in sheet.custom_properties.items():
            key = name.casefold()
            if key in sheet_property_names:
                continue
            sheet_property_names.add(key)
            property_definitions.append(
                {"type": "sheet", "name": name, "default_value": value},
            )
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
        "unreferenced_dwgs": [str(path) for path in workspace.unreferenced_dwgs],
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
