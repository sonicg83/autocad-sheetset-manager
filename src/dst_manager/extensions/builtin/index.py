"""固定内置扩展索引（PLAN-DM-020 Task 1 / ARCH-DM-006 §4.1）。

白名单直接引用已审核的工厂函数与随包清单资源（EP-01）：清单数据文件不得
携带 Python 模块名、类名、脚本路径或可执行命令，宿主也绝不从 YAML 导入
模块。PyInstaller 打包按本索引显式包含资源，不做文件扫描猜测。
"""

from __future__ import annotations

from dst_manager.extensions.builtin.sheet_catalog.extension import (
    create_sheet_catalog_extension,
)
from dst_manager.extensions.contracts import BuiltinExtensionEntry

BUILTIN_EXTENSION_INDEX: tuple[BuiltinExtensionEntry, ...] = (
    BuiltinExtensionEntry(
        manifest_resource="dst_manager/extensions/builtin/sheet_catalog/manifest.yaml",
        factory=create_sheet_catalog_extension,
    ),
)
