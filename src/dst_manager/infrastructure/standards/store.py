"""官方/用户图纸标准库的稳定公共门面。"""

from __future__ import annotations

from dst_manager.infrastructure.standards.draft_storage import StandardDraftStorage
from dst_manager.infrastructure.standards.identity_lookup import StandardIdentityLookup
from dst_manager.infrastructure.standards.package_io import StandardPackageIO
from dst_manager.infrastructure.standards.store_common import (
    PublishedStandard,
    StandardDraft,
    StandardStoreError,
    StandardSummary,
)
from dst_manager.infrastructure.standards.store_core import StandardStoreCore


class StandardStore(
    StandardDraftStorage,
    StandardIdentityLookup,
    StandardPackageIO,
    StandardStoreCore,
):
    """官方只读库与用户标准库的稳定仓储接口。"""


__all__ = [
    "PublishedStandard",
    "StandardDraft",
    "StandardStore",
    "StandardStoreError",
    "StandardSummary",
]
