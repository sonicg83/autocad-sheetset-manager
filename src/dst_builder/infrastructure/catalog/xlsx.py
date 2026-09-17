"""图纸目录 XLSX 生成与读取（SPEC-DB-001 §8）：伴随成果，不是项目事实源。

固定工作表 ``图纸目录``、第一行 ``图号/图名/DWG/布局``、第二行唯一数据行；
图号一律以字符串单元格写入以保留前导零。确定性：workbook 元数据时间戳固定
为 1980-01-01，保存后统一重写 zip 条目时间戳/属性，同输入两次生成字节完全
一致（无时间戳/随机值渗入）。
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook

__all__ = [
    "SHEET_CATALOG_HEADERS",
    "SHEET_CATALOG_SHEET_NAME",
    "build_sheet_catalog_xlsx",
    "load_sheet_catalog",
]

SHEET_CATALOG_SHEET_NAME = "图纸目录"
SHEET_CATALOG_HEADERS = ("图号", "图名", "DWG", "布局")

_FIXED_METADATA_TIME = datetime(1980, 1, 1, 0, 0, 0, tzinfo=UTC)
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def build_sheet_catalog_xlsx(*, number: str, title: str, dwg: str, layout: str) -> bytes:
    """生成图纸目录 XLSX 字节（纯函数，同输入字节级一致）。"""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_CATALOG_SHEET_NAME
    worksheet.append(list(SHEET_CATALOG_HEADERS))
    worksheet.append([number, title, dwg, layout])

    properties = workbook.properties
    properties.creator = "dst-builder"
    properties.lastModifiedBy = "dst-builder"
    properties.created = _FIXED_METADATA_TIME
    properties.modified = _FIXED_METADATA_TIME

    buffer = BytesIO()
    workbook.save(buffer)
    return _normalize_zip(buffer.getvalue())


def load_sheet_catalog(data: bytes) -> list[list[str | None]]:
    """读回工作表全部单元格值（含表头）；工作表缺失时抛 :class:`KeyError`。"""
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        worksheet = workbook[SHEET_CATALOG_SHEET_NAME]
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _normalize_zip(data: bytes) -> bytes:
    """以固定时间戳与固定条目属性重写 zip，消除平台时间渗入。"""
    with zipfile.ZipFile(BytesIO(data)) as source:
        entries = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in entries:
            info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            target.writestr(info, payload)
    return buffer.getvalue()
