"""固定结构 SCR 生成器测试（SPEC-DB-001 §7）。

SCR 只允许固定命令 + 插件 DLL 路径 + 请求 JSON 路径占位；用户文本（布局名、
工程名等）没有任何进入 SCR 的通道。路径参数含控制字符或引号时拒绝渲染。
"""

from __future__ import annotations

import pytest

from dst_builder.domain.models import WORKER_COMMAND_NAME
from dst_builder.infrastructure.autocad.script import render_worker_scr

PLUGIN = r"C:\cad\DstBuilder.AutoCAD.dll"
REQUEST_JSON = r"C:\project\.builds\attempt-1\cad-drawing-request.json"


def test_scr_is_fixed_structure_with_path_placeholders() -> None:
    scr = render_worker_scr(PLUGIN, REQUEST_JSON)
    lines = scr.splitlines()

    assert lines == [
        "FILEDIA",
        "0",
        "SECURELOAD",
        "0",
        "CMDECHO",
        "0",
        "_.NETLOAD",
        f'"{PLUGIN}"',
        WORKER_COMMAND_NAME,
        f'"{REQUEST_JSON}"',
        "_.QSAVE",
        "_.QUIT",
    ]
    assert WORKER_COMMAND_NAME == "DSTBUILDER_CREATE_DRAWING"
    assert scr.endswith("\n")


def test_scr_does_not_expose_user_text_channel() -> None:
    """布局名等用户文本没有参数位：SCR 中除两条路径外不允许其他可变内容。"""
    scr = render_worker_scr(PLUGIN, REQUEST_JSON)

    user_texts = ["平面", "001 平面", "施工图", "-LAYOUT", "-INSERT", "-RENAME"]
    for text in user_texts:
        assert text not in scr


def test_scr_rejects_unsafe_path_argument() -> None:
    for bad in (r'C:\ev"il\a.dll', "C:/evil\ndll", "C:/evil\r.dll", "C:/evil\t.dll", ""):
        with pytest.raises(ValueError):
            render_worker_scr(bad, REQUEST_JSON)
        with pytest.raises(ValueError):
            render_worker_scr(PLUGIN, bad)


def test_scr_rejects_path_with_control_character() -> None:
    with pytest.raises(ValueError):
        render_worker_scr(PLUGIN, "C:/a\x00b.json")
