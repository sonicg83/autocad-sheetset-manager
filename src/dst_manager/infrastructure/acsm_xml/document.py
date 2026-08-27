import copy
import hashlib
import re
import uuid
from pathlib import Path

from lxml import etree

from dst_manager.domain.editing import (
    EditingError,
    normalize_property_name,
    validate_property_value,
    validate_xml_text,
)
from dst_manager.domain.models import (
    CustomPropertyDefinition,
    DerivedDocument,
    LayoutReference,
    RepairReport,
    Severity,
    Sheet,
    SheetSetDocument,
    Subset,
    ValidationIssue,
)
from dst_manager.infrastructure.acsm_xml.contract import (
    CLSID_LAYOUT_REFERENCE,
    CLSID_PROPERTY_BAG,
    CLSID_PROPERTY_VALUE,
    CLSID_SHEET,
    CLSID_SHEET_VIEWS,
    CLSID_SUBSET,
    validate_contract,
    validate_schema,
)
from dst_manager.infrastructure.acsm_xml.repair import AcsmRepairer

_ID_RE = re.compile(r"^g[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
_ACSM_ID_ATTR_RE = re.compile(rb'ID="g[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}"')
_HANDLE_RE = re.compile(r"^[0-9A-Fa-f]+$")


class AcsmValidationError(ValueError):
    @property
    def code(self) -> str:
        return str(self).split(":", 1)[0]


def _children(node: etree._Element, name: str):
    return [child for child in node if etree.QName(child).localname == name]


def _prop(node: etree._Element, name: str, default: str = "") -> str:
    for child in _children(node, "AcSmProp"):
        if child.get("propname") == name:
            return child.text or ""
    return default


def _set_prop(node: etree._Element, name: str, value: str) -> None:
    props = [child for child in _children(node, "AcSmProp") if child.get("propname") == name]
    if len(props) != 1:
        raise AcsmValidationError(f"CONTROLLED_PROPERTY_INVALID: {name}")
    text = _acsm_xml_text(value)
    try:
        props[0].text = text
    except (UnicodeError, ValueError) as exc:
        raise AcsmValidationError("XML_TEXT_INVALID") from exc


def _acsm_xml_text(value: object, code: str = "XML_TEXT_INVALID") -> str:
    try:
        return validate_xml_text(value, code)
    except EditingError as exc:
        raise AcsmValidationError(exc.code) from exc


def _custom_property_scope(node: etree._Element) -> str:
    flags = [child for child in _children(node, "AcSmProp") if child.get("propname") == "Flags"]
    if not flags:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_MISSING: {node.get('propname', '')}")
    if len(flags) != 1:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_INVALID: {node.get('propname', '')}")
    scope = (flags[0].text or "").strip()
    if scope not in {"1", "2"}:
        raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_INVALID: {node.get('propname', '')}")
    return scope


def _custom_property_values(node: etree._Element) -> list[etree._Element]:
    return [child for child in _children(node, "AcSmProp") if child.get("propname") == "Value"]


def _tag_like(node: etree._Element, local_name: str) -> str:
    namespace = etree.QName(node).namespace
    return f"{{{namespace}}}{local_name}" if namespace else local_name


def _new_acsm_id() -> str:
    return "g" + str(uuid.uuid4()).upper()


def _scope_for_property_type(property_type: str) -> str:
    if property_type == "sheetset":
        return "1"
    if property_type == "sheet":
        return "2"
    raise AcsmValidationError(f"CUSTOM_PROPERTY_TYPE_INVALID: {property_type}")


def _property_type_for_scope(scope: str) -> str:
    if scope == "1":
        return "sheetset"
    if scope == "2":
        return "sheet"
    raise AcsmValidationError(f"CUSTOM_PROPERTY_FLAGS_INVALID: {scope}")


def load_acsm(xml: bytes, *, repair: bool = True) -> "AcsmDocument":
    """统一 DST/XML 加载入口：parse → 契约扫描 → 可选内存修复 → XSD → 语义校验。

    所有工作区、预览、XML 和 CAD 暂存入口都必须经过本函数，禁止直接构造
    `AcsmDocument` 绕过 loader。内存修复不改变 revision（文件 SHA-256 仍是
    基准），读取不产生发布目录或文件时间戳变化。
    """
    return AcsmDocument(xml, repair=repair)


def repair_digest(root: etree._Element, base_revision_id: str) -> str:
    """由修复后 DOM 的 canonical 字节与基准修订组成修复预览摘要。

    修复会为缺失 ID 的对象生成随机 UUID，因此摘要对 `ID` 属性值做掩码
    规范化：摘要与源内容、修复动作绑定，但与随机生成的 ID 值无关，保证
    预览与执行（各自独立重解码）得到同一摘要。执行时必须从正式 DST 重新
    解码、修复并复核该摘要，禁止信任客户端 XML 或普通业务 commands 绕过。
    """
    canonical = etree.tostring(root, method="c14n", with_comments=True)
    masked = _ACSM_ID_ATTR_RE.sub(b'ID="@ID@"', canonical)
    return hashlib.sha256(masked + base_revision_id.encode("utf-8")).hexdigest()


class AcsmDocument:
    """保留未知内容、可修复加载的 AcSm DOM 载体。

    加载流程：parse → 宽容契约扫描 → 可选内存修复 → 严格 XSD → 语义校验。
    修复只发生在深拷贝副本上，不修改源对象或文件；`repair_report` 提供
    可审计报告，真正写回由应用层按报告门禁决定。
    """

    def __init__(self, xml: bytes, *, repair: bool = True):
        parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, no_network=True)
        try:
            self.root = etree.fromstring(xml, parser)
        except etree.XMLSyntaxError as exc:
            raise AcsmValidationError(f"XML_INVALID: {exc}") from exc
        if etree.QName(self.root).localname != "AcSmDatabase":
            raise AcsmValidationError("XML_ROOT_INVALID: 根节点必须为AcSmDatabase")
        repaired_root, report = AcsmRepairer().repair(self.root)
        if repair:
            self.root = repaired_root
            status = report.status
        else:
            # 不应用修复：raw DOM 保留原样；`report.actions` 描述的是本次识别但
            # 未应用的修复记录（DOM 中对应属性/节点仍缺失，`validate()` 会继续
            # 报出契约问题），因此已识别修复的输入一律标记为需确认。
            if report.actions and report.status == "REPAIRED":
                status = "INVALID_REPAIR_REQUIRED"
            else:
                status = report.status
        self._report = RepairReport(status, report.actions, report.blocking_issues)

    @property
    def repair_report(self) -> RepairReport:
        return self._report

    def clone(self) -> "AcsmDocument":
        result = object.__new__(AcsmDocument)
        result.root = copy.deepcopy(self.root)
        result._report = self._report
        return result

    def to_bytes(self) -> bytes:
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8")

    def semantic_bytes(self) -> bytes:
        """使用XML规范化比较DOM语义，不把声明和空元素写法视作差异。"""
        return etree.tostring(self.root, method="c14n", with_comments=True)

    def apply_metadata_commands(self, commands: list[dict]) -> None:
        """只更新已知属性；结构变化必须交给CAD重建任务。"""
        for command in commands:
            command_type = command.get("type")
            if command_type == "update_sheet":
                object_id = command.get("sheet_id")
                matches = self.root.xpath("//*[@ID=$object_id and local-name()='AcSmSheet']", object_id=object_id)
                if len(matches) != 1:
                    raise AcsmValidationError(f"SHEET_NOT_FOUND: {object_id}")
                sheet = matches[0]
                for field, prop_name in (("number", "Number"), ("title", "Title")):
                    if field in command:
                        _set_prop(sheet, prop_name, str(command[field]))
                self._set_custom_properties(sheet, command.get("custom_properties", {}), expected_scope="2")
            elif command_type == "update_sheet_set":
                matches = self.root.xpath("//*[local-name()='AcSmSheetSet']")
                if len(matches) != 1:
                    raise AcsmValidationError("SHEET_SET_INVALID")
                if "name" in command:
                    _set_prop(matches[0], "Name", str(command["name"]))
                self._set_custom_properties(matches[0], command.get("custom_properties", {}), expected_scope="1")
            elif command_type == "update_subset":
                subset_id = str(command.get("subset_id", ""))
                matches = self.root.xpath("//*[@ID=$subset_id and local-name()='AcSmSubset']", subset_id=subset_id)
                if len(matches) != 1:
                    raise AcsmValidationError(f"SUBSET_NOT_FOUND: {subset_id}")
                subset = matches[0]
                if "name" in command:
                    _set_prop(subset, "Name", str(command["name"]))
                if "position" in command:
                    parent = subset.getparent()
                    siblings = _children(parent, "AcSmSubset")
                    position = int(command["position"])
                    if position < 0 or position >= len(siblings):
                        raise AcsmValidationError(f"SUBSET_POSITION_INVALID: {position}")
                    parent.remove(subset)
                    remaining = _children(parent, "AcSmSubset")
                    if position >= len(remaining):
                        remaining[-1].addnext(subset) if remaining else parent.append(subset)
                    else:
                        remaining[position].addprevious(subset)
            else:
                raise AcsmValidationError(f"COMMAND_REQUIRES_CAD: {command_type}")

    def apply_structural_commands(self, commands: list[dict], base_revision: str) -> None:
        """事务式执行受控结构节点工厂，失败时不污染原 DOM。"""
        original_root = copy.deepcopy(self.root)
        try:
            self._apply_structural_commands_in_place(commands, base_revision)
        except Exception:
            self.root = original_root
            raise

    def _apply_structural_commands_in_place(self, commands: list[dict], base_revision: str) -> None:
        """在草稿 DOM 上执行受控结构命令。"""
        from dst_manager.domain.planning import new_acsm_id

        def one(local_name: str, object_id: str) -> etree._Element:
            matches = self.root.xpath("//*[@ID=$object_id and local-name()=$local_name]", object_id=object_id, local_name=local_name)
            if len(matches) != 1:
                raise AcsmValidationError(f"{local_name.upper()}_NOT_FOUND: {object_id}")
            return matches[0]

        for command_index, command in enumerate(commands):
            kind = command.get("type")
            if kind == "update_sheet":
                if "title" in command:
                    raise AcsmValidationError("COMMAND_UNSUPPORTED: update_sheet.title")
                node = one("AcSmSheet", str(command.get("sheet_id", "")))
                if "number" in command:
                    _set_prop(node, "Number", str(command["number"]))
                self._set_custom_properties(node, command.get("custom_properties", {}), expected_scope="2")
            elif kind == "update_sheet_set":
                self.apply_metadata_commands([command])
            elif kind == "update_subset_title":
                subset = one("AcSmSubset", str(command.get("subset_id", "")))
                _set_prop(subset, "Name", str(command.get("title", "")))
            elif kind == "update_subset":
                if "position" in command:
                    raise AcsmValidationError("COMMAND_UNSUPPORTED: update_subset.position")
                self.apply_metadata_commands([command])
            elif kind == "renumber_sheets":
                subset = one("AcSmSubset", str(command.get("subset_id", "")))
                start, width = int(command.get("start", 1)), int(command.get("width", 4))
                for offset, sheet in enumerate(_children(subset, "AcSmSheet")):
                    _set_prop(sheet, "Number", str(start + offset).zfill(width))
            elif kind == "delete_sheet":
                node = one("AcSmSheet", str(command.get("sheet_id", "")))
                parent = node.getparent()
                self._assert_no_external_id_reference(node)
                parent.remove(node)
                if not _children(parent, "AcSmSheet") and command.get("delete_empty_subset"):
                    self._assert_no_external_id_reference(parent)
                    parent.getparent().remove(parent)
            elif kind in {"move_sheet", "reorder_sheet"}:
                raise AcsmValidationError(f"COMMAND_UNSUPPORTED: {kind}")
            elif kind == "insert_sheet":
                target = one("AcSmSubset", str(command.get("target_subset_id", "")))
                count = self._positive_count(command.get("count", 1), "SHEET_INSERT_COUNT_INVALID")
                position = self._insertion_index(command, len(_children(target, "AcSmSheet")), "SHEET_POSITION_INVALID")
                source = self._layout_source(command)
                template = (_children(target, "AcSmSheet") or self.root.xpath("//*[local-name()='AcSmSheet']") or [None])[0]
                inserted: list[etree._Element] = []
                for offset in range(count):
                    sheet_id = new_acsm_id(base_revision, command_index, f"sheet-{offset}")
                    node = self._make_sheet_node(
                        sheet_id,
                        str(command.get("number", _prop(template, "Number") if template is not None else "")),
                        str(command.get("title", _prop(template, "Title") if template is not None else "")),
                        source["file"],
                        "",
                        source["layout"],
                        "0",
                    )
                    self._set_custom_properties(node, command.get("custom_properties", {}), expected_scope="2")
                    inserted.append(node)
                sheets = _children(target, "AcSmSheet")
                sheets[position:position] = inserted
                self._reconcile_controlled_children(target, "AcSmSheet", sheets)
            elif kind == "insert_subset":
                count = self._positive_count(command.get("initial_sheet_count", 1), "EMPTY_SUBSET")
                sheet_set = self._sheet_set()
                position = self._insertion_index(command, len(_children(sheet_set, "AcSmSubset")), "SUBSET_POSITION_INVALID", allow_empty=True)
                source = self._layout_source(command)
                title = str(command.get("title", "")).strip()
                if not title:
                    raise AcsmValidationError("SHEET_TITLE_EMPTY")
                subset = self._make_subset_node(new_acsm_id(base_revision, command_index, "subset"), title)
                for offset in range(count):
                    subset.append(
                        self._make_sheet_node(
                            new_acsm_id(base_revision, command_index, f"subset-sheet-{offset}"),
                            str(offset + 1),
                            title,
                            source["file"],
                            "",
                            source["layout"],
                            "0",
                        ),
                    )
                subsets = _children(sheet_set, "AcSmSubset")
                subsets.insert(position, subset)
                self._reconcile_controlled_children(sheet_set, "AcSmSubset", subsets)
            else:
                raise AcsmValidationError(f"COMMAND_UNSUPPORTED: {kind}")

    def apply_property_definition_commands(self, commands: list[dict]) -> None:
        """新增或删除图纸集/图纸自定义属性定义和值节点。"""
        for command in commands:
            kind = command.get("type")
            property_type = str(command.get("property_type", ""))
            scope = _scope_for_property_type(property_type)
            name = self._normalize_property_name(command.get("name", ""))
            if kind == "add_custom_property":
                definition = CustomPropertyDefinition(property_type, name, str(command.get("default_value", "")))
                self._add_property_definition(definition, duplicate_ok=False)
            elif kind == "delete_custom_property":
                self._delete_property_definition(scope, name)
            else:
                raise AcsmValidationError(f"COMMAND_UNSUPPORTED: {kind}")

    def apply_derived_document(self, derived: DerivedDocument) -> None:
        """将已经验证的最终结构写入受控 AcSm 节点，不重新计算业务规则。"""
        draft = self.clone()
        draft._apply_derived_document_in_place(derived)
        self.root = draft.root

    def _apply_derived_document_in_place(self, derived: DerivedDocument) -> None:
        sheet_set = self._sheet_set()
        self._assert_unique_derived_ids(derived)
        derived_subset_ids = {subset.acsm_id for subset in derived.subsets}
        desired_subsets: list[etree._Element] = []

        for derived_subset in derived.subsets:
            if not derived_subset.sheets:
                raise AcsmValidationError("EMPTY_SUBSET")
            subset = self._find_by_id("AcSmSubset", derived_subset.acsm_id)
            if subset is None:
                subset = self._make_subset_node(derived_subset.acsm_id, derived_subset.display_name)
            _set_prop(subset, "Name", derived_subset.display_name)
            desired_sheets: list[etree._Element] = []

            for derived_sheet in derived_subset.sheets:
                sheet = self._find_by_id("AcSmSheet", derived_sheet.acsm_id)
                if sheet is None:
                    sheet = self._make_sheet_node(
                        derived_sheet.acsm_id,
                        derived_sheet.number,
                        derived_sheet.title,
                        derived_sheet.layout.file_name,
                        derived_sheet.layout.relative_file_name,
                        derived_sheet.layout.layout_name,
                        derived_sheet.layout.handle or "0",
                    )
                _set_prop(sheet, "Number", derived_sheet.number)
                _set_prop(sheet, "Title", derived_sheet.title)
                layouts = _children(sheet, "AcSmAcDbLayoutReference")
                if len(layouts) != 1:
                    raise AcsmValidationError(f"SHEET_LAYOUT_COUNT: {derived_sheet.acsm_id}")
                if derived_sheet.layout.layout_name:
                    _set_prop(layouts[0], "Name", derived_sheet.layout.layout_name)
                desired_sheets.append(sheet)

            expected_sheet_ids = {sheet.acsm_id for sheet in derived_subset.sheets}
            for sheet in list(_children(subset, "AcSmSheet")):
                if sheet.get("ID") not in expected_sheet_ids:
                    self._assert_no_external_id_reference(sheet)
            self._reconcile_controlled_children(subset, "AcSmSheet", desired_sheets)
            desired_subsets.append(subset)

        for subset in list(_children(sheet_set, "AcSmSubset")):
            if subset.get("ID") not in derived_subset_ids:
                self._assert_no_external_id_reference(subset)
        self._reconcile_controlled_children(sheet_set, "AcSmSubset", desired_subsets)

        for definition in derived.property_diff.added:
            self._add_property_definition(definition, duplicate_ok=True)

        for derived_subset in derived.subsets:
            for derived_sheet in derived_subset.sheets:
                sheet = self._find_by_id("AcSmSheet", derived_sheet.acsm_id)
                if sheet is None:
                    raise AcsmValidationError(f"SHEET_NOT_FOUND: {derived_sheet.acsm_id}")
                self._set_custom_properties(sheet, derived_sheet.custom_properties, expected_scope="2")

    def _sheet_set(self) -> etree._Element:
        matches = self.root.xpath("//*[local-name()='AcSmSheetSet']")
        if len(matches) != 1:
            raise AcsmValidationError("SHEET_SET_INVALID")
        return matches[0]

    def _find_by_id(self, local_name: str, object_id: str) -> etree._Element | None:
        matches = self.root.xpath(
            "//*[@ID=$object_id and local-name()=$local_name]",
            object_id=object_id,
            local_name=local_name,
        )
        if len(matches) > 1:
            raise AcsmValidationError(f"{local_name.upper()}_DUPLICATED: {object_id}")
        return matches[0] if matches else None

    def _unique_acsm_id(self, preferred: str | None = None) -> str:
        used = {node.get("ID") for node in self.root.xpath(".//*[@ID] | self::node()[@ID]")}
        if preferred:
            if preferred.casefold() in {item.casefold() for item in used if item is not None}:
                raise AcsmValidationError(f"DUPLICATE_ACSM_ID: {preferred}")
            return preferred
        while True:
            value = _new_acsm_id()
            if value not in used:
                return value

    def _make_prop(self, name: str, value: str, *, vt: str | None = None) -> etree._Element:
        attributes = {"propname": name}
        if vt is not None:
            attributes["vt"] = vt
        try:
            node = etree.Element(_tag_like(self.root, "AcSmProp"), attributes)
            node.text = _acsm_xml_text(value)
        except (UnicodeError, ValueError) as exc:
            raise AcsmValidationError("XML_TEXT_INVALID") from exc
        return node

    def _make_property_value(
        self,
        definition: CustomPropertyDefinition,
        *,
        default_value: str | None = None,
    ) -> etree._Element:
        scope = _scope_for_property_type(definition.type)
        value = definition.default_value if default_value is None else default_value
        name = _acsm_xml_text(definition.name, "CUSTOM_PROPERTY_NAME_INVALID")
        try:
            node = etree.Element(
                _tag_like(self.root, "AcSmCustomPropertyValue"),
                {"ID": self._unique_acsm_id(), "clsid": CLSID_PROPERTY_VALUE, "propname": name, "vt": "13"},
            )
        except (UnicodeError, ValueError) as exc:
            raise AcsmValidationError("CUSTOM_PROPERTY_NAME_INVALID") from exc
        node.append(self._make_prop("Flags", scope, vt=self._custom_property_prop_vt("Flags", "3")))
        if value:
            node.append(self._make_prop("Value", value, vt=self._custom_property_prop_vt("Value", "8")))
        return node

    def _make_custom_property_bag(self) -> etree._Element:
        return etree.Element(
            _tag_like(self.root, "AcSmCustomPropertyBag"),
            {"ID": self._unique_acsm_id(), "clsid": CLSID_PROPERTY_BAG, "propname": "CustomPropertyBag", "vt": "13"},
        )

    def _make_subset_node(self, subset_id: str, name: str) -> etree._Element:
        node = etree.Element(
            _tag_like(self.root, "AcSmSubset"),
            {"ID": self._unique_acsm_id(subset_id), "clsid": CLSID_SUBSET},
        )
        node.append(self._make_prop("Name", name, vt="8"))
        return node

    def _make_sheet_views(self) -> etree._Element:
        return etree.Element(
            _tag_like(self.root, "AcSmSheetViews"),
            {"ID": self._unique_acsm_id(), "clsid": CLSID_SHEET_VIEWS, "propname": "SheetViews", "vt": "13"},
        )

    def _make_sheet_node(
        self,
        sheet_id: str,
        number: str,
        title: str,
        file_name: str,
        relative_file_name: str,
        layout_name: str,
        handle: str,
    ) -> etree._Element:
        node = etree.Element(
            _tag_like(self.root, "AcSmSheet"),
            {"ID": self._unique_acsm_id(sheet_id), "clsid": CLSID_SHEET},
        )
        bag = self._make_custom_property_bag()
        for definition in self._sheet_property_definitions():
            bag.append(self._make_property_value(definition, default_value=""))
        node.append(bag)

        layout = etree.Element(
            _tag_like(self.root, "AcSmAcDbLayoutReference"),
            {"ID": self._unique_acsm_id(), "clsid": CLSID_LAYOUT_REFERENCE, "propname": "Layout", "vt": "13"},
        )
        relative = relative_file_name
        if not relative and file_name:
            relative = ".\\" + Path(file_name).name
        layout.append(self._make_prop("AcDbHandle", handle or "0", vt="8"))
        layout.append(self._make_prop("FileName", file_name, vt="8"))
        layout.append(self._make_prop("Name", layout_name, vt="8"))
        layout.append(self._make_prop("Relative_FileName", relative, vt="8"))
        node.append(layout)

        node.append(self._make_prop("Number", number, vt="8"))
        node.append(self._make_sheet_views())
        node.append(self._make_prop("Title", title, vt="8"))
        return node

    def _custom_property_prop_vt(self, propname: str, default: str) -> str:
        matches = self.root.xpath(
            "//*[local-name()='AcSmCustomPropertyValue']/*[local-name()='AcSmProp' and @propname=$propname]",
            propname=propname,
        )
        for match in matches:
            value = match.get("vt")
            if value is not None:
                return value
        return default

    def _sheet_property_definitions(self) -> list[CustomPropertyDefinition]:
        definitions: list[CustomPropertyDefinition] = []
        seen: set[str] = set()
        anchor_nodes = self._sheet_set().xpath(
            "./*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue']",
        )
        value_nodes = self.root.xpath(
            "//*[local-name()='AcSmSheet']"
            "/*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue']",
        )
        for node in [*anchor_nodes, *value_nodes]:
            if _custom_property_scope(node) != "2":
                continue
            name = node.get("propname", "")
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            definitions.append(CustomPropertyDefinition("sheet", name, ""))
        return definitions

    def _ensure_custom_property_bag(self, owner: etree._Element) -> etree._Element:
        bags = _children(owner, "AcSmCustomPropertyBag")
        if len(bags) > 1:
            raise AcsmValidationError(f"CUSTOM_PROPERTY_BAG_DUPLICATED: {owner.get('ID', '')}")
        if bags:
            return bags[0]
        bag = self._make_custom_property_bag()
        if etree.QName(owner).localname == "AcSmSheet":
            owner.insert(0, bag)
            return bag
        props = _children(owner, "AcSmProp")
        if props:
            props[-1].addnext(bag)
        else:
            owner.insert(0, bag)
        return bag

    def _owner_has_property(self, owner: etree._Element, scope: str, name: str) -> bool:
        key = name.casefold()
        for node in owner.xpath(
            "./*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue']",
        ):
            if _custom_property_scope(node) == scope and node.get("propname", "").casefold() == key:
                return True
        return False

    def _existing_property_types(self, name: str) -> set[str]:
        key = name.casefold()
        types: set[str] = set()
        for node in self.root.xpath("//*[local-name()='AcSmCustomPropertyValue']"):
            if node.get("propname", "").casefold() == key:
                types.add(_property_type_for_scope(_custom_property_scope(node)))
        return types

    def _property_owners(self, scope: str) -> list[etree._Element]:
        if scope == "1":
            return [self._sheet_set()]
        return [self._sheet_set(), *self.root.xpath("//*[local-name()='AcSmSheet']")]

    def _add_property_definition(self, definition: CustomPropertyDefinition, *, duplicate_ok: bool) -> None:
        try:
            validate_property_value(definition.default_value)
        except EditingError as exc:
            raise AcsmValidationError(exc.code) from exc
        scope = _scope_for_property_type(definition.type)
        existing_types = self._existing_property_types(definition.name)
        if existing_types - {definition.type}:
            raise AcsmValidationError(f"CUSTOM_PROPERTY_TYPE_CONFLICT: {definition.name}")
        if existing_types and not duplicate_ok:
            raise AcsmValidationError(f"CUSTOM_PROPERTY_NAME_DUPLICATE: {definition.name}")
        for owner in self._property_owners(scope):
            if self._owner_has_property(owner, scope, definition.name):
                continue
            owner_default = "" if definition.type == "sheet" and owner is self._sheet_set() else definition.default_value
            self._ensure_custom_property_bag(owner).append(
                self._make_property_value(definition, default_value=owner_default),
            )

    def _delete_property_definition(self, scope: str, name: str) -> None:
        removed = False
        key = name.casefold()
        for owner in self._property_owners(scope):
            for bag in _children(owner, "AcSmCustomPropertyBag"):
                for node in list(_children(bag, "AcSmCustomPropertyValue")):
                    if _custom_property_scope(node) == scope and node.get("propname", "").casefold() == key:
                        bag.remove(node)
                        removed = True
        if not removed:
            raise AcsmValidationError(f"CUSTOM_PROPERTY_NOT_FOUND: {name}")

    @staticmethod
    def _assert_unique_derived_ids(derived: DerivedDocument) -> None:
        seen: set[str] = set()
        for subset in derived.subsets:
            for object_id in [subset.acsm_id, *(sheet.acsm_id for sheet in subset.sheets)]:
                key = object_id.casefold()
                if key in seen:
                    raise AcsmValidationError(f"DUPLICATE_ACSM_ID: {object_id}")
                seen.add(key)

    @staticmethod
    def _reconcile_controlled_children(
        parent: etree._Element,
        local_name: str,
        desired: list[etree._Element],
    ) -> None:
        if len({id(node) for node in desired}) != len(desired):
            raise AcsmValidationError("DUPLICATE_ACSM_ID")
        original = list(parent)
        controlled_positions = [
            index
            for index, child in enumerate(original)
            if etree.QName(child).localname == local_name
        ]
        original_tails = [child.tail for child in original]
        desired_index = 0
        result: list[etree._Element] = []
        result_tails: list[str | None] = []
        result_parent_text = parent.text
        last_controlled = controlled_positions[-1] if controlled_positions else None

        def append_node(node: etree._Element) -> None:
            result.append(node)
            result_tails.append(None)

        def append_boundary_text(value: str | None) -> None:
            nonlocal result_parent_text
            if value is None:
                return
            if result:
                current = result_tails[-1]
                result_tails[-1] = value if current is None else current + value
                return
            result_parent_text = value if result_parent_text is None else result_parent_text + value

        for index, child in enumerate(original):
            if etree.QName(child).localname == local_name:
                if desired_index < len(desired):
                    append_node(desired[desired_index])
                    desired_index += 1
            else:
                append_node(child)
            if index == last_controlled:
                for node in desired[desired_index:]:
                    append_node(node)
                desired_index = len(desired)
            append_boundary_text(original_tails[index])
        if last_controlled is None:
            for node in desired:
                append_node(node)
        try:
            parent.text = result_parent_text
            for node, tail in zip(result, result_tails, strict=True):
                node.tail = tail
            parent[:] = result
        except (UnicodeError, ValueError) as exc:
            raise AcsmValidationError("CONTROLLED_CHILD_RECONCILIATION_FAILED") from exc

    @staticmethod
    def _normalize_property_name(value: object) -> str:
        try:
            return normalize_property_name(str(value))
        except EditingError as exc:
            raise AcsmValidationError(exc.code) from exc

    @staticmethod
    def _positive_count(value: object, code: str) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise AcsmValidationError(f"{code}: {value}") from exc
        if count < 1:
            raise AcsmValidationError(f"{code}: {value}")
        return count

    @staticmethod
    def _layout_source(command: dict) -> dict[str, str]:
        source = command.get("source") or {}
        source_type = str(source.get("type", ""))
        source_file = str(source.get("file", "")).strip()
        source_layout = str(source.get("layout", "")).strip()
        if source_type not in {"existing_snapshot", "template_layout"} or not source_file or not source_layout:
            raise AcsmValidationError("LAYOUT_SOURCE_INVALID")
        return {"type": source_type, "file": source_file, "layout": source_layout}

    @staticmethod
    def _insertion_index(command: dict, length: int, code: str, *, allow_empty: bool = False) -> int:
        if "position" in command:
            position = int(command["position"])
            if position < 0 or position > length:
                raise AcsmValidationError(f"{code}: {position}")
            return position
        ordinal = int(command.get("ordinal", 1 if allow_empty and length == 0 else length))
        if length == 0:
            if allow_empty and ordinal == 1:
                return 0
            raise AcsmValidationError(f"{code}: {ordinal}")
        if ordinal < 1 or ordinal > length:
            raise AcsmValidationError(f"{code}: {ordinal}")
        placement = str(command.get("placement", command.get("direction", "after"))).strip().casefold()
        if placement in {"before", "向前添加", "front"}:
            return ordinal - 1
        if placement in {"after", "向后添加", "back"}:
            return ordinal
        raise AcsmValidationError(f"{code}: {placement}")

    def apply_layout_bindings(self, bindings: dict[str, dict[str, str]], dst_dir: Path) -> None:
        self.apply_layout_references(bindings, dst_dir)
        for sheet_id, binding in bindings.items():
            layout = self._layout_reference_for_sheet(sheet_id)
            _set_prop(layout, "AcDbHandle", binding["handle"])

    def apply_layout_references(self, references: dict[str, dict[str, str]], dst_dir: Path) -> None:
        for sheet_id, reference in references.items():
            layout = self._layout_reference_for_sheet(sheet_id)
            target = Path(reference["file"]).resolve()
            try:
                relative = target.relative_to(dst_dir.resolve())
            except ValueError as exc:
                raise AcsmValidationError(f"DWG_OUTSIDE_WORKSPACE: {target}") from exc
            _set_prop(layout, "FileName", str(target))
            _set_prop(layout, "Relative_FileName", ".\\" + str(relative).replace("/", "\\"))
            _set_prop(layout, "Name", reference["layout"])

    def _layout_reference_for_sheet(self, sheet_id: str) -> etree._Element:
        sheet = self._find_by_id("AcSmSheet", sheet_id)
        if sheet is None:
            raise AcsmValidationError(f"SHEET_NOT_FOUND: {sheet_id}")
        layouts = _children(sheet, "AcSmAcDbLayoutReference")
        if len(layouts) != 1:
            raise AcsmValidationError(f"SHEET_LAYOUT_COUNT: {sheet_id}")
        return layouts[0]

    def apply_subset_names(self, names: dict[str, str]) -> None:
        for subset_id, name in names.items():
            matches = self.root.xpath("//*[@ID=$subset_id and local-name()='AcSmSubset']", subset_id=subset_id)
            if len(matches) != 1:
                raise AcsmValidationError(f"SUBSET_NOT_FOUND: {subset_id}")
            _set_prop(matches[0], "Name", name)

    def _set_custom_properties(self, owner: etree._Element, values: dict, *, expected_scope: str, clear_others: bool = False) -> None:
        """按 AutoCAD 的 Value/Flags 语义更新已有自定义属性定义。"""
        custom_nodes = owner.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']")
        by_key: dict[tuple[str, str], etree._Element] = {}
        scopes_by_name: dict[str, set[str]] = {}
        value_nodes: dict[int, list[etree._Element]] = {}
        for node in custom_nodes:
            name = node.get("propname", "")
            scope = _custom_property_scope(node)
            key = (scope, name)
            if key in by_key:
                raise AcsmValidationError(f"CUSTOM_PROPERTY_DUPLICATED: {name}")
            by_key[key] = node
            scopes_by_name.setdefault(name, set()).add(scope)
            found_values = _custom_property_values(node)
            if len(found_values) > 1:
                raise AcsmValidationError(f"CUSTOM_PROPERTY_VALUE_DUPLICATED: {name}")
            value_nodes[id(node)] = found_values

        if clear_others:
            for (scope, _), node in by_key.items():
                if scope != expected_scope:
                    continue
                for value_node in value_nodes[id(node)]:
                    node.remove(value_node)
                value_nodes[id(node)] = []

        for raw_name, raw_value in values.items():
            name = _acsm_xml_text(raw_name)
            value = _acsm_xml_text(raw_value)
            node = by_key.get((expected_scope, name))
            if node is None:
                if name in scopes_by_name:
                    raise AcsmValidationError(f"CUSTOM_PROPERTY_SCOPE_MISMATCH: {name}")
                raise AcsmValidationError(f"CUSTOM_PROPERTY_NOT_FOUND: {name}")
            current_nodes = value_nodes[id(node)]
            current_value = current_nodes[0].text or "" if current_nodes else ""
            if current_value == value:
                continue
            if not value:
                if current_nodes:
                    node.remove(current_nodes[0])
                    value_nodes[id(node)] = []
                continue
            if current_nodes:
                try:
                    current_nodes[0].text = value
                except (UnicodeError, ValueError) as exc:
                    raise AcsmValidationError("XML_TEXT_INVALID") from exc
                continue
            flags_node = next(child for child in _children(node, "AcSmProp") if child.get("propname") == "Flags")
            value_node = etree.Element(flags_node.tag, {"propname": "Value", "vt": "8"})
            try:
                value_node.text = value
            except (UnicodeError, ValueError) as exc:
                raise AcsmValidationError("XML_TEXT_INVALID") from exc
            value_node.tail = flags_node.tail
            flags_node.addnext(value_node)
            value_nodes[id(node)] = [value_node]

    def _custom_property_issues(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for owner in self.root.xpath("//*[local-name()='AcSmCustomPropertyBag']/.."):
            seen: set[tuple[str, str]] = set()
            for node in owner.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
                name = node.get("propname", "")
                try:
                    scope = _custom_property_scope(node)
                except AcsmValidationError as exc:
                    code = str(exc).split(":", 1)[0]
                    issues.append(ValidationIssue(code, Severity.ERROR, f"自定义属性“{name}”的 Flags 无效", owner.get("ID")))
                    continue
                key = (scope, name)
                if key in seen:
                    issues.append(ValidationIssue("CUSTOM_PROPERTY_DUPLICATED", Severity.ERROR, f"自定义属性“{name}”重复", owner.get("ID")))
                seen.add(key)
                if len(_custom_property_values(node)) > 1:
                    issues.append(ValidationIssue("CUSTOM_PROPERTY_VALUE_DUPLICATED", Severity.ERROR, f"自定义属性“{name}”存在多个 Value", owner.get("ID")))
        return issues

    def _assert_no_external_id_reference(self, owned: etree._Element) -> None:
        owned_ids = {node.get("ID") for node in owned.xpath(".//*[@ID] | self::*[@ID]") if node.get("ID")}
        if not owned_ids:
            return
        for node in self.root.iter():
            if node is owned or owned in node.iterancestors() or node in owned.iterdescendants():
                continue
            values = list(node.attrib.values()) + ([node.text] if node.text else [])
            if any(object_id in value for object_id in owned_ids for value in values):
                raise AcsmValidationError(f"UNKNOWN_REFERENCE_BLOCKED: {node.get('ID', etree.QName(node).localname)}")

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = self._custom_property_issues()
        # 契约层：必需属性、固定值、AcSmProp vt 与父级包含关系
        issues.extend(validate_contract(self.root))
        # 严格后置 XSD 结构边界
        issues.extend(validate_schema(self.root))
        seen: set[str] = set()
        sheet_sets = self.root.xpath("//*[local-name()='AcSmSheetSet']")
        if not sheet_sets:
            issues.append(ValidationIssue("SHEET_SET_MISSING", Severity.ERROR, "缺少AcSmSheetSet节点"))
        if not _prop(self.root, "DbVersion"):
            issues.append(ValidationIssue("DATABASE_VERSION_MISSING", Severity.ERROR, "缺少AcSm数据库版本"))
        for node in self.root.iter():
            object_id = node.get("ID")
            if not object_id:
                continue
            key = object_id.casefold()
            if key in seen:
                issues.append(ValidationIssue("DUPLICATE_ACSM_ID", Severity.ERROR, "AcSm ID重复", object_id))
            seen.add(key)
            if not _ID_RE.fullmatch(object_id):
                issues.append(ValidationIssue("INVALID_ACSM_ID", Severity.ERROR, "AcSm ID格式无效", object_id))
        for node in self.root.xpath("//*[local-name()='AcSmSheet']"):
            layouts = _children(node, "AcSmAcDbLayoutReference")
            if len(layouts) != 1:
                issues.append(ValidationIssue("SHEET_LAYOUT_COUNT", Severity.ERROR, "图纸必须恰好有一个布局引用", node.get("ID")))
                continue
            layout = layouts[0]
            required = ("FileName", "Relative_FileName", "Name", "AcDbHandle")
            for name in required:
                if not _prop(layout, name):
                    issues.append(ValidationIssue("LAYOUT_FIELD_MISSING", Severity.ERROR, f"布局缺少{name}", node.get("ID")))
            handle = _prop(layout, "AcDbHandle")
            if handle == "0":
                issues.append(ValidationIssue("LAYOUT_HANDLE_PLACEHOLDER", Severity.ERROR, "布局Handle仍为CAD回写前占位值", node.get("ID")))
            elif handle and not _HANDLE_RE.fullmatch(handle):
                issues.append(ValidationIssue("LAYOUT_HANDLE_INVALID", Severity.ERROR, "布局Handle无效", node.get("ID")))
            if not _prop(node, "Number") or not _prop(node, "Title"):
                issues.append(ValidationIssue("SHEET_FIELD_MISSING", Severity.ERROR, "图纸缺少Number或Title", node.get("ID")))
        return issues

    def project(self, dst_dir: Path, root_override: Path | None = None) -> SheetSetDocument:
        sheet_set_nodes = self.root.xpath("//*[local-name()='AcSmSheetSet']")
        if not sheet_set_nodes:
            raise AcsmValidationError("SHEET_SET_MISSING")
        sheet_set = sheet_set_nodes[0]
        sheet_definition_names: dict[str, str] = {}
        for value in sheet_set.xpath(
            "./*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue']",
        ):
            try:
                if _custom_property_scope(value) == "2":
                    name = value.get("propname", "")
                    sheet_definition_names.setdefault(name.casefold(), name)
            except AcsmValidationError:
                continue
        subsets: list[Subset] = []
        for order, subset_node in enumerate(self.root.xpath("//*[local-name()='AcSmSubset']")):
            subset = Subset(subset_node.get("ID", ""), _prop(subset_node, "Name"), order)
            # 只收集此子集直接拥有的图纸，避免嵌套子集重复投影。
            for sheet_node in _children(subset_node, "AcSmSheet"):
                layout_nodes = _children(sheet_node, "AcSmAcDbLayoutReference")
                if not layout_nodes:
                    continue
                layout_node = layout_nodes[0]
                layout = LayoutReference(
                    _prop(layout_node, "FileName"),
                    _prop(layout_node, "Relative_FileName"),
                    _prop(layout_node, "Name"),
                    _prop(layout_node, "AcDbHandle"),
                )
                custom: dict[str, str] = {}
                for value in sheet_node.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
                    try:
                        if _custom_property_scope(value) == "2":
                            name = value.get("propname", "")
                            custom[name] = _prop(value, "Value")
                            sheet_definition_names.setdefault(name.casefold(), name)
                    except AcsmValidationError:
                        continue
                subset.sheets.append(Sheet(sheet_node.get("ID", ""), _prop(sheet_node, "Number"), _prop(sheet_node, "Title"), layout, custom))
            subsets.append(subset)
        sheet_set_custom: dict[str, str] = {}
        for value in sheet_set.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
            try:
                if _custom_property_scope(value) == "1":
                    sheet_set_custom[value.get("propname", "")] = _prop(value, "Value")
            except AcsmValidationError:
                continue
        document = SheetSetDocument(
            self.root.get("ID", ""),
            _prop(sheet_set, "Name"),
            subsets,
            sheet_set_custom,
            self.validate(),
            list(sheet_definition_names.values()),
            self._report,
        )
        self.resolve_paths(document, dst_dir, root_override)
        return document

    @staticmethod
    def resolve_paths(document: SheetSetDocument, dst_dir: Path, root_override: Path | None = None) -> None:
        for sheet in document.sheets:
            reference = sheet.layout
            relative_text = reference.relative_file_name.replace("\\", "/").removeprefix("./")
            candidates = [
                (dst_dir / relative_text, "relative"),
                (Path(reference.file_name), "absolute"),
                (dst_dir / Path(reference.file_name.replace("\\", "/")).name, "basename"),
            ]
            if root_override is not None:
                candidates.append((root_override.resolve() / Path(reference.file_name.replace("\\", "/")).name, "root_override"))
            for candidate, source in candidates:
                if candidate.is_file():
                    reference.resolved_path = candidate.resolve()
                    reference.resolution_source = source
                    break
            if reference.resolved_path is None:
                document.diagnostics.append(ValidationIssue("DWG_PATH_NOT_FOUND", Severity.ERROR, "找不到布局引用的DWG", sheet.acsm_id, reference.file_name))
