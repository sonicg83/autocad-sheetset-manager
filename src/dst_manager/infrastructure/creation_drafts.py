"""创建草稿的原子 JSON 持久化（PLAN-DM-036 Task 1）。

布局::

    <settings.data_dir>/creation-drafts/<draft_id>/draft.json

草稿根固定在 Manager 应用数据目录，不写入目标项目目录，也不写工作区。
写入走「临时文件 + ``os.replace``」的既有原子原语；文档只保留固定字段集，
因此请求无法夹带派生结果、任意模板路径、逐张 Sheet 输入或预览状态——文件里
出现白名单之外的字段即视为损坏并隔离。

本层只做**结构**门禁（字段集、类型、阶段白名单、组身份唯一），不做标准相关
的语义校验（属性是否可输入由应用层按固定标准判定），也不运行派生、编号或
DWG 命名。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dst_manager.domain.creation import (
    CREATION_INITIAL_STEP,
    CREATION_STEPS,
    CreationDraft,
    CreationGroupInput,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text

#: 草稿文档版本；v2 起 ``standard_version`` 为整数（v1 文本版本不再支持，
#: 本地草稿视为损坏隔离，不自动迁移）。
CREATION_DRAFT_SCHEMA_VERSION = 2
DRAFT_NAME = "draft.json"

_DRAFT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DRAFT_KEYS = frozenset(
    {
        "schema_version",
        "id",
        "standard_id",
        "standard_version",
        "revision",
        "step",
        "target_path",
        "sheetset_values",
        "groups",
    }
)
_GROUP_KEYS = frozenset(
    {
        "group_id",
        "created_order",
        "title",
        "count",
        "base_asset_id",
        "layout_asset_id",
        "paper_layout",
        "sheet_values",
    }
)


class CreationDraftStoreError(Exception):
    """创建草稿存储失败；``code`` 为稳定错误码，消息以该码开头。"""

    code = "CREATION_DRAFT_INVALID"


class CreationDraftNotFoundError(CreationDraftStoreError):
    code = "CREATION_DRAFT_NOT_FOUND"


class CreationDraftConflictError(CreationDraftStoreError):
    code = "CREATION_DRAFT_CONFLICT"


class CreationDraftCorruptError(CreationDraftStoreError):
    code = "CREATION_DRAFT_CORRUPT"


class CreationDraftInvalidError(CreationDraftStoreError):
    code = "CREATION_DRAFT_INVALID"


def _error(exception: type[CreationDraftStoreError], detail: str) -> CreationDraftStoreError:
    return exception(f"{exception.code}: {detail}")


class CreationDraftStore:
    """创建草稿仓储：初建、读取、带修订校验的保存与删除。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def create(
        self,
        standard_id: str,
        standard_version: int,
        sheetset_values: Mapping[str, str],
        *,
        step: str = CREATION_INITIAL_STEP,
    ) -> CreationDraft:
        """初建草稿：修订 1、空目标路径、无图纸组。

        ``sheetset_values`` 是初建那一次应用的普通属性默认值；此后保存与恢复
        都按传入值原样落盘，不回填默认值。
        """
        draft = CreationDraft(
            id=uuid.uuid4().hex,
            standard_id=standard_id,
            standard_version=standard_version,            revision=1,
            step=step,
            target_path="",
            sheetset_values=dict(sheetset_values),
            groups=(),
        )
        document = _document_or_invalid(draft)
        directory = self._directory(draft.id)
        directory.mkdir(parents=True)
        try:
            self._write(directory, document)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return draft

    def load(self, draft_id: str) -> CreationDraft:
        """读取草稿；文件损坏时隔离原文件并报 ``CREATION_DRAFT_CORRUPT``。"""
        path = self._document_path(draft_id)
        if not path.is_file():
            raise _error(CreationDraftNotFoundError, f"创建草稿 {draft_id!r} 不存在")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return _draft_from_document(document, draft_id)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self._quarantine(path, draft_id)
            raise _error(
                CreationDraftCorruptError, f"创建草稿 {draft_id!r} 内容损坏，已隔离：{exc}"
            ) from exc

    def save(
        self, draft_id: str, value: CreationDraft, *, expected_revision: int
    ) -> CreationDraft:
        """按乐观修订保存草稿；身份与标准固定，修订号由仓储递增。

        调用方提交的 ``value.revision`` 不参与判定：唯一权威是 ``expected_revision``
        与磁盘上的当前修订。标准身份与草稿 ID 由路径与初建值决定，请求不得改写。
        """
        stored = self.load(draft_id)
        if stored.revision != expected_revision:
            raise _error(
                CreationDraftConflictError,
                f"创建草稿 {draft_id!r} 修订已变化：expected={expected_revision}, current={stored.revision}",
            )
        if value.id != stored.id:
            raise _error(
                CreationDraftInvalidError, f"草稿身份 {value.id!r} 与路径 {draft_id!r} 不一致"
            )
        if (value.standard_id, value.standard_version) != (
            stored.standard_id,
            stored.standard_version,
        ):
            raise _error(
                CreationDraftInvalidError,
                f"草稿固定的标准 {stored.standard_id}@{stored.standard_version} 不可改写为 "
                f"{value.standard_id}@{value.standard_version}",
            )
        saved = replace(value, revision=stored.revision + 1)
        self._write(self._directory(draft_id), _document_or_invalid(saved))
        return saved

    def delete(self, draft_id: str) -> None:
        """删除草稿目录（含已隔离文件的父目录）；不存在时报缺失。"""
        directory = self._directory(draft_id)
        if not directory.is_dir():
            raise _error(CreationDraftNotFoundError, f"创建草稿 {draft_id!r} 不存在")
        shutil.rmtree(directory)

    def _directory(self, draft_id: str) -> Path:
        """草稿目录；ID 非法时拒绝，避免越界路径。"""
        if not _DRAFT_ID.fullmatch(draft_id):
            raise _error(CreationDraftInvalidError, f"创建草稿 ID {draft_id!r} 非法")
        return self.root / draft_id

    def _document_path(self, draft_id: str) -> Path:
        return self._directory(draft_id) / DRAFT_NAME

    def _write(self, directory: Path, document: Mapping[str, object]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            directory / DRAFT_NAME, json.dumps(document, ensure_ascii=False, indent=2)
        )

    def _quarantine(self, path: Path, draft_id: str) -> None:
        """把损坏文件移出草稿目录（同盘 rename），保留现场供排查。"""
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        os.replace(path, self.root / f"{draft_id}.corrupt-{stamp}.json")


# ---- 文档编解码（结构门禁的唯一实现） ------------------------------------


def _document_or_invalid(draft: CreationDraft) -> dict[str, object]:
    """序列化请求提交的草稿值；结构越界时以 ``CREATION_DRAFT_INVALID`` 拒绝。"""
    try:
        return _draft_to_document(draft)
    except ValueError as exc:
        raise _error(CreationDraftInvalidError, str(exc)) from exc


def _draft_to_document(draft: CreationDraft) -> dict[str, object]:
    """把草稿值序列化为受控文档；越界字段以 ``ValueError`` 拒绝。"""
    if not isinstance(draft, CreationDraft):
        raise ValueError(f"草稿值类型非法：{type(draft).__name__}")  # noqa: TRY004 - 草稿结构非法统一归类
    groups = []
    for item in draft.groups:
        if not isinstance(item, CreationGroupInput):
            raise ValueError(f"图纸组值类型非法：{type(item).__name__}")  # noqa: TRY004 - 草稿结构非法统一归类
        groups.append(
            {
                "group_id": item.group_id,
                "created_order": item.created_order,
                "title": item.title,
                "count": item.count,
                "base_asset_id": item.base_asset_id,
                "layout_asset_id": item.layout_asset_id,
                "paper_layout": item.paper_layout,
                "sheet_values": dict(item.sheet_values),
            }
        )
    document: dict[str, object] = {
        "schema_version": CREATION_DRAFT_SCHEMA_VERSION,
        "id": draft.id,
        "standard_id": draft.standard_id,
        "standard_version": draft.standard_version,
        "revision": draft.revision,
        "step": draft.step,
        "target_path": draft.target_path,
        "sheetset_values": dict(draft.sheetset_values),
        "groups": groups,
    }
    _validate_document(document)
    return document


def _draft_from_document(document: object, draft_id: str) -> CreationDraft:
    """把磁盘文档还原为草稿值；结构非法以 ``ValueError`` 拒绝。"""
    _validate_document(document)
    if not isinstance(document, dict):  # 与门禁同口径的窄化，供类型检查器使用
        raise ValueError("草稿文档必须是 JSON 对象")  # noqa: TRY004 - 草稿结构非法统一归类
    if document["id"] != draft_id:
        raise ValueError(f"文档身份 {document['id']!r} 与路径 {draft_id!r} 不一致")
    groups = cast("list[dict[str, object]]", document["groups"])
    return CreationDraft(
        id=str(document["id"]),
        standard_id=str(document["standard_id"]),
        standard_version=cast(int, document["standard_version"]),
        revision=cast(int, document["revision"]),
        step=str(document["step"]),
        target_path=str(document["target_path"]),
        sheetset_values=dict(cast("dict[str, str]", document["sheetset_values"])),
        groups=tuple(
            CreationGroupInput(
                group_id=str(item["group_id"]),
                created_order=cast(int, item["created_order"]),
                title=str(item["title"]),
                count=cast(int, item["count"]),
                base_asset_id=str(item["base_asset_id"]),
                layout_asset_id=str(item["layout_asset_id"]),
                paper_layout=str(item["paper_layout"]),
                sheet_values=dict(cast("dict[str, str]", item["sheet_values"])),
            )
            for item in groups
        ),
    )


def _validate_document(document: object) -> None:
    """结构门禁：字段集、类型、阶段白名单与组身份唯一性。

    只做结构判定，不判定「图名非空」「张数为正」等语义（它们属于预览诊断），
    因此允许保存未填完的输入。文件与请求值共用本门禁：文件失败即损坏，请求
    值失败即非法。
    """
    if not isinstance(document, dict):
        raise ValueError("草稿文档必须是 JSON 对象")  # noqa: TRY004 - 草稿结构非法统一归类
    if set(document) != _DRAFT_KEYS:
        unexpected = sorted(set(document) - _DRAFT_KEYS)
        missing = sorted(_DRAFT_KEYS - set(document))
        raise ValueError(f"草稿字段越界：多出={unexpected}, 缺少={missing}")
    if document["schema_version"] != CREATION_DRAFT_SCHEMA_VERSION:
        raise ValueError(f"草稿 schema_version {document['schema_version']!r} 不受支持")
    for key in ("id", "standard_id"):
        _require_text(document[key], key)
    _require_int(document["standard_version"], "standard_version", minimum=1)
    _require_int(document["revision"], "revision", minimum=1)
    if document["step"] not in CREATION_STEPS:
        raise ValueError(f"草稿阶段 {document['step']!r} 不在 {list(CREATION_STEPS)} 内")
    if not isinstance(document["target_path"], str):
        raise ValueError("target_path 必须是字符串")  # noqa: TRY004 - 草稿结构非法统一归类
    _require_string_map(document["sheetset_values"], "sheetset_values")
    groups = document["groups"]
    if not isinstance(groups, list):
        raise ValueError("groups 必须是数组")  # noqa: TRY004 - 草稿结构非法统一归类
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for item in groups:
        _validate_group(item, seen_ids, seen_orders)


def _validate_group(item: object, seen_ids: set[str], seen_orders: set[int]) -> None:
    if not isinstance(item, dict):
        raise ValueError("图纸组必须是 JSON 对象")  # noqa: TRY004 - 草稿结构非法统一归类
    if set(item) != _GROUP_KEYS:
        unexpected = sorted(set(item) - _GROUP_KEYS)
        missing = sorted(_GROUP_KEYS - set(item))
        raise ValueError(f"图纸组字段越界：多出={unexpected}, 缺少={missing}")
    _require_text(item["group_id"], "group_id")
    if item["group_id"] in seen_ids:
        raise ValueError(f"图纸组身份重复：{item['group_id']!r}")
    seen_ids.add(item["group_id"])
    _require_int(item["created_order"], "created_order", minimum=0)
    # created_order 是创建序：数组顺序可重排，它不随之变化，故只要求唯一。
    if item["created_order"] in seen_orders:
        raise ValueError(f"created_order 重复：{item['created_order']!r}")
    seen_orders.add(item["created_order"])
    _require_int(item["count"], "count", minimum=0)
    for key in ("title", "base_asset_id", "layout_asset_id", "paper_layout"):
        if not isinstance(item[key], str):
            raise ValueError(f"图纸组 {key} 必须是字符串")  # noqa: TRY004 - 草稿结构非法统一归类
    _require_string_map(item["sheet_values"], "sheet_values")


def _require_text(value: object, key: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} 必须是非空字符串")


def _require_int(value: object, key: str, *, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{key} 必须是不小于 {minimum} 的整数")


def _require_string_map(value: object, key: str) -> None:
    if not isinstance(value, dict) or any(
        not isinstance(name, str) or not name or not isinstance(item, str)
        for name, item in value.items()
    ):
        raise ValueError(f"{key} 必须是「非空字符串 → 字符串」映射")
