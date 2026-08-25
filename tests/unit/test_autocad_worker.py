from pathlib import Path

from dst_manager.infrastructure.autocad.worker import ScriptRenderer


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
