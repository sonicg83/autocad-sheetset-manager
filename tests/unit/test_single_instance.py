"""桌面壳单实例守卫单测：互斥量名称派生、先启动持锁/后启动被拒、释放重入、
唤起容错与非 Windows 放行。Windows 内核对象用例在非 Windows 平台跳过。"""

from pathlib import Path

import pytest

from dst_manager.infrastructure import single_instance as si


def test_instance_app_dir_uses_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert si.instance_app_dir() == Path(r"D:\user-appdata") / "dst-manager"


def test_instance_app_dir_explicit_base_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert si.instance_app_dir(tmp_path) == tmp_path


def test_mutex_name_is_deterministic_and_user_scoped():
    first = si.mutex_name(Path(r"D:\appdata-a"))
    again = si.mutex_name(Path(r"D:\appdata-a"))
    other = si.mutex_name(Path(r"D:\appdata-b"))
    assert first == again
    assert first != other
    assert first.startswith("Local\\dst-manager-")
    assert len(first) == len("Local\\dst-manager-") + 12  # 固定前缀 + 12 位十六进制摘要


@pytest.mark.skipif(not si.WINDOWS, reason="命名互斥量为 Windows 内核对象")
def test_acquire_second_instance_denied_until_release():
    """先启动者持锁；同进程再获取被判为第二个实例；释放后可重新成为唯一实例。"""
    guard = si.acquire_instance_mutex(Path(r"C:\instance-test"))
    assert guard is not None
    try:
        duplicate = si.acquire_instance_mutex(Path(r"C:\instance-test"))
        assert duplicate is None  # 已有实例在运行
    finally:
        si.release_instance_mutex(guard)
    # 释放后内核互斥量归属本进程关闭，重新获取应成功
    again = si.acquire_instance_mutex(Path(r"C:\instance-test"))
    assert again is not None
    si.release_instance_mutex(again)


def test_acquire_non_windows_platform_allows_startup(monkeypatch):
    monkeypatch.setattr(si, "WINDOWS", False)
    guard = si.acquire_instance_mutex(Path(r"C:\unused"))
    assert guard is si._NO_GUARD_REQUIRED  # 放行标记不等于“第二个实例”
    si.release_instance_mutex(guard)  # 释放放行标记必须无事发生


@pytest.mark.skipif(not si.WINDOWS, reason="命名互斥量为 Windows 内核对象")
def test_acquire_platform_gate_consistent_with_release(monkeypatch):
    """非 Windows 模拟态下 release 对放行标记与句柄既不抛错也不动内核。"""
    monkeypatch.setattr(si, "WINDOWS", False, raising=False)
    si.release_instance_mutex(None)
    si.release_instance_mutex(si._NO_GUARD_REQUIRED)
    si.release_instance_mutex(123)  # 非 Windows 下直返，不触 Win32


def test_find_app_window_never_raises_when_missing(monkeypatch, tmp_path):
    """找不到窗口（首个实例仍在启动/标题异常）应容错返回 None，后续唤起静默跳过。"""
    monkeypatch.setattr(si.time, "sleep", lambda _seconds: None)
    if si.WINDOWS:
        assert si.find_app_window("__DST_MANAGER_UNLIKELY_TITLE__", attempts=2) is None
    else:
        assert si.find_app_window("any", attempts=2) is None


def test_restore_and_foreground_best_effort_non_windows(monkeypatch):
    monkeypatch.setattr(si, "WINDOWS", False)
    assert si.restore_and_foreground(12345) is False


def test_notify_already_running_reports_and_returns(capsys, monkeypatch):
    """第二个实例收尾全流程不抛异常；无窗口可唤起时仅报错退出。"""
    monkeypatch.setattr(si, "WINDOWS", False)
    monkeypatch.setattr(si, "find_app_window", lambda *_a, **_k: None)
    si.notify_already_running_and_raise()
    captured = capsys.readouterr()
    assert "已在运行" in captured.err


@pytest.mark.skipif(not si.WINDOWS, reason="前台唤起逻辑为 Windows 行为")
def test_restore_and_foreground_with_hwnd_no_window_owns_target(monkeypatch):
    """对不属于本进程的假句柄调用不崩溃（Win32 对无效句柄静默返回失败）。"""
    result = si.restore_and_foreground(0)  # 空句柄
    assert result is False