"""图纸目录内置扩展：生命周期外壳与预览动作（PLAN-DM-020 Task 1/6）。

预览动作只从 :class:`~dst_manager.extensions.capabilities.ExtensionContext`
获取冻结工作区快照（SPEC-DM-012 §12 只读边界：不触碰 reader、DST、数据库
或文件系统），把请求模板交给 :mod:`.preview` 构建规范化预览、兼容性诊断与
确定性摘要。受限表达式与模板（Task 5）、候选 XLSX 导出（Task 7～9）分别
在各自模块落地。首期不注册后台计时器、外部进程或网络连接。
"""

from __future__ import annotations

from dst_manager.extensions.builtin.sheet_catalog.preview import (
    SheetCatalogPreview,
    SheetCatalogPreviewRequest,
    build_preview,
)
from dst_manager.extensions.capabilities import ExtensionContext
from dst_manager.extensions.contracts import Extension

#: 与随包 manifest.yaml 保持一致（由单元测试钉住，防止漂移）。
EXTENSION_ID = "dst-manager.sheet-catalog"
EXTENSION_VERSION = "0.1.0"
PREVIEW_ACTION_ID = "export-xlsx"


class SheetCatalogExtension:
    """首期无后台资源；start/stop 只标记生命周期边界。"""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def preview(
        self, context: ExtensionContext, request: SheetCatalogPreviewRequest
    ) -> SheetCatalogPreview:
        """对上下文冻结快照构建图纸目录预览（修订漂移由上下文拒绝）。"""
        snapshot = context.workspace_snapshot()
        return build_preview(
            snapshot,
            request.template,
            extension_id=EXTENSION_ID,
            extension_version=EXTENSION_VERSION,
            action_id=PREVIEW_ACTION_ID,
        )


def create_sheet_catalog_extension() -> Extension:
    """固定索引引用的工厂函数。"""
    return SheetCatalogExtension()
