"""runtime 路径解析单测：开发态/frozen 态两态定位与测试注入；无窗日志重定向。"""

import sys
from pathlib import Path

from dst_manager.runtime import (
    _stdio_usable,
    is_frozen,
    log_dir,
    redirect_frozen_stdio,
    resource_dir,
)

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


def test_migrate_database_uses_resource_dir(monkeypatch, tmp_path):
    """frozen 态下 alembic.ini 与 migrations/ 是打包资源：必须经 resource_dir 定位而非源码树。"""
    import shutil

    from dst_manager.infrastructure.persistence import database as database_module

    shutil.copyfile(REPO_ROOT / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(REPO_ROOT / "migrations", tmp_path / "migrations")
    monkeypatch.setattr(database_module, "resource_dir", lambda: tmp_path)
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    database_module.migrate_database(url)
    # PLAN-DM-020 Task 2 已把 head 前移到 0006（此处原漏更新，随 Task 3 全量回归修复）
    assert database_module.LATEST_SCHEMA_REVISION == "0006_dm020_extension_platform"
    # 迁移真实发生：alembic_version 表存在且为最新修订
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    version = engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == database_module.LATEST_SCHEMA_REVISION


class _FakeNullWriter:
    """模拟 PyInstaller windowed 态注入的 NullWriter：有 write/flush、无 fileno。"""

    def write(self, *_args):
        pass

    def flush(self):
        pass


class _FakeRealStream:
    def fileno(self):
        return 1


def test_stdio_usable_distinguishes_null_writer_from_real_stream():
    assert _stdio_usable(None) is False
    assert _stdio_usable(_FakeNullWriter()) is False
    assert _stdio_usable(_FakeRealStream()) is True


def test_log_dir_frozen_uses_localappdata(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert log_dir() == Path(r"D:\user-appdata") / "dst-manager" / "logs"


def test_log_dir_explicit_base_overrides(monkeypatch):
    assert log_dir(Path(r"D:\inject")) == Path(r"D:\inject")


def test_redirect_frozen_stdio_noop_in_dev(monkeypatch, tmp_path):
    """开发态日志走终端，重定向必须不生效。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert redirect_frozen_stdio("desktop", base=tmp_path) is False
    assert not list(tmp_path.iterdir())


def test_redirect_frozen_stdio_ignores_console_commands(monkeypatch, tmp_path):
    """doctor/serve 等控制台子命令不重定向（命令行可见）。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert redirect_frozen_stdio("doctor", base=tmp_path) is False
    assert not list(tmp_path.iterdir())


def test_redirect_frozen_stdio_replaces_null_streams_and_writes_header(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeNullWriter())
    monkeypatch.setattr(sys, "stderr", _FakeNullWriter())
    assert redirect_frozen_stdio("desktop", base=tmp_path) is True
    # monkeypatch teardown 会还原 sys.stdout/stderr，此处只验证指向与落盘
    assert Path(sys.stdout.name) == tmp_path / "dst-manager.log"
    sys.stdout.write("壳进程输出\n")  # 行缓冲：换行即落盘
    sys.stderr.write("启动警告\n")
    sys.stderr.flush()
    text = (tmp_path / "dst-manager.log").read_text(encoding="utf-8")
    assert "desktop =====" in text
    assert "壳进程输出" in text
    assert "启动警告" in text


def test_redirect_frozen_stdio_worker_writes_worker_log(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert redirect_frozen_stdio("worker", base=tmp_path) is True
    assert Path(sys.stderr.name) == tmp_path / "worker.log"


def test_redirect_frozen_stdio_keeps_usable_stream(monkeypatch, tmp_path):
    """从控制台手工运行时输出保持可见：可用流不被替换。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeRealStream())
    monkeypatch.setattr(sys, "stderr", _FakeNullWriter())
    assert redirect_frozen_stdio("worker", base=tmp_path) is True
    assert isinstance(sys.stdout, _FakeRealStream)  # 可用流未被替换
    assert Path(sys.stderr.name) == tmp_path / "worker.log"  # 仅坏流被重定向
