"""图纸目录内置扩展的最小生命周期外壳（PLAN-DM-020 Task 1）。

预览动作（Task 6）、受限表达式与模板（Task 5）和候选 XLSX 导出（Task 7～9）
后续落地；本任务只提供注册表要求的 ``start``/``stop`` 生命周期。首期不注册
后台计时器、外部进程或网络连接。
"""

from __future__ import annotations

from dst_manager.extensions.contracts import Extension


class SheetCatalogExtension:
    """首期无后台资源；start/stop 只标记生命周期边界。"""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def create_sheet_catalog_extension() -> Extension:
    """固定索引引用的工厂函数。"""
    return SheetCatalogExtension()
