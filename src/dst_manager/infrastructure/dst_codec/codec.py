"""DST Codec 兼容导出（PLAN-DB-001 Task 6：实现所有权已迁至 dst_platform.acsm.codec）。

本模块只做薄 re-export；唯一实现见 ``dst_platform/acsm/codec.py``。
"""

from dst_platform.acsm.codec import _DECODE, _ENCODE, CodecError, DstCodec

__all__ = ["_DECODE", "_ENCODE", "CodecError", "DstCodec"]
