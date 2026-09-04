"""runtime 路径解析单测：开发态/frozen 态两态定位与测试注入。"""

import sys
from pathlib import Path

from dst_manager.runtime import is_frozen, resource_dir

REPO_ROOT = Path(__file__).parents[2]


def test_dev_state_resource_dir_is_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert is_frozen() is False
    assert resource_dir() == REPO_ROOT


def test_frozen_state_resource_dir_is_meipass(monkeypatch):
    meipass = Path(r"C:\packed\_internal")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert is_frozen() is True
    assert resource_dir() == meipass


def test_explicit_base_overrides_both_states(monkeypatch):
    base = Path(r"D:\inject")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resource_dir(base) == base


def test_api_mounts_web_dist_from_resource_dir(monkeypatch, tmp_path):
    """静态站点目录必须经 resource_dir 定位：frozen 态下 __file__ 不再指向源码树。"""
    from dst_manager.interfaces import api

    web_dist = tmp_path / "web" / "dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(api, "resource_dir", lambda: tmp_path)
    app = api.create_app()
    # Starlette 将根挂载 "/" 归一化为 ""，故两种取值都算根挂载
    mounts = [r for r in app.routes if r.path in ("", "/") and r.__class__.__name__ == "Mount"]
    assert mounts, "web/dist 未被挂载到 /"
