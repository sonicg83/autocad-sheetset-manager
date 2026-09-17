"""规范化 JSON、确定性哈希与派生值（PLAN-DB-001 Task 2，SPEC-DB-001 §4/§5）。

冻结两类确定性契约：

* 规范化 JSON：UTF-8、键名排序、无多余空白、数组保序、``ensure_ascii=False``；
  SHA-256 与 UUIDv5 命名空间（``dst-builder:revision:`` / ``dst-builder:plan:`` /
  ``dst-builder:package:``）按 §5/§9 公式逐字转录；
* 派生值：``sheet_number`` / ``layout_name`` / ``dwg_name`` 按 §4 公式派生，
  起始序号位数超过 ``width`` 即图号溢出。
"""

import uuid

import pytest

from dst_builder.domain.normalization import (
    canonical_json,
    dwg_name,
    layout_name,
    package_id_from_manifest_sha256,
    plan_id_from_sha256,
    revision_id_from_sha256,
    sha256_hex,
    sheet_number,
    task_id_from_revision_sha256,
)


def test_canonical_json_sorts_keys_and_compacts_whitespace() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_keeps_non_ascii_literal() -> None:
    assert canonical_json({"名": "值"}) == '{"名":"值"}'


def test_canonical_json_keeps_array_order() -> None:
    assert canonical_json({"sheets": ["a", "b"]}) == '{"sheets":["a","b"]}'
    assert canonical_json({"sheets": ["b", "a"]}) == '{"sheets":["b","a"]}'


def test_key_order_does_not_change_hash() -> None:
    """键顺序变化不改变哈希（§5：相同规范化输入得到相同哈希）。"""
    left = sha256_hex(canonical_json({"a": 1, "b": {"c": 2, "d": 3}}))
    right = sha256_hex(canonical_json({"b": {"d": 3, "c": 2}, "a": 1}))
    assert left == right


def test_array_order_change_changes_hash() -> None:
    """数组保序：数组顺序属于语义，顺序变化必须改变哈希。"""
    left = sha256_hex(canonical_json({"sheets": ["a", "b"]}))
    right = sha256_hex(canonical_json({"sheets": ["b", "a"]}))
    assert left != right


def test_sha256_hex_matches_spec_formula() -> None:
    """§5 公式直录：``hashlib.sha256(canonical.encode('utf-8')).hexdigest()``。"""
    import hashlib

    canonical = '{"a":1,"名":"值"}'
    assert sha256_hex(canonical) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert len(sha256_hex(canonical)) == 64


def test_uuid_ids_use_spec_namespaces() -> None:
    """§5/§9 命名空间公式直录：revision/plan/package 三类确定性 ID。"""
    sha256 = "a" * 64
    assert revision_id_from_sha256(sha256) == str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:revision:{sha256}")
    )
    assert plan_id_from_sha256(sha256) == str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:plan:{sha256}")
    )
    assert package_id_from_manifest_sha256(sha256) == str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:package:{sha256}")
    )


def test_task_id_derives_from_revision_sha256_and_semantic_path() -> None:
    """任务 ID 由计划哈希（同修订）与对象语义路径 UUIDv5 派生，不得使用随机值。"""
    sha256 = "b" * 64
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:task:{sha256}:drawing"))
    assert task_id_from_revision_sha256(sha256, "drawing") == expected
    assert task_id_from_revision_sha256(sha256, "drawing") == task_id_from_revision_sha256(
        sha256, "drawing"
    )
    assert task_id_from_revision_sha256(sha256, "sheetset") != expected


def test_sheet_number_zero_pads_start_within_width() -> None:
    assert sheet_number("A-", 1, 3) == "A-001"
    assert sheet_number("", 42, 6) == "000042"
    assert sheet_number("A-", 999999, 6) == "A-999999"
    assert sheet_number("A-", 0, 1) == "A-0"


def test_sheet_number_overflow_rejected() -> None:
    """图号溢出：起始序号十进制位数不得超过位数。"""
    with pytest.raises(ValueError):
        sheet_number("A-", 1234, 3)


def test_layout_name_and_dwg_name_follow_spec_formula() -> None:
    """§4 派生公式：layout_name = 图号 + 空格 + 图名；dwg_name = layout_name + .dwg。"""
    number = sheet_number("A-", 1, 3)
    assert layout_name(number, "首层平面图") == "A-001 首层平面图"
    assert dwg_name(layout_name(number, "首层平面图")) == "A-001 首层平面图.dwg"
