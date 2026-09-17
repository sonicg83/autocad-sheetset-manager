"""Manager 文本/XML 校验入口。

``normalize_derived_name`` 的危险名称字符判定已切换到共享纯函数
``dst_platform.contracts.naming.contains_unsafe_filename_char``
（PLAN-DB-001 Task 6，字符集取并集，语义只紧不松：共享函数额外拒绝
DEL 控制字符 ``\\x7f``）；错误码与 ``ValueError(f"{label}无效")`` 消息保持不变。
"""

from pathlib import Path

from dst_platform.contracts.naming import contains_unsafe_filename_char


def validate_xml_text(value: str) -> str:
    if any(
        not (
            ord(character) in {0x09, 0x0A, 0x0D}
            or 0x20 <= ord(character) <= 0xD7FF
            or 0xE000 <= ord(character) <= 0xFFFD
            or 0x10000 <= ord(character) <= 0x10FFFF
        )
        for character in value
    ):
        raise ValueError("文本包含 XML 1.0 禁止字符")
    return value


def validate_absolute_source_file(value: str) -> str:
    if any(character in value for character in ("\x00", "\r", "\n")) or not Path(value).is_absolute():
        raise ValueError("布局来源必须是无控制字符的绝对路径")
    return value


def normalize_derived_name(value: str, label: str) -> str:
    normalized = validate_xml_text(value).strip()
    if not normalized or contains_unsafe_filename_char(normalized):
        raise ValueError(f"{label}无效")
    return normalized


def normalize_property_name(value: str) -> str:
    normalized = validate_xml_text(value).strip()
    if not normalized:
        raise ValueError("自定义属性名称不能为空")
    return normalized


def validate_sheet_set_name(value: str) -> str:
    validate_xml_text(value)
    if not value.strip():
        raise ValueError("图纸集名称不能为空")
    return value


def validate_custom_properties(value: dict[str, str]) -> dict[str, str]:
    for name, item in value.items():
        normalize_property_name(name)
        validate_xml_text(item)
    return value
