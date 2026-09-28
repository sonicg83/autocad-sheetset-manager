"""标准库 ID 与规范化名称占用索引。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from dst_manager.domain.standard_identity import normalize_standard_name


@dataclass(frozen=True, slots=True)
class IdentityEntry:
    """供身份索引使用的最小库条目。"""

    standard_id: str
    name: str
    source: str
    status: str
    draft_id: str | None = None


class IdentityIndex:
    """以一次列表扫描建立 ID 与非空名称索引，供写入门禁复用。"""

    def __init__(self, entries: Iterable[IdentityEntry] = ()) -> None:
        self._by_id: dict[str, list[IdentityEntry]] = {}
        self._by_name: dict[str, list[IdentityEntry]] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: IdentityEntry) -> None:
        self._by_id.setdefault(entry.standard_id, []).append(entry)
        normalized = normalize_standard_name(entry.name)
        if normalized:
            self._by_name.setdefault(normalized, []).append(entry)

    def find_id(
        self, standard_id: str, *, exclude_draft_id: str | None = None
    ) -> IdentityEntry | None:
        return next(
            (
                entry
                for entry in self._by_id.get(standard_id, ())
                if exclude_draft_id is None or entry.draft_id != exclude_draft_id
            ),
            None,
        )

    def find_name(
        self, name: str, *, exclude_draft_id: str | None = None
    ) -> IdentityEntry | None:
        normalized = normalize_standard_name(name)
        if not normalized:
            return None
        return next(
            (
                entry
                for entry in self._by_name.get(normalized, ())
                if exclude_draft_id is None or entry.draft_id != exclude_draft_id
            ),
            None,
        )
