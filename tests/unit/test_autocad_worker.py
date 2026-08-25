import json
from pathlib import Path

import pytest

from dst_manager.infrastructure.autocad.worker import (
    ScriptRenderer,
    parse_rename_result,
    rename_request_path,
    rename_result_path,
    write_rename_request,
)


def test_render_rename_uses_only_fixed_safe_commands_without_request_path_input():
    plugin = Path("C:/plugins/AutoCAD Worker/DstManager.AutoCAD.dll")
    request = Path("C:/临时工作区/" + "很长的目录名/" * 30 + "改名请求.json")
    script = ScriptRenderer().render_rename(plugin, request)

    assert script.splitlines() == [
        "FILEDIA",
        "0",
        "SECURELOAD",
        "0",
        "CMDECHO",
        "0",
        "_.NETLOAD",
        f'"{plugin}"',
        "DstRenameLayouts",
        "CMDECHO",
        "1",
        "FILEDIA",
        "1",
        "SECURELOAD",
        "1",
        "_.QSAVE",
        "_.QUIT",
    ]
    for forbidden in ("DstDeleteLayouts", "DstGetLayoutHandles", "_.-LAYOUT", "_Template"):
        assert forbidden not in script


def test_render_rename_restores_secureload_before_save_and_quit():
    lines = ScriptRenderer().render_rename(
        Path("C:/plugins/AutoCAD Worker/DstManager.AutoCAD.dll"),
        Path("C:/staging/001 rename request.json"),
    ).splitlines()

    secureload_indexes = [index for index, line in enumerate(lines) if line == "SECURELOAD"]
    assert len(secureload_indexes) == 2
    restored_index = secureload_indexes[-1]
    assert lines[restored_index + 1] == "1"
    assert restored_index < lines.index("_.QSAVE") < lines.index("_.QUIT")


def test_render_rename_rejects_control_characters_in_plugin_path():
    plugin = Path("C:/plugins/AutoCAD\nWorker/DstManager.AutoCAD.dll")

    with pytest.raises(ValueError, match="SCR_ARGUMENT_UNSAFE"):
        ScriptRenderer().render_rename(plugin, Path("C:/staging/request.json"))


def test_rename_sidecars_use_fixed_names_and_strict_result(tmp_path: Path):
    drawing = tmp_path / "001 第一册.dwg"

    request = write_rename_request(
        drawing,
        [{"original_layout": "001 第一册", "target_layout": "002 第一册"}],
    )

    assert request == drawing.with_suffix(".dst-layout-rename-request.json")
    assert rename_request_path(drawing) == request
    assert rename_result_path(drawing) == drawing.with_suffix(".dst-layout-rename-result.json")
    assert json.loads(request.read_text(encoding="utf-8")) == {
        "version": 1,
        "layouts": [{"old_name": "001 第一册", "new_name": "002 第一册"}],
    }
    assert parse_rename_result(
        '{"version":1,"renamed_count":1,"final_layouts":["002 第一册"]}',
        {"002 第一册"},
    ) == 1


@pytest.mark.parametrize(
    "layouts",
    [
        [],
        [{"target_layout": "新名称"}],
        [{"original_layout": "", "target_layout": "新名称"}],
        [{"original_layout": "旧名称", "target_layout": ""}],
        [
            {"original_layout": "OldName", "target_layout": "新名称 1"},
            {"original_layout": "oldname", "target_layout": "新名称 2"},
        ],
        [
            {"original_layout": "旧名称 1", "target_layout": "NewName"},
            {"original_layout": "旧名称 2", "target_layout": "newname"},
        ],
        [
            {"original_layout": "旧名称", "target_layout": "新名称 1"},
            {"original_layout": "旧名称 2", "target_layout": "新名称 1"},
        ],
    ],
)
def test_write_rename_request_rejects_invalid_names(tmp_path: Path, layouts: list[dict[str, str]]):
    with pytest.raises(ValueError, match="LAYOUT_RENAME_REQUEST_INVALID"):
        write_rename_request(tmp_path / "drawing.dwg", layouts)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "renamed_count": 1, "final_layouts": ["新名称"]},
        {"version": True, "renamed_count": 1, "final_layouts": ["新名称"]},
        {"version": 1, "renamed_count": True, "final_layouts": ["新名称"]},
        {"version": 1, "renamed_count": -1, "final_layouts": ["新名称"]},
        {"version": 1, "renamed_count": "1", "final_layouts": ["新名称"]},
        {"version": 1, "renamed_count": 1, "final_layouts": ["新名称", "新名称"]},
        {"version": 1, "renamed_count": 1, "final_layouts": ["NewName", "newname"]},
        {"version": 1, "renamed_count": 1, "final_layouts": ["新名称", "额外名称"]},
        {"version": 1, "renamed_count": 1, "final_layouts": []},
        {"version": 1, "renamed_count": 1},
    ],
)
def test_parse_rename_result_rejects_invalid_payloads(payload: dict[str, object]):
    with pytest.raises(ValueError, match="LAYOUT_RENAME_RESULT_INVALID"):
        parse_rename_result(json.dumps(payload, ensure_ascii=False), {"新名称"})


@pytest.mark.parametrize(
    "text",
    [
        "不是 JSON",
        "[]",
        '{"version":1,"renamed_count":1,"final_layouts":["新名称"],"extra":true}',
        '{"version":1,"renamed_count":1,"final_layouts":"新名称"}',
        '{"version":1,"renamed_count":1,"final_layouts":[""]}',
        '{"version":1,"renamed_count":1,"final_layouts":[1]}',
    ],
)
def test_parse_rename_result_rejects_invalid_json_shapes(text: str):
    with pytest.raises(ValueError, match="LAYOUT_RENAME_RESULT_INVALID"):
        parse_rename_result(text, {"新名称"})


def test_render_rebuild_contains_handle_read_in_the_same_script():
    script = ScriptRenderer().render_rebuild(
        Path("C:/plugins/DstManager.AutoCAD.dll"),
        [
            {
                "source_file": "C:/sources/template.dwg",
                "source_layout": "A3",
                "target_layout": "001-A",
            },
            {
                "source_file": "C:/sources/template.dwg",
                "source_layout": "A4",
                "target_layout": "002-B",
            },
        ],
    )

    lines = script.splitlines()
    handles_index = lines.index("DstGetLayoutHandles")
    rename_indexes = [
        index
        for index in range(len(lines) - 1)
        if lines[index : index + 2] == ["_.-LAYOUT", "_Rename"]
    ]

    assert script.count("_.NETLOAD") == 1
    assert script.count("DstGetLayoutHandles") == 1
    assert script.count("_.QSAVE") == 1
    assert script.count("_.QUIT") == 1
    assert lines.index("DstDeleteDefaultLayout") < handles_index
    assert [(lines[index + 2], lines[index + 3]) for index in rename_indexes] == [
        ("A3", "DST_TMP_0000"),
        ("A4", "DST_TMP_0001"),
        ("DST_TMP_0000", "001-A"),
        ("DST_TMP_0001", "002-B"),
    ]
    assert all(index < handles_index for index in rename_indexes)
    assert handles_index < lines.index("_.QSAVE") < lines.index("_.QUIT")


def test_render_handles_remains_a_standalone_handle_script():
    script = ScriptRenderer().render_handles(Path("C:/plugins/DstManager.AutoCAD.dll"))

    assert "DstGetLayoutHandles" in script
    for structural_command in ("DstDeleteLayouts", "_.-LAYOUT", "_Rename", "DstDeleteDefaultLayout"):
        assert structural_command not in script
