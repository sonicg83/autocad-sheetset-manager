"""任务 1 权威结构投影契约（先行门禁）。

用最小临时 DST 夹具通过既有 `preview_changes` 预览路径（无 CAD）验证
`execution_intent.derived_document` 的结构投影契约：新增/删除/改名的派生
ID、数量、属性、顺序均来自服务端权威响应，且相同命令重复请求结果一致。
该契约是前端 `applyDerivedProjection` 的数据门禁——浏览器不得重新派生结构。
"""

from pathlib import Path

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.dst_codec import DstCodec


def _next_id(counter: list[int]) -> str:
    counter[0] += 1
    return f"g00000000-0000-0000-0000-{counter[0]:012X}"


def _build_dst(tmp_path: Path, titles: list[tuple[str, str]]) -> Path:
    """构造最小契约合规 DST：单个子集，每张图纸的布局文件为真实存在的虚构 DWG。"""
    counter: list[int] = [0]
    sheets_xml: list[str] = []
    for number, title in titles:
        dwg = tmp_path / f"{number} 平面图.dwg"
        dwg.write_bytes(b"fake")
        sheet_id = _next_id(counter)
        property_bag_id = _next_id(counter)
        property_value_id = _next_id(counter)
        layout_id = _next_id(counter)
        views_id = _next_id(counter)
        sheets_xml.append(
            f'<AcSmSheet ID="{sheet_id}" clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
            f'<AcSmCustomPropertyBag ID="{property_bag_id}" clsid="g4D103908-8C86-4D95-BBF4-68B9A7B00731" propname="CustomPropertyBag" vt="13">'
            f'<AcSmCustomPropertyValue ID="{property_value_id}" clsid="g8D22A2A4-1777-4D78-84CC-69EF741FE954" propname="比例" vt="13">'
            f'<AcSmProp propname="Flags" vt="3">2</AcSmProp><AcSmProp propname="Value" vt="8">1:100</AcSmProp>'
            f"</AcSmCustomPropertyValue></AcSmCustomPropertyBag>"
            f'<AcSmAcDbLayoutReference ID="{layout_id}" clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13">'
            f'<AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp>'
            f'<AcSmProp propname="FileName" vt="8">{dwg}</AcSmProp>'
            f'<AcSmProp propname="Name" vt="8">{number} {title}</AcSmProp>'
            f'<AcSmProp propname="Relative_FileName" vt="8">.\\{dwg.name}</AcSmProp>'
            f"</AcSmAcDbLayoutReference>"
            f'<AcSmProp propname="Number" vt="8">{number}</AcSmProp>'
            f'<AcSmSheetViews ID="{views_id}" clsid="gF40F931B-64BC-4B90-9FC8-A11A77D6815B" propname="SheetViews" vt="13"/>'
            f'<AcSmProp propname="Title" vt="8">{title}</AcSmProp>'
            "</AcSmSheet>",
        )
    subset_id = _next_id(counter)
    sheet_set_id = _next_id(counter)
    database_id = _next_id(counter)
    first, last = titles[0][0], titles[-1][0]
    subset_name = f"{first}-{last} 平面图"
    xml = (
        f'<AcSmDatabase ID="{database_id}" clsid="g2162C6B6-0CE4-40E8-912B-46F59DFDF826">'
        f'<AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>'
        f'<AcSmSheetSet ID="{sheet_set_id}" clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
        f'<AcSmProp propname="Name" vt="8">测试图纸集</AcSmProp>'
        f'<AcSmSubset ID="{subset_id}" clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
        f'<AcSmProp propname="Name" vt="8">{subset_name}</AcSmProp>'
        + "".join(sheets_xml)
        + "</AcSmSubset></AcSmSheetSet></AcSmDatabase>"
    )
    dst = tmp_path / "图纸集.dst"
    DstCodec().encode_file(xml.encode("utf-8"), dst)
    return dst


def _open(tmp_path: Path, titles: list[tuple[str, str]]):
    dst = _build_dst(tmp_path, titles)
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    return service, workspace, dst


def _preview(service, workspace, commands):
    return service.preview_changes(workspace.id, workspace.revision_id, commands, "2020")


def _insert_sheet_command(workspace, template: Path, *, ordinal: int, placement: str = "after"):
    return {
        "type": "insert_sheet",
        "target_subset_id": workspace.document.subsets[0].acsm_id,
        "ordinal": ordinal,
        "placement": placement,
        "count": 1,
        "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
    }


def test_insert_then_property_edit_keeps_stable_id_and_derived_values(tmp_path):
    """insert→属性编辑：新增 ID 稳定，图号/派生标题/布局/属性/Handle 全部取响应，不填造真实 Handle 或 resolved_path。"""
    service, workspace, _ = _open(tmp_path, [("001", "平面图"), ("002", "平面图")])
    template = tmp_path / "标准模板.dwg"
    template.write_bytes(b"fake")
    existing_ids = {sheet.acsm_id for sheet in workspace.document.subsets[0].sheets}
    insert = _insert_sheet_command(workspace, template, ordinal=2)

    first = _preview(service, workspace, [insert])
    assert first["executable"] is True
    sheets = first["execution_intent"]["derived_document"]["subsets"][0]["sheets"]
    assert [sheet["number"] for sheet in sheets] == ["001", "002", "003"]
    new_sheet = sheets[2]
    assert new_sheet["acsm_id"] not in existing_ids and new_sheet["acsm_id"].startswith("g")
    assert new_sheet["title"] == "平面图 (三)"
    assert new_sheet["layout"]["layout_name"] == "003 平面图 (三)"
    assert new_sheet["layout"]["handle"] == ""  # 不填造真实 Handle
    assert new_sheet["layout"]["resolved_path"] is None  # 不填造 resolved_path
    assert new_sheet["custom_properties"] == {}
    assert sheets[0]["custom_properties"] == {"比例": "1:100"}  # 既有属性取自响应基准

    # 同一新增 + 对既有图纸属性编辑（新命令排在新增之后，命令索引不前移）→ 新增 ID 稳定
    existing = workspace.document.subsets[0].sheets[0].acsm_id
    second = _preview(
        service,
        workspace,
        [insert, {"type": "update_sheet_properties", "sheet_id": existing, "custom_properties": {"比例": "1:50"}}],
    )
    assert second["executable"] is True
    assert second["execution_intent"]["derived_document"]["subsets"][0]["sheets"][2]["acsm_id"] == new_sheet["acsm_id"]
    assert second["execution_intent"]["derived_document"]["subsets"][0]["sheets"][0]["custom_properties"] == {"比例": "1:100"}


def test_insert_then_insert_yields_distinct_ordered_ids_and_repeatable(tmp_path):
    """insert→insert：两个新增 ID 互不相同、顺序保持、数量正确；相同命令重复预览结果一致（确定性投影）。"""
    service, workspace, _ = _open(tmp_path, [("001", "平面图"), ("002", "平面图")])
    template = tmp_path / "标准模板.dwg"
    template.write_bytes(b"fake")
    base_ids = [sheet.acsm_id for sheet in workspace.document.subsets[0].sheets]
    commands = [
        _insert_sheet_command(workspace, template, ordinal=2),
        _insert_sheet_command(workspace, template, ordinal=3),
    ]

    preview = _preview(service, workspace, commands)
    assert preview["executable"] is True
    derived = preview["execution_intent"]["derived_document"]
    sheets = derived["subsets"][0]["sheets"]
    assert len(sheets) == 4
    assert [sheet["acsm_id"] for sheet in sheets[:2]] == base_ids  # 既有对象身份保持
    new_ids = [sheet["acsm_id"] for sheet in sheets[2:]]
    assert len(new_ids) == len(set(new_ids)) and all(identifier not in base_ids for identifier in new_ids)
    assert [sheet["number"] for sheet in sheets] == ["001", "002", "003", "004"]
    assert [sheet["title"] for sheet in sheets] == ["平面图 (一)", "平面图 (二)", "平面图 (三)", "平面图 (四)"]
    assert derived["subsets"][0]["number_range"] == "001-004"

    again = _preview(service, workspace, commands)
    assert again["execution_intent"]["derived_document"] == derived  # 重复请求一致


def test_delete_then_undo_restores_base_without_mutation(tmp_path):
    """delete→undo：删除后结构投影移除图纸并重派生；空命令撤销后服务端不持久化预览，重开仍为基底。"""
    service, workspace, dst = _open(tmp_path, [("001", "平面图"), ("002", "平面图"), ("003", "平面图")])
    subset = workspace.document.subsets[0]
    base_ids = [sheet.acsm_id for sheet in subset.sheets]

    deleted = _preview(service, workspace, [{"type": "delete_sheet", "sheet_id": base_ids[1]}])
    assert deleted["executable"] is True
    sheets = deleted["execution_intent"]["derived_document"]["subsets"][0]["sheets"]
    assert [sheet["acsm_id"] for sheet in sheets] == [base_ids[0], base_ids[2]]
    assert [sheet["number"] for sheet in sheets] == ["001", "002"]
    assert [sheet["title"] for sheet in sheets] == ["平面图 (一)", "平面图 (二)"]

    undone = _preview(service, workspace, [])
    assert undone["executable"] is True and undone["execution_intent"] is None

    reloaded = service.open_workspace(dst)
    assert [sheet.acsm_id for sheet in reloaded.document.subsets[0].sheets] == base_ids


def test_rename_then_insert_id_is_index_sensitive(tmp_path):
    """rename→insert：改名与新增同批时，新增 ID 由命令索引决定——前端不得跨结构边界压缩/重排命令。"""
    service, workspace, _ = _open(tmp_path, [("001", "平面图"), ("002", "平面图")])
    template = tmp_path / "标准模板.dwg"
    template.write_bytes(b"fake")
    subset_id = workspace.document.subsets[0].acsm_id
    insert = _insert_sheet_command(workspace, template, ordinal=2)
    rename = {"type": "update_subset_title", "subset_id": subset_id, "title": "总平面图"}

    rename_first = _preview(service, workspace, [rename, insert])
    insert_first = _preview(service, workspace, [insert, rename])
    derived_a = rename_first["execution_intent"]["derived_document"]
    derived_b = insert_first["execution_intent"]["derived_document"]

    assert derived_a["subsets"][0]["display_name"] == "001-003 总平面图"
    assert derived_b["subsets"][0]["display_name"] == "001-003 总平面图"
    assert derived_a["subsets"][0]["sheets"][2]["acsm_id"] != derived_b["subsets"][0]["sheets"][2]["acsm_id"]
