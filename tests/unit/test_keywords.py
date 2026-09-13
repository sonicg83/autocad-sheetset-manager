# 不编号图纸关键字：规范化、上限校验与子集标题匹配（SPEC-DM-014）
import pytest

from dst_manager.domain.keywords import (
    MAX_UNNUMBERED_KEYWORD_CHARS,
    MAX_UNNUMBERED_KEYWORDS,
    KeywordLimitError,
    format_keywords,
    normalize_keywords,
    parse_keywords,
    title_matches_keywords,
)


def test_normalize_splits_halfwidth_and_fullwidth_commas() -> None:
    # 半角与全角逗号都作为分隔符（与图纸目录扩展的输出图纸过滤语义一致）
    assert normalize_keywords("封面,图纸目录") == ("封面", "图纸目录")
    assert normalize_keywords("封面，图纸目录") == ("封面", "图纸目录")
    assert normalize_keywords("封面, 图纸目录，说明") == ("封面", "图纸目录", "说明")


def test_normalize_ignores_blank_items_and_trims() -> None:
    assert normalize_keywords(" , 封面 ,, ") == ("封面",)
    assert normalize_keywords("") == ()
    assert normalize_keywords(None) == ()
    assert normalize_keywords([]) == ()


def test_normalize_dedupes_case_insensitively_keeping_first_spelling() -> None:
    assert normalize_keywords("Cover,cover,COVER") == ("Cover",)
    assert normalize_keywords("封面,封面") == ("封面",)
    assert normalize_keywords(["封面", " 封面 "]) == ("封面",)


def test_normalize_accepts_string_sequences() -> None:
    # 设置持久形态是字符串，但序列形态也必须可用（手编 settings.json / 未来迁移）
    assert normalize_keywords(["封面", " 图纸目录 "]) == ("封面", "图纸目录")
    assert normalize_keywords(("封面",)) == ("封面",)


def test_normalize_rejects_non_string_payload() -> None:
    with pytest.raises(TypeError):
        normalize_keywords(3)
    with pytest.raises(TypeError):
        normalize_keywords(["封面", 3])


def test_format_keywords_is_persist_form() -> None:
    assert format_keywords(("封面", "图纸目录")) == "封面,图纸目录"
    assert format_keywords(()) == ""


def test_parse_keywords_enforces_count_limit() -> None:
    value = ",".join(f"关键字{index}" for index in range(MAX_UNNUMBERED_KEYWORDS + 1))
    with pytest.raises(KeywordLimitError) as exc_info:
        parse_keywords(value)
    assert exc_info.value.kind == "count"
    assert exc_info.value.limit == MAX_UNNUMBERED_KEYWORDS
    assert exc_info.value.actual == MAX_UNNUMBERED_KEYWORDS + 1


def test_parse_keywords_enforces_single_keyword_length_limit() -> None:
    with pytest.raises(KeywordLimitError) as exc_info:
        parse_keywords("封" * (MAX_UNNUMBERED_KEYWORD_CHARS + 1))
    assert exc_info.value.kind == "length"
    assert exc_info.value.limit == MAX_UNNUMBERED_KEYWORD_CHARS
    assert exc_info.value.actual == MAX_UNNUMBERED_KEYWORD_CHARS + 1


def test_parse_keywords_accepts_boundary_values() -> None:
    value = ",".join(f"关键字{index}" for index in range(MAX_UNNUMBERED_KEYWORDS))
    assert len(parse_keywords(value)) == MAX_UNNUMBERED_KEYWORDS
    assert parse_keywords("封" * MAX_UNNUMBERED_KEYWORD_CHARS) == ("封" * MAX_UNNUMBERED_KEYWORD_CHARS,)


def test_title_matches_keywords_is_substring_or_semantics() -> None:
    keywords = ("封面", "图纸目录")
    assert title_matches_keywords("封面", keywords) is True
    assert title_matches_keywords("方案封面图", keywords) is True  # 字面子串命中
    assert title_matches_keywords("图纸目录", keywords) is True
    assert title_matches_keywords("平面图", keywords) is False
    assert title_matches_keywords("封面", ()) is False  # 空清单 = 全部子集照常编号


def test_title_matches_keywords_is_case_insensitive() -> None:
    assert title_matches_keywords("COVER SHEET", ("cover",)) is True
    assert title_matches_keywords("Cover", ("封面", "cover")) is True
