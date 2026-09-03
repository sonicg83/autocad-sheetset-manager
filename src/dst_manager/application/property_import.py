"""自定义属性 CSV 导入导出域（v0.3.2 Task 0 自 service.py 拆分）。

`PropertyImportOperations` 以 mixin 组合进 `DstManagerService`：预览解析
CSV 为属性命令，复用受控编辑域的 `preview_changes`/`execute_changes`
完成执行与发布，行为与公共签名保持不变。
"""

import csv
import io
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.application.summaries import operation_digest
from dst_manager.domain.editing import (
    parse_property_csv_result,
    property_definitions_from_document,
)


class PropertyImportOperations:
    def preview_custom_property_import(
        self,
        workspace_id: str,
        base_revision_id: str,
        csv_data: bytes,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        parsed = parse_property_csv_result(csv_data)
        existing = {
            item.name.casefold(): item
            for item in property_definitions_from_document(workspace.document)
        }
        changes: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        diagnostics = [
            {
                "code": item.code,
                "severity": "error",
                "message": item.message,
                "line": item.line,
            }
            for item in parsed.diagnostics
        ]
        for record in parsed.records:
            line = record.line
            definition = record.definition
            previous = existing.get(definition.name.casefold())
            action = "add"
            if previous is not None and previous.type != definition.type:
                action = "conflict"
                diagnostics.append(
                    {
                        "code": "CUSTOM_PROPERTY_TYPE_CONFLICT",
                        "severity": "error",
                        "message": f"自定义属性类型冲突：{definition.name}",
                        "line": line,
                    },
                )
            elif previous is not None and previous.name != definition.name:
                action = "conflict"
                diagnostics.append(
                    {
                        "code": "CUSTOM_PROPERTY_NAME_DUPLICATE",
                        "severity": "error",
                        "message": f"自定义属性名称大小写冲突：{definition.name}",
                        "line": line,
                    },
                )
            elif previous is not None:
                action = "skip"
            else:
                command = {
                    "type": "add_custom_property",
                    "property_type": definition.type,
                    "name": definition.name,
                    "default_value": definition.default_value,
                }
                commands.append(command)
                existing[definition.name.casefold()] = definition
            changes.append(
                {
                    "line": line,
                    "action": action,
                    "type": definition.type,
                    "name": definition.name,
                    "default_value": definition.default_value,
                    "affected_sheet_count": len(workspace.document.sheets) if definition.type == "sheet" else 0,
                },
            )
        main_preview = self.preview_changes(workspace_id, base_revision_id, commands)
        diagnostics.extend(main_preview["diagnostics"])
        preview_digest = operation_digest(
            operation_type="property_csv_import",
            workspace_id=workspace_id,
            base_revision_id=base_revision_id,
            normalized_input={"commands": commands},
            semantic_diff={
                "changes": changes,
                "diagnostics": diagnostics,
                "change_semantic_diff": main_preview["semantic_diff"],
            },
            target_baselines={str(workspace.dst_path): base_revision_id},
        )
        return {
            **main_preview,
            "changes": changes,
            "commands": commands,
            "diagnostics": diagnostics,
            "executable": not any(item["severity"] == "error" for item in diagnostics),
            "preview_digest": preview_digest,
        }

    def import_custom_properties(
        self,
        workspace_id: str,
        base_revision_id: str,
        csv_data: bytes,
        preview_digest: str,
    ) -> dict[str, Any]:
        preview = self.preview_custom_property_import(workspace_id, base_revision_id, csv_data)
        if not preview["executable"]:
            raise ApplicationError("PLAN_INVALID", "属性 CSV 导入计划包含阻断诊断")
        if preview_digest != preview["preview_digest"]:
            raise ApplicationError("REPREVIEW_REQUIRED", "CSV 导入预览已变化或尚未确认，请重新预览并确认", 409)
        if not preview["commands"]:
            return {
                "id": None,
                "workspace_id": workspace_id,
                "status": "SUCCEEDED",
                "revision_id": base_revision_id,
                "no_op": True,
            }
        change_preview = self.preview_changes(workspace_id, base_revision_id, preview["commands"])
        return self.execute_changes(
            workspace_id,
            base_revision_id,
            preview["commands"],
            preview_digest=change_preview["preview_digest"],
        )

    def export_custom_properties_csv(self, workspace_id: str) -> bytes:
        workspace = self.get_workspace(workspace_id)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["type", "name", "default_value"])
        for definition in property_definitions_from_document(workspace.document):
            writer.writerow([definition.type, definition.name, definition.default_value])
        return stream.getvalue().encode("utf-8")
