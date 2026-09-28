"""旧版已发布标准的只读快照解析。"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import NAMESPACE_URL, uuid5

from dst_manager.domain.standard_errors import StandardSchemaError
from dst_manager.domain.standard_models import LegacyDrawingStandard
from dst_manager.domain.standard_schema import (
    LEGACY_STANDARD_ID_PATTERN,
    parse_standard_version,
)
from dst_manager.domain.standard_semantics import validate_published_semantics
from dst_manager.domain.standards import parse_standard_draft_document


def parse_legacy_published_standard_document(
    data: Mapping[str, object], *, standard_id: str, version: int
) -> LegacyDrawingStandard:
    """校验 schema v2 快照并转成仅供当前进程读取的模型。

    不迁移文件，也不将旧名称式 ID、发布版本或未知发布时间带入新文档。
    """
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 2:
        raise StandardSchemaError("STANDARD_SCHEMA_VERSION_UNSUPPORTED: 不是旧版 schema v2 文档")
    stored_id = data.get("standard_id")
    if (
        not isinstance(stored_id, str)
        or not LEGACY_STANDARD_ID_PATTERN.fullmatch(stored_id)
        or stored_id != standard_id
    ):
        raise StandardSchemaError("STANDARD_ID_INVALID: 旧快照 ID 与目录身份不匹配")
    stored_version = parse_standard_version(data.get("version"))
    if stored_version != version:
        raise StandardSchemaError("STANDARD_VERSION_INVALID: 旧快照版本与目录身份不匹配")

    description = data.get("description")
    release_notes = data.get("release_notes", "")
    if description is not None and not isinstance(description, str):
        raise StandardSchemaError("STANDARD_DESCRIPTION_INVALID: description 必须是字符串")
    if not isinstance(release_notes, str):
        raise StandardSchemaError("STANDARD_DESCRIPTION_INVALID: release_notes 必须是字符串")

    compatible_document = dict(data)
    compatible_document["schema_version"] = 3
    # 临时 UUID 仅用于复用 v3 结构校验；最终模型仍保留旧身份供只读上下文识别。
    compatible_document["standard_id"] = str(uuid5(NAMESPACE_URL, f"dst-manager:{standard_id}"))
    compatible_document["published_at"] = None
    compatible_document["description"] = description if description is not None else release_notes
    compatible_document.pop("version", None)
    compatible_document.pop("release_notes", None)

    draft = parse_standard_draft_document(compatible_document)
    validate_published_semantics(draft)  # 旧发布快照仍须满足当前标准的发布语义。
    return LegacyDrawingStandard(
        schema_version=2,
        standard_id=standard_id,
        version=stored_version,
        published_at=None,
        name=draft.name,
        description=draft.description,
        supported_cad_versions=draft.supported_cad_versions,
        properties=draft.properties,
        dwg_naming=draft.dwg_naming,
        assets=draft.assets,
        numbering=draft.numbering,
        dependencies=draft.dependencies,
    )
