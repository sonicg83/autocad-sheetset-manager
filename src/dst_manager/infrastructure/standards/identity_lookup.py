"""标准 UUID 与规范化名称的占用查询。"""

from __future__ import annotations

from dst_manager.domain.standard_identity import (
    normalize_standard_name,
    parse_standard_id,
)
from dst_manager.infrastructure.standards.identity_index import (
    IdentityEntry,
    IdentityIndex,
)
from dst_manager.infrastructure.standards.store_common import _error


class StandardIdentityLookup:
    """StandardIdentityLookup 的标准库操作组合。"""

    def published_name_owners(self) -> dict[str, str]:
        """规范化非空名称 → 已发布标准 ID，用于保留旧调用门面。"""
        owners: dict[str, str] = {}
        for summary in self.list():
            if summary.status != "published":
                continue
            normalized = normalize_standard_name(summary.name)
            if normalized:
                owners.setdefault(normalized, summary.standard_id)
        return owners

    def check_published_name(self, standard_id: str, name: str) -> None:
        """兼容入口：检查官方与用户已发布标准中的名称冲突。"""
        owner = self.published_name_owners().get(normalize_standard_name(name))
        if owner is not None and owner != standard_id:
            raise _error(
                "STANDARD_NAME_CONFLICT",
                f"标准名称 {name!r} 已由已发布标准 {owner!r} 占用",
            )

    def _identity_index(self) -> IdentityIndex:
        return IdentityIndex(
            IdentityEntry(
                standard_id=summary.standard_id,
                name=summary.name,
                source=summary.source,
                status=summary.status,
                draft_id=summary.draft_id,
            )
            for summary in self.list()
        )

    def _identity_entries(self) -> list[IdentityEntry]:
        return [
            IdentityEntry(
                standard_id=summary.standard_id,
                name=summary.name,
                source=summary.source,
                status=summary.status,
                draft_id=summary.draft_id,
            )
            for summary in self.list()
        ]

    def check_available_identity(
        self,
        standard_id: str,
        name: str,
        *,
        exclude_draft_id: str | None = None,
    ) -> None:
        """拒绝库内重复 UUID 或重复的非空规范化名称。"""
        try:
            canonical_id = parse_standard_id(standard_id)
        except ValueError as exc:
            raise _error("STANDARD_ID_INVALID", "标准 ID 必须是带连字符的 UUID") from exc
        if not isinstance(name, str):
            raise _error("STANDARD_NAME_INVALID", "标准名称必须是字符串")
        index = self._identity_index()
        id_owner = index.find_id(canonical_id, exclude_draft_id=exclude_draft_id)
        if id_owner is not None:
            raise _error(
                "STANDARD_ID_EXISTS",
                f"标准 ID 已被名称 {id_owner.name!r} 占用",
            )
        name_owner = index.find_name(name, exclude_draft_id=exclude_draft_id)
        if name_owner is not None:
            raise _error(
                "STANDARD_NAME_CONFLICT",
                f"标准名称 {name!r} 已由标准 {name_owner.standard_id!r} 占用",
            )
