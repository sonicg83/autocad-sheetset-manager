from pathlib import Path

import pytest

from dst_manager.infrastructure.dst_codec import DstCodec


@pytest.fixture
def tiny_workspace(tmp_path:Path):
    # 契约合规的最小工作区文档：已知对象带固定 clsid/propname/vt，Sheet 含
    # bag/layout/Number/Title/AcSmSheetViews，另保留一个 Unknown 扩展节点。
    ids=[f"g00000000-0000-0000-0000-{i:012X}" for i in range(1,11)]
    xml=f'''<AcSmDatabase ID="{ids[0]}" clsid="g2162C6B6-0CE4-40E8-912B-46F59DFDF826"><AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp><AcSmSheetSet ID="{ids[1]}" clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13"><AcSmProp propname="Name" vt="8">测试集</AcSmProp><AcSmSubset ID="{ids[2]}" clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322"><AcSmProp propname="Name" vt="8">分组</AcSmProp><AcSmSheet ID="{ids[3]}" clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"><AcSmCustomPropertyBag ID="{ids[4]}" clsid="g4D103908-8C86-4D95-BBF4-68B9A7B00731" propname="CustomPropertyBag" vt="13"><AcSmCustomPropertyValue ID="{ids[5]}" clsid="g8D22A2A4-1777-4D78-84CC-69EF741FE954" propname="比例" vt="13"><AcSmProp propname="Flags" vt="3">2</AcSmProp><AcSmProp propname="Value" vt="8">1:100</AcSmProp></AcSmCustomPropertyValue></AcSmCustomPropertyBag><AcSmAcDbLayoutReference ID="{ids[8]}" clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13"><AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp><AcSmProp propname="FileName" vt="8">C:\\old\\A.dwg</AcSmProp><AcSmProp propname="Name" vt="8">001 平面</AcSmProp><AcSmProp propname="Relative_FileName" vt="8">.\\A.dwg</AcSmProp></AcSmAcDbLayoutReference><AcSmProp propname="Number" vt="8">001</AcSmProp><AcSmSheetViews ID="{ids[9]}" clsid="gF40F931B-64BC-4B90-9FC8-A11A77D6815B" propname="SheetViews" vt="13"/><AcSmProp propname="Title" vt="8">平面</AcSmProp><Unknown keep="yes"/></AcSmSheet></AcSmSubset></AcSmSheetSet></AcSmDatabase>'''.encode()
    marker=b'<AcSmProp propname="Name" vt="8">\xe6\xb5\x8b\xe8\xaf\x95\xe9\x9b\x86</AcSmProp>'
    sheet_set_custom=f'<AcSmCustomPropertyBag ID="{ids[6]}" clsid="g4D103908-8C86-4D95-BBF4-68B9A7B00731" propname="CustomPropertyBag" vt="13"><AcSmCustomPropertyValue ID="{ids[7]}" clsid="g8D22A2A4-1777-4D78-84CC-69EF741FE954" propname="项目号" vt="13"><AcSmProp propname="Flags" vt="3">1</AcSmProp><AcSmProp propname="Value" vt="8">P-000</AcSmProp></AcSmCustomPropertyValue></AcSmCustomPropertyBag>'.encode()
    xml=xml.replace(marker,marker+sheet_set_custom,1)
    (tmp_path/"A.dwg").write_bytes(b"fake"); dst=tmp_path/"test.dst"; DstCodec().encode_file(xml,dst); return dst,ids[3]