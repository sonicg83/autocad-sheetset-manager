"""共享危险名称校验契约：dst_platform.contracts.naming（PLAN-DB-001 Task 2）。

规范依据 SPEC-DB-001 §4：

* 禁止 ``<>:"/\\|?*`` 与控制字符；
* 不得以句点/空格结尾（保存前先去除首尾空白，因此尾部空格经 trim 后不可能幸存）；
* 去除扩展名并忽略大小写后不得等于保留设备名 CON/PRN/AUX/NUL/COM1~9/LPT1~9；
* 规范化后的文件基名最长 180 个字符。

Manager 既有等价实现位于 ``src/dst_manager/domain/text_validation.py``（模块级正则
``_UNSAFE_DERIVED_NAME``），其字符类比 §4 多禁止 ``;`` 与 ``=``。共享纯函数取两者
并集，保证「Manager 拒绝的名称共享函数必拒绝」，Manager 侧（Task 6）切换到共享实现
时语义只紧不松。本测试只读 Manager 代码做等价证明；Builder 产品代码不得 import
dst_manager（由 tests/architecture/test_product_boundaries.py 门禁保证）。
"""

import pytest

from dst_manager.domain.text_validation import (
    normalize_derived_name as manager_validate_derived_name,
)
from dst_platform.contracts.naming import (
    MAX_WINDOWS_BASE_NAME_CHARS,
    WINDOWS_RESERVED_DEVICE_NAMES,
    WINDOWS_UNSAFE_FILENAME_CHARS,
    validate_windows_file_name,
)

# Manager _UNSAFE_DERIVED_NAME 的字面字符类（控制字符区间 \x00-\x1f 单独参数化）。
MANAGER_UNSAFE_CHARS = '<>/\\":;?*|='
MANAGER_CONTROL_CHARS = tuple(chr(code) for code in range(0x20))

SPEC_RESERVED_NAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
)


def test_shared_sets_match_spec_and_manager_union() -> None:
    """共享字符集 = §4 规范集合 ∪ Manager 既有字符集合；保留设备名集合与 §4 一致。"""
    assert WINDOWS_UNSAFE_FILENAME_CHARS == frozenset('<>:"/\\|?*;=')
    assert WINDOWS_RESERVED_DEVICE_NAMES == frozenset(SPEC_RESERVED_NAMES)
    assert MAX_WINDOWS_BASE_NAME_CHARS == 180


@pytest.mark.parametrize(
    "character",
    [*MANAGER_UNSAFE_CHARS, *MANAGER_CONTROL_CHARS],
)
def test_manager_rejected_chars_are_also_rejected_by_shared(character: str) -> None:
    """Manager 既有危险名称样例逐字符证明共享函数语义一致（Manager 拒绝 ⇒ 共享拒绝）。"""
    name = f"平面{character}图"

    with pytest.raises(ValueError):
        manager_validate_derived_name(name, "布局名称")
    with pytest.raises(ValueError):
        validate_windows_file_name(name)


@pytest.mark.parametrize("name", ["a<b", 'c"d', "e:f", "g|h", "i?j", "k*l", "x/y", "x\\y"])
def test_spec_unsafe_chars_rejected(name: str) -> None:
    """SPEC §4 明确禁止的字符同样被共享函数拒绝。"""
    with pytest.raises(ValueError):
        validate_windows_file_name(name)


@pytest.mark.parametrize("name", ["名称.", "版本.", "A-001."])
def test_trailing_dot_rejected(name: str) -> None:
    """规范化后不得以句点结尾。"""
    with pytest.raises(ValueError):
        validate_windows_file_name(name)


def test_trailing_space_is_trimmed_not_rejected() -> None:
    """保存前统一去除首尾空白，尾部空格经 trim 后视为合法名称。"""
    assert validate_windows_file_name("名称 ") == "名称"


@pytest.mark.parametrize(
    "name",
    [
        *SPEC_RESERVED_NAMES,
        *(name.lower() for name in SPEC_RESERVED_NAMES),
        *(f"{name}.dwg" for name in SPEC_RESERVED_NAMES),
        "Com1.dwt",
        "NUL.DWG",
    ],
)
def test_reserved_device_names_rejected_case_insensitively_with_extension(name: str) -> None:
    """去除扩展名并忽略大小写后等于保留设备名的名称必须拒绝。"""
    with pytest.raises(ValueError):
        validate_windows_file_name(name)


def test_empty_and_whitespace_only_rejected() -> None:
    with pytest.raises(ValueError):
        validate_windows_file_name("")
    with pytest.raises(ValueError):
        validate_windows_file_name("   ")


def test_base_name_length_limit_is_180_stem_chars() -> None:
    """基名长度按去除扩展名后的主干计，恰好 180 合法、181 拒绝。"""
    stem_limit = "图" * MAX_WINDOWS_BASE_NAME_CHARS
    assert validate_windows_file_name(f"{stem_limit}.dwg") == f"{stem_limit}.dwg"
    with pytest.raises(ValueError):
        validate_windows_file_name(f"{stem_limit}图.dwg")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("首层平面图", "首层平面图"),
        ("  首层平面图  ", "首层平面图"),
        ("A1 平面", "A1 平面"),
        ("总平面图-2", "总平面图-2"),
        ("图纸.2026", "图纸.2026"),
    ],
)
def test_safe_names_accepted_and_trimmed(name: str, expected: str) -> None:
    """安全名称共享函数与 Manager 返回一致的规范化结果。"""
    assert validate_windows_file_name(name) == expected
    assert manager_validate_derived_name(name, "布局名称") == expected
