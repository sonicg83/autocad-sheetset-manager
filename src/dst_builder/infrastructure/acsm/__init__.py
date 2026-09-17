"""Builder AcSm 基础设施：从生成计划确定性构造与校验 DST（SPEC-DB-001 §8）。

二进制编解码与契约校验复用 ``dst_platform.acsm`` 共享原语；本包只拥有
Builder 自己的 DOM 工厂（``factory``）与语义投影（``projection``）。
"""

from dst_builder.infrastructure.acsm.factory import (
    DST_DB_VERSION,
    build_dst_bytes,
    build_dst_xml,
    dst_object_id,
)
from dst_builder.infrastructure.acsm.projection import (
    DST_VALIDATION_FAILED,
    DstValidationError,
    ensure_dst_valid,
    validate_dst_bytes,
)

__all__ = [
    "DST_DB_VERSION",
    "DST_VALIDATION_FAILED",
    "DstValidationError",
    "build_dst_bytes",
    "build_dst_xml",
    "dst_object_id",
    "ensure_dst_valid",
    "validate_dst_bytes",
]
