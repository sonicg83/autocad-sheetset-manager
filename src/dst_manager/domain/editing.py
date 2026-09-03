import copy
import csv
import io
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dst_manager.domain.models import (
    CustomPropertyDefinition,
    DerivedDocument,
    DerivedSubset,
    LayoutReference,
    PropertyDefinitionDiff,
    Sheet,
    SheetSetDocument,
    Subset,
    SuffixOptions,
)


class EditingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class PropertyCsvDiagnostic:
    code: str
    message: str
    line: int | None


@dataclass(frozen=True, slots=True)
class PropertyCsvRecord:
    line: int
    definition: CustomPropertyDefinition


@dataclass(frozen=True, slots=True)
class PropertyCsvParseResult:
    records: list[PropertyCsvRecord]
    diagnostics: list[PropertyCsvDiagnostic]


_NUMBER_RANGE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s+(.+?)\s*$")
_UNSAFE_NAME = re.compile(r"[<>/\\\":;?*|=\r\n\x00-\x1f]")
_CONTROL_CHAR = re.compile(r"[\x00-\x1f\x7f]")
_CHINESE_DIGITS = "零一二三四五六七八九"


def normalize_property_name(name: str) -> str:
    validate_xml_text(name, "CUSTOM_PROPERTY_NAME_INVALID")
    if _CONTROL_CHAR.search(name):
        raise EditingError("CUSTOM_PROPERTY_NAME_INVALID", "自定义属性名称不能包含控制字符")
    normalized = name.strip()
    if not normalized:
        raise EditingError("CUSTOM_PROPERTY_NAME_EMPTY", "自定义属性名称不能为空")
    return normalized


def validate_property_value(value: object) -> str:
    return validate_xml_text(
        value,
        "CUSTOM_PROPERTY_VALUE_INVALID",
        "自定义属性值包含 XML 1.0 禁止字符",
    )


def validate_xml_text(
    value: object,
    error_code: str = "XML_TEXT_INVALID",
    error_message: str = "文本包含 XML 1.0 禁止字符",
) -> str:
    """校验可写入 XML 1.0 文本节点或属性的 Unicode 字符。"""
    text = str(value)
    for character in text:
        codepoint = ord(character)
        if not (
            codepoint in {0x09, 0x0A, 0x0D}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            raise EditingError(error_code, error_message)
    return text


def _property_definition(raw: CustomPropertyDefinition | tuple[str, str, str]) -> CustomPropertyDefinition:
    if isinstance(raw, CustomPropertyDefinition):
        property_type, name, default_value = raw.type, raw.name, raw.default_value
    else:
        property_type, name, default_value = raw
    if property_type not in {"sheetset", "sheet"}:
        raise EditingError("CUSTOM_PROPERTY_TYPE_INVALID", f"自定义属性类型无效：{property_type}")
    return CustomPropertyDefinition(
        property_type,
        normalize_property_name(str(name)),
        validate_property_value(default_value),
    )


def _validated_property_definition(
    raw: CustomPropertyDefinition | tuple[str, str, str],
    seen: dict[str, CustomPropertyDefinition],
) -> CustomPropertyDefinition:
    definition = _property_definition(raw)
    key = definition.name.casefold()
    if key in seen:
        previous = seen[key]
        code = (
            "CUSTOM_PROPERTY_TYPE_CONFLICT"
            if previous.type != definition.type
            else "CUSTOM_PROPERTY_NAME_DUPLICATE"
        )
        raise EditingError(code, f"自定义属性名称重复：{definition.name}")
    seen[key] = definition
    return definition


def validate_property_definitions(
    definitions: Iterable[CustomPropertyDefinition | tuple[str, str, str]],
) -> list[CustomPropertyDefinition]:
    result: list[CustomPropertyDefinition] = []
    seen: dict[str, CustomPropertyDefinition] = {}
    for raw in definitions:
        result.append(_validated_property_definition(raw, seen))
    return result


def property_definitions_from_document(document: SheetSetDocument) -> list[CustomPropertyDefinition]:
    """提取稳定属性定义；图纸定义锚点只保存名称，默认值始终为空。"""
    result = [
        CustomPropertyDefinition("sheetset", name, value)
        for name, value in sorted(
            document.custom_properties.items(),
            key=lambda item: (item[0].casefold(), item[0]),
        )
    ]
    sheet_names: dict[str, str] = {
        name.casefold(): name
        for name in document.sheet_property_definitions
    }
    for sheet in document.sheets:
        for name in sheet.custom_properties:
            key = name.casefold()
            previous = sheet_names.get(key)
            if previous is None or name < previous:
                sheet_names[key] = name
    result.extend(
        CustomPropertyDefinition("sheet", name, "")
        for name in sorted(sheet_names.values(), key=lambda item: (item.casefold(), item))
    )
    return result


def _csv_diagnostic(exc: EditingError, line: int | None) -> PropertyCsvDiagnostic:
    _, separator, message = str(exc).partition(": ")
    return PropertyCsvDiagnostic(exc.code, message if separator else str(exc), line)


def parse_property_csv_result(data: bytes) -> PropertyCsvParseResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        error = EditingError("CUSTOM_PROPERTY_CSV_ENCODING_INVALID", "CSV 必须使用 UTF-8 编码")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, None)])

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        error = EditingError("CUSTOM_PROPERTY_CSV_HEADER_INVALID", "CSV 缺少表头")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, 1)])
    except csv.Error:
        error = EditingError("CUSTOM_PROPERTY_CSV_HEADER_INVALID", "CSV 表头格式无效")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, 1)])
    if len(header) == 1 and ";" in header[0]:
        error = EditingError("CUSTOM_PROPERTY_CSV_HEADER_INVALID", "CSV 必须使用逗号分隔")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, 1)])
    if len(header) != 3:
        error = EditingError("CUSTOM_PROPERTY_CSV_COLUMNS_INVALID", "CSV 只能包含三列")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, 1)])
    if header != ["type", "name", "default_value"]:
        error = EditingError("CUSTOM_PROPERTY_CSV_HEADER_INVALID", "CSV 表头必须为 type,name,default_value")
        return PropertyCsvParseResult([], [_csv_diagnostic(error, 1)])

    records: list[PropertyCsvRecord] = []
    diagnostics: list[PropertyCsvDiagnostic] = []
    seen: dict[str, CustomPropertyDefinition] = {}
    previous_end = reader.line_num
    while True:
        start_line = previous_end + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error:
            error = EditingError("CUSTOM_PROPERTY_CSV_COLUMNS_INVALID", "CSV 记录格式无效")
            diagnostics.append(_csv_diagnostic(error, start_line))
            break
        previous_end = reader.line_num
        if not row or all(not item.strip() for item in row):
            continue
        if len(row) != 3:
            error = EditingError("CUSTOM_PROPERTY_CSV_COLUMNS_INVALID", "CSV 只能包含三列")
            diagnostics.append(_csv_diagnostic(error, start_line))
            continue
        try:
            definition = _validated_property_definition((row[0].strip(), row[1], row[2]), seen)
        except EditingError as exc:
            diagnostics.append(_csv_diagnostic(exc, start_line))
            continue
        records.append(PropertyCsvRecord(start_line, definition))
    return PropertyCsvParseResult(records, diagnostics)


def parse_property_csv(data: bytes) -> list[CustomPropertyDefinition]:
    result = parse_property_csv_result(data)
    if result.diagnostics:
        diagnostic = result.diagnostics[0]
        raise EditingError(diagnostic.code, diagnostic.message)
    return [record.definition for record in result.records]


def _chinese_number(value: int) -> str:
    if value <= 0:
        raise EditingError("SHEET_TITLE_ORDINAL_INVALID", "图纸标题序号必须为正整数")
    if value < 10:
        return _CHINESE_DIGITS[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + _CHINESE_DIGITS[value % 10]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _CHINESE_DIGITS[tens] + "十" + (_CHINESE_DIGITS[ones] if ones else "")
    if value < 1000:
        return "".join(_CHINESE_DIGITS[int(digit)] for digit in str(value))
    raise EditingError("SHEET_TITLE_ORDINAL_OUT_OF_RANGE", "中文标题后缀序号不能超过 999")


def format_sheet_title(base_title: str, ordinal: int | None, enabled: bool, suffix_type: int) -> str:
    title = base_title.strip()
    if not title:
        raise EditingError("SHEET_TITLE_EMPTY", "图纸标题不能为空")
    if suffix_type not in {1, 2}:
        raise EditingError("NUMBER_SUFFIX_TYPE_INVALID", "标题后缀类型只能为 1 或 2")
    if not enabled or ordinal is None:
        return title
    if ordinal < 1:
        raise EditingError("SHEET_TITLE_ORDINAL_INVALID", "图纸标题序号必须为正整数")
    suffix = _chinese_number(ordinal) if suffix_type == 1 else str(ordinal)
    return f"{title} ({suffix})"


def derive_group_titles(
    groups: list[tuple[str, str, int]],
    enabled: bool,
    suffix_type: int,
) -> list[list[str]]:
    for _, title, count in groups:
        format_sheet_title(title, None, enabled, suffix_type)
        if count < 1:
            raise EditingError("EMPTY_SUBSET", "子集必须至少包含一张图纸")
    result: list[list[str]] = [[] for _ in groups]
    by_title: dict[str, list[tuple[int, int, str, int]]] = {}
    for index, (number_range, title, count) in enumerate(groups):
        by_title.setdefault(title.strip().casefold(), []).append(
            (_range_start(number_range), index, title.strip(), count),
        )
    for members in by_title.values():
        members.sort(key=lambda item: item[0])
        group_title = members[0][2]
        total = sum(item[3] for item in members)
        ordinal = 1
        for _, index, _, count in members:
            if total == 1:
                result[index] = [format_sheet_title(group_title, None, enabled, suffix_type)]
                continue
            result[index] = [
                format_sheet_title(group_title, ordinal + offset, enabled, suffix_type)
                for offset in range(count)
            ]
            ordinal += count
    return result


def _compressed_group_title(base_title: str, sheet_titles: list[str]) -> str:
    """把组内多张带后缀图纸的标题压缩为单个带区间后缀的标题。

    例如三张 `图纸目录 (一)`/`图纸目录 (二)`/`图纸目录 (三)` 压缩为
    `图纸目录 (一)-(三)`，供派生 DWG 文件名使用。组内仅一张时沿用基础
    标题（向后兼容）；任一张标题结构不符合 `基础标题 (后缀)` 时防御性
    回退为基础标题，保持与旧行为一致。
    """
    if len(sheet_titles) < 2:
        return base_title  # 组内仅一张时沿用基础标题（SPEC-DM-008 §3.2 向后兼容）
    prefix = f"{base_title} ("
    suffixes: list[str] = []
    for title in sheet_titles:
        if title.startswith(prefix) and title.endswith(")"):
            suffixes.append(title[len(prefix):-1])
        else:
            return base_title  # 结构异常时防御性回退为基础标题
    return f"{prefix}{')-('.join(suffixes)})"


def derive_document_structure(
    document: SheetSetDocument,
    commands: list[dict[str, Any]],
    suffix_options: SuffixOptions,
) -> DerivedDocument:
    subsets = sorted(copy.deepcopy(document.subsets), key=lambda item: item.order)
    document_seed = _document_state_seed(document)
    subset_by_id = {subset.acsm_id: subset for subset in subsets}
    titles = {subset.acsm_id: _editable_subset_title(subset.name) for subset in subsets}
    affected: set[str] = set()
    layout_sources = _existing_layout_sources(document)
    property_diff = _apply_property_commands(document, subsets, commands)

    for command_index, command in enumerate(commands):
        kind = command.get("type")
        if kind == "import_custom_properties":
            continue
        if kind == "update_subset":
            subset_id = str(command.get("subset_id", ""))
            if subset_id not in subset_by_id:
                raise EditingError("SUBSET_NOT_FOUND", f"找不到子集：{subset_id}")
            title = str(command.get("title", command.get("name", ""))).strip()
            if not title:
                raise EditingError("SHEET_TITLE_EMPTY", "子集标题不能为空")
            titles[subset_id] = _editable_subset_title(title)
            affected.add(subset_id)
        elif kind == "insert_sheet":
            target = _target_subset(subset_by_id, command)
            if "number" in command or "title" in command:
                raise EditingError("SHEET_INSERT_DERIVED_FIELD_NOT_ACCEPTED", "新增图纸不接收图号或标题")
            count = _positive_int(command.get("count", 1), "SHEET_INSERT_COUNT_INVALID")
            source = _layout_source(command)
            if source["type"] == "existing_snapshot" and (not source["file"] or not source["layout"]):
                source = _resolve_existing_snapshot(document, target.acsm_id)
            position = _insertion_index(command, len(target.sheets), "SHEET_POSITION_INVALID")
            new_sheets = []
            for offset in range(count):
                sheet_id = _new_id(document_seed, "sheet", command_index, offset)
                new_sheets.append(Sheet(sheet_id, "", "", LayoutReference(source["file"], "", source["layout"], ""), {}))
                layout_sources[sheet_id] = dict(source)
            target.sheets[position:position] = new_sheets
            affected.add(target.acsm_id)
        elif kind == "insert_subset":
            count = _positive_int(command.get("initial_sheet_count", 1), "INITIAL_SHEET_COUNT_INVALID")
            title = str(command.get("title", "")).strip()
            if not title:
                raise EditingError("SHEET_TITLE_EMPTY", "子集标题不能为空")
            source = _layout_source(command)
            subset_id = _new_id(document_seed, "subset", command_index, 0)
            sheets = []
            for offset in range(count):
                sheet_id = _new_id(document_seed, "subset-sheet", command_index, offset)
                sheets.append(Sheet(sheet_id, "", "", LayoutReference(source["file"], "", source["layout"], ""), {}))
                layout_sources[sheet_id] = dict(source)
            subset = Subset(subset_id, title, 0, sheets)
            position = _insertion_index(command, len(subsets), "SUBSET_POSITION_INVALID", allow_empty=True)
            subsets.insert(position, subset)
            subset_by_id[subset_id] = subset
            titles[subset_id] = title
            affected.add(subset_id)
        elif kind == "delete_sheet":
            subset, index, sheet = _locate_sheet(subsets, str(command.get("sheet_id", "")))
            subset.sheets.pop(index)
            layout_sources.pop(sheet.acsm_id, None)
            affected.add(subset.acsm_id)
        elif kind == "delete_subset":
            subset_id = str(command.get("subset_id", ""))
            subset = subset_by_id.get(subset_id)
            if subset is None:
                raise EditingError("SUBSET_NOT_FOUND", f"找不到子集：{subset_id}")
            if command.get("confirm_delete_all_sheets") is not True:
                raise EditingError("DELETE_SUBSET_SHEETS_CONFIRMATION_REQUIRED", "必须确认删除子集内全部图纸")
            if command.get("confirm_delete_main_dwg") is not True:
                raise EditingError("DELETE_SUBSET_DWG_CONFIRMATION_REQUIRED", "必须确认删除子集对应主 DWG")
            subsets.remove(subset)
            subset_by_id.pop(subset_id)
            titles.pop(subset_id, None)
            for sheet in subset.sheets:
                layout_sources.pop(sheet.acsm_id, None)
            affected.add(subset_id)
        elif kind in {"update_sheet_set", "update_sheet"}:
            continue
        else:
            raise EditingError("COMMAND_UNSUPPORTED", f"不支持的命令：{kind}")

    _apply_added_sheet_property_defaults(subsets, property_diff.added)

    start, width = _number_seed(document)
    current = start
    for subset in subsets:
        if not subset.sheets:
            raise EditingError("EMPTY_SUBSET", "子集必须至少包含一张图纸")
        for sheet in subset.sheets:
            sheet.number = str(current).zfill(width)
            current += 1

    groups = [
        (_number_range(subset.sheets), titles[subset.acsm_id], len(subset.sheets))
        for subset in subsets
    ]
    group_titles = derive_group_titles(groups, suffix_options.enabled, suffix_options.suffix_type)
    derived_subsets = []
    for subset, titles_for_subset in zip(subsets, group_titles):
        title = titles[subset.acsm_id]
        for sheet, sheet_title in zip(subset.sheets, titles_for_subset):
            sheet.title = sheet_title
            sheet.layout.layout_name = _layout_name(sheet.number, sheet.title)
        number_range = _number_range(subset.sheets)
        source_target = _source_target_file(document, subset, layout_sources)
        target_file = _target_file_name(source_target, number_range, _compressed_group_title(title, titles_for_subset))
        derived_subsets.append(
            DerivedSubset(subset.acsm_id, title, number_range, f"{number_range} {title}", subset.sheets, source_target, target_file),
        )

    return DerivedDocument(derived_subsets, sorted(affected), property_diff, layout_sources)


def _locate_sheet(subsets: list[Subset], sheet_id: str) -> tuple[Subset, int, Sheet]:
    for subset in subsets:
        for index, sheet in enumerate(subset.sheets):
            if sheet.acsm_id == sheet_id:
                return subset, index, sheet
    raise EditingError("SHEET_NOT_FOUND", f"找不到图纸：{sheet_id}")


def _apply_added_sheet_property_defaults(subsets: list[Subset], definitions: list[CustomPropertyDefinition]) -> None:
    sheet_definitions = [definition for definition in definitions if definition.type == "sheet"]
    if not sheet_definitions:
        return
    for subset in subsets:
        for sheet in subset.sheets:
            for definition in sheet_definitions:
                sheet.custom_properties.setdefault(definition.name, definition.default_value)


def _apply_property_commands(
    document: SheetSetDocument,
    subsets: list[Subset],
    commands: list[dict[str, Any]],
) -> PropertyDefinitionDiff:
    added: list[CustomPropertyDefinition] = []
    skipped: list[CustomPropertyDefinition] = []
    existing = _existing_property_definitions(document)
    for command in commands:
        if command.get("type") != "import_custom_properties":
            continue
        definitions = validate_property_definitions(command.get("definitions", []))
        for definition in definitions:
            key = definition.name.casefold()
            previous = existing.get(key)
            if previous is not None and previous.type != definition.type:
                raise EditingError("CUSTOM_PROPERTY_TYPE_CONFLICT", f"自定义属性类型冲突：{definition.name}")
            if previous is not None:
                skipped.append(definition)
                continue
            existing[key] = definition
            added.append(definition)
            if definition.type == "sheet":
                for subset in subsets:
                    for sheet in subset.sheets:
                        sheet.custom_properties[definition.name] = definition.default_value
    return PropertyDefinitionDiff(added, skipped)


def _existing_property_definitions(document: SheetSetDocument) -> dict[str, CustomPropertyDefinition]:
    definitions = {
        name.casefold(): CustomPropertyDefinition("sheetset", name, value)
        for name, value in document.custom_properties.items()
    }
    sheet_names = list(document.sheet_property_definitions)
    sheet_names.extend(name for sheet in document.sheets for name in sheet.custom_properties)
    for name in sheet_names:
        definitions.setdefault(name.casefold(), CustomPropertyDefinition("sheet", name, ""))
    return definitions


def _existing_layout_sources(document: SheetSetDocument) -> dict[str, dict[str, str]]:
    return {
        sheet.acsm_id: {
            "type": "existing_snapshot",
            "file": str(sheet.layout.resolved_path or sheet.layout.file_name),
            "layout": sheet.layout.layout_name,
        }
        for sheet in document.sheets
    }


def _target_subset(subsets: dict[str, Subset], command: dict[str, Any]) -> Subset:
    target_id = str(command.get("target_subset_id", ""))
    if target_id not in subsets:
        raise EditingError("SUBSET_NOT_FOUND", f"找不到目标子集：{target_id}")
    return subsets[target_id]


def _layout_source(command: dict[str, Any]) -> dict[str, str]:
    source = command.get("source") or {}
    source_type = str(source.get("type", ""))
    source_file = str(source.get("file", "")).strip()
    source_layout = str(source.get("layout", "")).strip()
    if source_type not in {"existing_snapshot", "template_layout"}:
        raise EditingError("LAYOUT_SOURCE_INVALID", "新增图纸的来源文件或布局无效")
    if source_type == "template_layout" and (not source_file or not source_layout):
        raise EditingError("LAYOUT_SOURCE_INVALID", "新增图纸的来源文件或布局无效")
    return {"type": source_type, "file": source_file, "layout": source_layout}


def _resolve_existing_snapshot(document: SheetSetDocument, target_subset_id: str) -> dict[str, str]:
    """从目标子集首张图纸的 DST 登记解析已有布局来源（只读原始文档）。

    解析发生在 layout_sources 写入前，保证 planning/baseline/cad_job 读到
    齐全的三字段。目标子集缺图或首图登记为空时阻断（SPEC-DM-008 F-02）。
    """
    original = next(
        (subset for subset in document.subsets if subset.acsm_id == target_subset_id),
        None,
    )
    if original is not None and original.sheets:
        sheet = original.sheets[0]
        file_name = str(sheet.layout.resolved_path or sheet.layout.file_name)
        layout = sheet.layout.layout_name
        if file_name and layout:
            return {"type": "existing_snapshot", "file": file_name, "layout": layout}
    raise EditingError("LAYOUT_SOURCE_INVALID", "目标子集缺少可用的已有布局来源")


def _positive_int(value: object, code: str) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise EditingError(code, "数量必须为正整数") from exc
    if count < 1:
        raise EditingError(code, "数量必须为正整数")
    return count


def _insertion_index(
    command: dict[str, Any],
    length: int,
    code: str,
    *,
    allow_empty: bool = False,
) -> int:
    if "ordinal" not in command and "position" in command:
        position = int(command["position"])
        if position < 0 or position > length:
            raise EditingError(code, f"插入位置越界：{position}")
        return position
    ordinal = int(command.get("ordinal", 1 if allow_empty and length == 0 else length))
    if length == 0:
        if allow_empty and ordinal == 1:
            return 0
        raise EditingError(code, "空集合只能使用序号 1")
    if ordinal < 1 or ordinal > length:
        raise EditingError(code, f"插入序号越界：{ordinal}")
    placement = str(command.get("placement", command.get("direction", "after"))).strip().casefold()
    if placement in {"before", "向前添加", "front"}:
        return ordinal - 1
    if placement in {"after", "向后添加", "back"}:
        return ordinal
    raise EditingError(code, f"插入方向无效：{placement}")


def _number_seed(document: SheetSetDocument) -> tuple[int, int]:
    for sheet in document.sheets:
        if sheet.number.isdigit():
            return int(sheet.number), len(sheet.number)
    return 1, 1


def _number_range(sheets: list[Sheet]) -> str:
    if not sheets:
        raise EditingError("EMPTY_SUBSET", "子集必须至少包含一张图纸")
    return sheets[0].number if len(sheets) == 1 else f"{sheets[0].number}-{sheets[-1].number}"


def _range_start(number_range: str) -> int:
    first = number_range.split("-", 1)[0].strip()
    if not first.isdigit():
        raise EditingError("NUMBER_RANGE_INVALID", f"图号范围无效：{number_range}")
    return int(first)


def _editable_subset_title(name: str) -> str:
    stripped = name.strip()
    match = _NUMBER_RANGE.fullmatch(stripped)
    return match.group(3).strip() if match else stripped


def _document_state_seed(document: SheetSetDocument) -> str:
    parts = [f"database:{document.database_id}"]
    for subset in sorted(document.subsets, key=lambda item: item.order):
        parts.append(f"subset:{subset.acsm_id}")
        parts.extend(f"sheet:{sheet.acsm_id}" for sheet in subset.sheets)
    return "\x1f".join(parts)


def _new_id(document_seed: str, kind: str, command_index: int, offset: int) -> str:
    value = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"dst-manager:v021:{document_seed}:{kind}:{command_index}:{offset}",
    )
    return "g" + str(value).upper()


def _layout_name(number: str, title: str) -> str:
    name = f"{number.strip()} {title.strip()}".strip()
    if not name or len(name) > 255 or _UNSAFE_NAME.search(name):
        raise EditingError("LAYOUT_NAME_INVALID", f"布局名无效：{name!r}")
    return name


def _source_target_file(
    document: SheetSetDocument,
    derived_subset: Subset,
    layout_sources: dict[str, dict[str, str]],
) -> str:
    original = next((subset for subset in document.subsets if subset.acsm_id == derived_subset.acsm_id), None)
    if original is not None:
        for sheet in original.sheets:
            value = str(sheet.layout.resolved_path or sheet.layout.file_name)
            if value:
                return value
    for sheet in derived_subset.sheets:
        source = layout_sources.get(sheet.acsm_id, {})
        if source.get("file"):
            return source["file"]
    return ""


def _target_file_name(source_target: str, number_range: str, title: str) -> str:
    base = Path(source_target) if source_target else Path(f"{number_range} {title}.dwg")
    prefix_match = re.match(r"^(.*?-)(?=\d)", base.stem)
    prefix = prefix_match.group(1) if prefix_match else ""
    file_name = f"{prefix}{number_range} {title}.dwg"
    if _UNSAFE_NAME.search(file_name) or len(file_name) > 240:
        raise EditingError("DWG_FILE_NAME_INVALID", f"派生DWG文件名无效：{file_name}")
    return str(base.with_name(file_name))
