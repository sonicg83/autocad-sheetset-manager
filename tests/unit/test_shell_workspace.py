"""壳桥可信工作区上下文与文件夹/偏好方法单测（PLAN-DM-015 任务 2）。

fake Explorer 调用器只记录参数、绝不弹出窗口，覆盖：未打开工作区、其他
workspace_id、关闭后调用、目录消失、空格/中文路径、路径/命令注入拒绝，
以及 load/save_sheet_columns 与 clear_workspace_context 的错误码与成功路径。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dst_manager.application.shell_context import ShellContext
from dst_manager.config import Settings
from dst_manager.infrastructure.explorer import ExplorerUnsupportedError
from dst_manager.infrastructure.sheet_preferences import SheetPreferences
from dst_manager.interfaces.api import create_app
from dst_manager.interfaces.shell import ShellBridge


class FakeExplorer:
    """只记录参数、绝不弹出窗口的资源管理器调用器。"""

    def __init__(self):
        self.calls: list[tuple[str, Path]] = []
        self.fail: Exception | None = None

    def open_folder_and_select(self, file: Path) -> None:
        self.calls.append(("select", Path(file)))
        if self.fail is not None:
            raise self.fail

    def open_folder(self, folder: Path) -> None:
        self.calls.append(("folder", Path(folder)))
        if self.fail is not None:
            raise self.fail


def _fake_workspace(workspace_id: str = "ws-1", root: Path | None = None, dst_path: Path | None = None):
    return SimpleNamespace(id=workspace_id, root=root, dst_path=dst_path)


def _make_bridge(tmp_path: Path):
    context = ShellContext()
    preferences = SheetPreferences(tmp_path / "app-data")
    explorer = FakeExplorer()
    bridge = ShellBridge(context=context, preferences=preferences, explorer=explorer)
    return bridge, context, explorer


def _valid_preferences():
    return {
        "schemaVersion": 1,
        "file": True,
        "layout": False,
        "subsetAll": True,
        "subsetSingle": False,
        "properties": {"sheet:比例": True},
    }


def test_open_folder_requires_opened_workspace(tmp_path):
    bridge, _, explorer = _make_bridge(tmp_path)
    result = bridge.open_workspace_folder("ws-1")
    assert result["ok"] is False
    assert result["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert explorer.calls == []


def test_open_folder_rejects_other_workspace_id(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程"
    project.mkdir()
    dst = project / "图纸集.dst"
    dst.write_bytes(b"fake")
    context.set_workspace(_fake_workspace("ws-1", project, dst))
    result = bridge.open_workspace_folder("ws-2")
    assert result["ok"] is False
    assert result["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert explorer.calls == []


def test_open_folder_after_close_returns_unavailable(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    assert bridge.clear_workspace_context("ws-1")["ok"] is True
    result = bridge.open_workspace_folder("ws-1")
    assert result["ok"] is False
    assert result["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert explorer.calls == []


def test_open_folder_selects_dst_with_spaces_and_cjk_path(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程 甲"
    project.mkdir()
    dst = project / "图纸集.dst"
    dst.write_bytes(b"fake")
    context.set_workspace(_fake_workspace("ws-1", project, dst))
    result = bridge.open_workspace_folder("ws-1")
    assert result == {"ok": True, "value": None}
    assert explorer.calls == [("select", dst)]  # 完整原样路径，不做任何改写


def test_open_folder_opens_directory_when_dst_missing(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程"
    project.mkdir()
    context.set_workspace(_fake_workspace("ws-1", project, project / "消失的图纸集.dst"))
    result = bridge.open_workspace_folder("ws-1")
    assert result["ok"] is True
    assert explorer.calls == [("folder", project)]


def test_open_folder_reports_missing_directory(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程"  # 目录消失：根本不创建
    context.set_workspace(_fake_workspace("ws-1", project, project / "图纸集.dst"))
    result = bridge.open_workspace_folder("ws-1")
    assert result["ok"] is False
    assert result["code"] == "SHELL_DIRECTORY_NOT_FOUND"
    assert explorer.calls == []


def test_open_folder_reports_open_failure(tmp_path):
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程"
    project.mkdir()
    dst = project / "图纸集.dst"
    dst.write_bytes(b"fake")
    context.set_workspace(_fake_workspace("ws-1", project, dst))
    explorer.fail = ExplorerUnsupportedError("当前平台不支持打开资源管理器")
    result = bridge.open_workspace_folder("ws-1")
    assert result["ok"] is False
    assert result["code"] == "SHELL_OPEN_FAILED"


def test_explorer_reports_unsupported_on_non_windows(monkeypatch):
    """非 Windows 平台：真实 Explorer 适配直接返回不支持（不拼 shell 命令）。"""
    from dst_manager.infrastructure.explorer import Explorer

    monkeypatch.setattr("dst_manager.infrastructure.explorer.sys.platform", "linux")
    explorer = Explorer()
    with pytest.raises(ExplorerUnsupportedError):
        explorer.open_folder(Path("/工程 甲"))
    with pytest.raises(ExplorerUnsupportedError):
        explorer.open_folder_and_select(Path("/工程 甲/图纸集.dst"))


def test_open_folder_workspace_id_cannot_inject_path(tmp_path):
    """前端传入的 workspace_id 只用于匹配，绝不成为 explorer 目标；目标只能是上下文路径。"""
    bridge, context, explorer = _make_bridge(tmp_path)
    project = tmp_path / "工程"
    project.mkdir()
    dst = project / "图纸集.dst"
    dst.write_bytes(b"fake")
    context.set_workspace(_fake_workspace("ws-1", project, dst))
    evil = "..\\..\\Windows\\System32;calc.exe"
    result = bridge.open_workspace_folder(evil)
    assert result["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert explorer.calls == []


def test_load_sheet_columns_returns_none_when_empty(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    result = bridge.load_sheet_columns("ws-1")
    assert result == {"ok": True, "value": None}


def test_save_and_load_sheet_columns_roundtrip(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    assert bridge.save_sheet_columns("ws-1", _valid_preferences()) == {"ok": True, "value": None}
    assert bridge.load_sheet_columns("ws-1") == {"ok": True, "value": _valid_preferences()}


def test_save_sheet_columns_rejects_invalid_preferences(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    result = bridge.save_sheet_columns("ws-1", {"schemaVersion": 2})
    assert result["ok"] is False
    assert result["code"] == "SHEET_PREFERENCES_INVALID"


def test_save_sheet_columns_io_error_maps_to_preferences_io(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    (tmp_path / "app-data" / "ui-preferences").mkdir(parents=True)
    (tmp_path / "app-data" / "ui-preferences" / "sheets").write_text("occupied", encoding="utf-8")
    result = bridge.save_sheet_columns("ws-1", _valid_preferences())
    assert result["ok"] is False
    assert result["code"] == "SHEET_PREFERENCES_IO"


def test_sheet_columns_require_valid_context(tmp_path):
    bridge, _, _ = _make_bridge(tmp_path)
    assert bridge.load_sheet_columns("ws-1")["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert bridge.save_sheet_columns("ws-1", _valid_preferences())["code"] == "SHELL_WORKSPACE_UNAVAILABLE"


def test_clear_workspace_context_clears_and_is_idempotent_guarded(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    assert bridge.clear_workspace_context("ws-1") == {"ok": True, "value": None}
    assert context.current is None
    # 已清空后再清：无可匹配上下文，报不可用（前端按 best-effort 忽略）
    again = bridge.clear_workspace_context("ws-1")
    assert again["ok"] is False and again["code"] == "SHELL_WORKSPACE_UNAVAILABLE"


def test_clear_workspace_context_rejects_other_workspace_id(tmp_path):
    bridge, context, _ = _make_bridge(tmp_path)
    context.set_workspace(_fake_workspace("ws-1", tmp_path / "工程", tmp_path / "工程" / "图纸集.dst"))
    result = bridge.clear_workspace_context("ws-2")
    assert result["ok"] is False
    assert result["code"] == "SHELL_WORKSPACE_UNAVAILABLE"
    assert context.current is not None and context.current.workspace_id == "ws-1"  # 不清掉当前上下文


def test_create_app_on_workspace_opened_registers_context(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    context = ShellContext()
    app = create_app(Settings(data_dir=tmp_path / "data"), on_workspace_opened=context.set_workspace)
    with TestClient(app) as client:
        response = client.post("/api/workspaces/open", json={"dst_path": str(dst)})
        assert response.status_code == 200
        workspace_id = response.json()["id"]
        assert response.json()["dst_path"] == str(dst)
    assert context.current is not None
    assert context.current.workspace_id == workspace_id
    assert context.current.dst_path == dst


def test_create_app_open_without_callback_keeps_http_contract(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))  # 默认 on_workspace_opened=None
    with TestClient(app) as client:
        response = client.post("/api/workspaces/open", json={"dst_path": str(dst)})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] and body["dst_path"] == str(dst) and body["revision_id"]
        assert body["sheet_set"]["sheet_count"] == 1
