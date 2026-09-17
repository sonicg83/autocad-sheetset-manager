"""DST Codec 平台所有权契约（PLAN-DB-001 Task 6，产品无关）。

所有权：``dst_platform.acsm.codec``（自 ``dst_manager.infrastructure.dst_codec.codec``
迁入）；Manager 原路径仅薄 re-export，行为由 tests/unit 既有 Manager 回归守护。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dst_platform.acsm.codec import CodecError, DstCodec

_XML = "<root><sheet>平面图</sheet></root>".encode()


def test_sha256_matches_hashlib() -> None:
    assert DstCodec.sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_decode_bytes_returns_decoded_xml() -> None:
    xml = DstCodec().decode_bytes(DstCodec().encode_bytes(_XML))
    assert xml == _XML


def test_decode_bytes_rejects_invalid_xml() -> None:
    with pytest.raises(CodecError, match="DST_DECODE_INVALID_XML"):
        DstCodec().decode_bytes(b"<root")


def test_encode_bytes_rejects_invalid_xml() -> None:
    with pytest.raises(CodecError, match="XML_INVALID"):
        DstCodec().encode_bytes(b"<root")


def test_decode_file_missing_reports_dst_not_found(tmp_path: Path) -> None:
    with pytest.raises(CodecError, match="DST_NOT_FOUND"):
        DstCodec().decode_file(tmp_path / "missing.dst")


def test_encode_file_writes_encoded_and_decode_roundtrip(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "sample.dst"
    codec = DstCodec()
    codec.encode_file(_XML, destination)
    assert destination.is_file()
    assert codec.decode_file(destination) == _XML
