"""资产基础设施：文件存储与 ``assets`` 表仓储适配器。"""

from dst_builder.infrastructure.assets.store import (
    MAX_ASSET_BYTES,
    AssetRecord,
    AssetRepository,
    SqliteAssetRepository,
)

__all__ = [
    "MAX_ASSET_BYTES",
    "AssetRecord",
    "AssetRepository",
    "SqliteAssetRepository",
]
