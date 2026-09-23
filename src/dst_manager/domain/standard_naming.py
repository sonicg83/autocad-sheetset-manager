"""标准级唯一 DWG 命名模板（PLAN-DM-038 Task 3）。

每个标准必须且只能有一条全项目 DWG 命名模板，应用于所有子集主 DWG。模板
只生成文件名**主体**，``.dwg`` 由本模块固定追加；系统不替换或删除非法字符，
而是定位到片段并返回稳定错误码。

允许字段只有 ``subset.scope``、``subset.name``、``subset.sequence`` 与全部
``sheetset`` 属性；``sheet`` 属性令牌在结构层与渲染层都被拒绝。求值顺序为
``普通 sheetset 属性 → sheetset 映射属性 → sheetset 组合属性 → DWG 命名``。

调用约定：``sheetset_values`` 以 ``property_id`` 为键。普通属性必须提供键
（可以为空串），派生属性在上游失败时**必须缺失键**——缺失即代表「上游无法
计算」，与「合法的空值」区分开；此时命名结果 ``ok`` 为 False。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from dst_manager.domain.standard_models import (
    DrawingStandard,
    StandardDiagnostic,
    StandardSegment,
)
from dst_manager.domain.standard_semantics import MAX_PAD_WIDTH, PAD_FORMAT_PATTERN

__all__ = [
    "EXTENSION",
    "MAX_FILENAME_LENGTH",
    "NamingResult",
    "SubsetNamingContext",
    "publish_naming_diagnostics",
    "render_dwg_filename",
    "segment_safety_violations",
    "validate_dwg_filenames",
]

#: 系统固定追加的扩展名。
EXTENSION = ".dwg"
#: 含扩展名的完整文件名长度上限。
MAX_FILENAME_LENGTH = 240

#: Windows 保留设备名（比较时忽略大小写，只看第一个句点之前的部分）。
RESERVED_DEVICE_NAMES = frozenset(
    ["con", "prn", "aux", "nul", "clock$"]
    + [f"com{index}" for index in range(1, 10)]
    + [f"lpt{index}" for index in range(1, 10)]
)
#: Windows 文件名非法字符（含路径分隔符与盘符冒号）。
ILLEGAL_CHARACTERS = frozenset('<>:"/\\|?*')


def segment_safety_violations(text: str) -> tuple[str, ...]:
    """文本命中的 Windows 片段安全违规种类（按固定顺序，可同时命中多个）。

    只做判定不做替换：``character`` 是控制字符或 Windows 非法字符，``trailing``
    是尾随空格或句点，``reserved`` 是保留设备名（忽略首个句点之前的部分比较）。
    DWG 命名主体与项目路径片段共用这份规则，各自映射成本层错误码与文案；由调用
    方决定取首个违规还是收集全部。空文本视为无违规。
    """
    if not text:
        return ()
    violations: list[str] = []
    if any(character in ILLEGAL_CHARACTERS or ord(character) < 32 for character in text):
        violations.append("character")
    if text[-1] in " .":
        violations.append("trailing")
    if text.split(".", 1)[0].casefold() in RESERVED_DEVICE_NAMES:
        violations.append("reserved")
    return tuple(violations)


@dataclass(frozen=True, slots=True)
class SubsetNamingContext:
    """一个子集的命名上下文：图纸号范围、名称与 1 起始物理顺序。"""

    scope: str
    name: str
    sequence: int


@dataclass(frozen=True, slots=True)
class NamingResult:
    """一次命名结果；``ok`` 为 False 时调用方不得使用该文件名。"""

    context: SubsetNamingContext
    body: str = ""
    filename: str = ""
    diagnostics: tuple[StandardDiagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.is_error for diagnostic in self.diagnostics)


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: str = "error",
    segment_index: int | None = None,
    property_id: str | None = None,
) -> StandardDiagnostic:
    return StandardDiagnostic(
        code=code,
        message=message,
        severity=severity,
        property_id=property_id,
        segment_index=segment_index,
    )


def _pad_width(code: str) -> int | None:
    if not PAD_FORMAT_PATTERN.fullmatch(code):
        return None
    width = int(code)
    return width if 1 <= width <= MAX_PAD_WIDTH else None


def _body_diagnostics(body: str) -> list[StandardDiagnostic]:
    """文件名主体安全校验；不做任何字符替换，只返回定位性错误。

    片段安全规则来自 :func:`segment_safety_violations`（与项目路径片段校验共用）；
    命名契约只报首个违规，因此按规则顺序取第一个命中的种类。
    """
    if not body:
        return [_diagnostic("DWG_NAME_EMPTY", "DWG 命名结果主体为空")]
    if EXTENSION in body.lower():
        return [
            _diagnostic(
                "DWG_NAME_EXTENSION_FORBIDDEN", f"命名主体 {body!r} 不得自行包含 .dwg 扩展名"
            )
        ]
    if body in (".", ".."):
        return [_diagnostic(*_body_violation_diagnostic("character", body))]
    violations = segment_safety_violations(body)
    if violations:
        return [_diagnostic(*_body_violation_diagnostic(violations[0], body))]
    if len(body) + len(EXTENSION) > MAX_FILENAME_LENGTH:
        return [
            _diagnostic(
                "DWG_NAME_TOO_LONG",
                f"含扩展名的文件名长度 {len(body) + len(EXTENSION)} 超过 {MAX_FILENAME_LENGTH}",
            )
        ]
    return []


def _body_violation_diagnostic(kind: str, body: str) -> tuple[str, str]:
    """片段安全违规种类 → DWG 命名错误码与文案。"""
    codes = {
        "character": "DWG_NAME_CHARACTER_INVALID",
        "trailing": "DWG_NAME_TRAILING_CHARACTER",
        "reserved": "DWG_NAME_RESERVED_DEVICE",
    }
    messages = {
        "character": f"命名主体 {body!r} 含路径片段、控制字符或 Windows 非法字符",
        "trailing": f"命名主体 {body!r} 不得以空格或句点结尾",
        "reserved": f"命名主体 {body!r} 是 Windows 保留设备名",
    }
    return (codes[kind], messages[kind])


def _system_value(
    segment: StandardSegment,
    context: SubsetNamingContext,
    index: int,
    diagnostics: list[StandardDiagnostic],
) -> str | None:
    field = segment.system_field
    if field == "subset.sequence":
        rendered = str(context.sequence)
        if segment.format is None:
            return rendered
        width = _pad_width(segment.format)
        if width is None:
            diagnostics.append(
                _diagnostic(
                    "STANDARD_SEGMENT_FORMAT_INVALID",
                    f"DWG 命名模板片段 #{index} 的格式码 {segment.format!r} 不是登记的数字补零格式",
                    segment_index=index,
                )
            )
            return None
        return rendered.zfill(width)
    if field == "subset.scope":
        value = context.scope
    elif field == "subset.name":
        value = context.name
    else:
        diagnostics.append(
            _diagnostic(
                "STANDARD_NAMING_FIELD_SCOPE_INVALID",
                f"DWG 命名模板越权引用系统字段 {field!r}",
                segment_index=index,
            )
        )
        return None
    if value == "":
        diagnostics.append(
            _diagnostic(
                "STANDARD_SYSTEM_VALUE_MISSING",
                f"DWG 命名模板片段 #{index} 缺少必需系统值 {field!r}",
                segment_index=index,
            )
        )
        return None
    return value


def render_dwg_filename(
    standard: DrawingStandard,
    sheetset_values: Mapping[str, str],
    context: SubsetNamingContext,
) -> NamingResult:
    """按模板渲染一个子集的 DWG 文件名（含固定追加的 ``.dwg``）。

    令牌缺失、作用域越权或主体非法时返回带 error 诊断的结果，``ok`` 为
    False 且 ``filename`` 为空；调用方不得使用不可用结果。
    """
    parts: list[str] = []
    diagnostics: list[StandardDiagnostic] = []

    def abort() -> NamingResult:
        return NamingResult(context=context, diagnostics=tuple(diagnostics))

    for index, segment in enumerate(standard.dwg_naming.segments):
        if segment.literal is not None:
            parts.append(segment.literal)
            continue
        if segment.system_field is not None:
            value = _system_value(segment, context, index, diagnostics)
            if value is None:
                return abort()
            parts.append(value)
            continue
        property_id = segment.property_id
        assert property_id is not None
        prop = standard.find_property(property_id)
        if prop is None:
            diagnostics.append(
                _diagnostic(
                    "STANDARD_SEGMENT_REFERENCE_UNKNOWN",
                    f"DWG 命名模板片段 #{index} 引用未知属性 {property_id!r}",
                    segment_index=index,
                    property_id=property_id,
                )
            )
            return abort()
        if prop.scope != "sheetset":
            diagnostics.append(
                _diagnostic(
                    "STANDARD_NAMING_FIELD_SCOPE_INVALID",
                    f"DWG 命名模板片段 #{index} 越权引用 {prop.scope} 属性 {property_id!r}",
                    segment_index=index,
                    property_id=property_id,
                )
            )
            return abort()
        if property_id not in sheetset_values:
            diagnostics.append(
                _diagnostic(
                    "DWG_NAMING_SOURCE_MISSING",
                    f"DWG 命名模板片段 #{index} 的 sheetset 属性 {property_id!r} 无法计算",
                    segment_index=index,
                    property_id=property_id,
                )
            )
            return abort()
        parts.append(sheetset_values[property_id])

    body = "".join(parts)
    diagnostics.extend(_body_diagnostics(body))
    return NamingResult(
        context=context,
        body=body,
        filename=f"{body}{EXTENSION}",
        diagnostics=tuple(diagnostics),
    )


def validate_dwg_filenames(
    standard: DrawingStandard,
    sheetset_values: Mapping[str, str],
    subsets: Sequence[SubsetNamingContext],
) -> tuple[NamingResult, ...]:
    """渲染全部子集并检查目标路径冲突（Windows 大小写不敏感语义）。

    只对可用结果做冲突判定；任一子集得到同一目标时，参与冲突的每个结果都
    带上 ``DWG_TARGET_COLLISION``。
    """
    results = [
        render_dwg_filename(standard, sheetset_values, context) for context in subsets
    ]
    groups: dict[str, list[int]] = {}
    for index, result in enumerate(results):
        if not result.ok:
            continue
        groups.setdefault(result.filename.casefold(), []).append(index)
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        for index in indexes:
            result = results[index]
            results[index] = replace(
                result,
                diagnostics=result.diagnostics
                + (
                    _diagnostic(
                        "DWG_TARGET_COLLISION",
                        f"目标文件名 {result.filename!r} 与本批其他子集冲突",
                    ),
                ),
            )
    return tuple(results)


def publish_naming_diagnostics(standard: DrawingStandard) -> tuple[StandardDiagnostic, ...]:
    """发布前命名门禁：模板同时缺少 ``subset.scope`` 与 ``subset.sequence`` 时告警。"""
    fields = {segment.system_field for segment in standard.dwg_naming.segments}
    if "subset.scope" in fields or "subset.sequence" in fields:
        return ()
    return (
        _diagnostic(
            "DWG_NAMING_UNIQUENESS_UNPROVEN",
            "DWG 命名模板未使用 subset.scope 或 subset.sequence，只能在具体项目中证明唯一性",
            severity="warning",
        ),
    )
