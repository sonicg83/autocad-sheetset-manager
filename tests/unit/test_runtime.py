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
