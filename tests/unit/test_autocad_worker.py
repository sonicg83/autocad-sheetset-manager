from pathlib import Path

from dst_manager.infrastructure.autocad.worker import ScriptRenderer


def test_render_rebuild_contains_handle_read_in_the_same_script():
    script = ScriptRenderer().render_rebuild(
        Path("C:/plugins/DstManager.AutoCAD.dll"),
        [
            {
                "source_file": "C:/sources/template.dwg",
                "source_layout": "A3",
                "target_layout": "001 平面",
            }
        ],
    )

    assert script.count("_.NETLOAD") == 1
    assert script.count("DstGetLayoutHandles") == 1
    assert script.count("_.QSAVE") == 1
    assert script.count("_.QUIT") == 1
    assert script.index("DstDeleteDefaultLayout") < script.index("DstGetLayoutHandles")
    assert script.index("DstGetLayoutHandles") < script.index("_.QSAVE") < script.index("_.QUIT")


def test_render_handles_remains_a_standalone_handle_script():
    script = ScriptRenderer().render_handles(Path("C:/plugins/DstManager.AutoCAD.dll"))

    assert "DstGetLayoutHandles" in script
    assert "DstDeleteLayouts" not in script
