"""原子写入与瞬时占用重试的单元测试。

对应 2026-09-14 现场：安全软件/EDR 文件过滤驱动在「新建临时文件 → os.replace」
之间短暂持有文件，返回 WinError 5/32/33，导致发布日志写入失败并回滚整批。
这里固定三类行为：瞬时拒绝按有界退避重试、预算耗尽仍抛原始错误、真实错误不重试。
"""

from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem import atomic as atomic_module
from dst_manager.infrastructure.filesystem.atomic import (
    DEFAULT_ATTEMPTS,
    DEFAULT_BASE_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    atomic_write_text,
    is_transient_contention,
)


def _windows_permission_error(winerror: int) -> PermissionError:
    error = PermissionError(13, "拒绝访问")
    error.winerror = winerror  # type: ignore[attr-defined]
    return error


def _no_sleep(delays: list[float]):
    def sleep(seconds: float) -> None:
        delays.append(seconds)

    return sleep


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_write_text_retries_transient_contention(tmp_path: Path, monkeypatch, winerror: int):
    target = tmp_path / "publish-journal.json"
    target.write_text("旧内容", encoding="utf-8")
    original_replace = atomic_module.os.replace
    calls = 0

    def replace(source, destination):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise _windows_permission_error(winerror)
        return original_replace(source, destination)

    delays: list[float] = []
    monkeypatch.setattr(atomic_module.os, "replace", replace)

    atomic_write_text(target, "新内容", sleep=_no_sleep(delays))

    assert calls == 3
    assert target.read_text(encoding="utf-8") == "新内容"
    # 退避必须递增且不超过上限；被拒绝的临时文件不得残留
    assert delays == [DEFAULT_BASE_DELAY_SECONDS, DEFAULT_BASE_DELAY_SECONDS * 2]
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_raises_original_error_after_budget_exhausted(tmp_path: Path, monkeypatch):
    target = tmp_path / "publish-journal.json"
    target.write_text("旧内容", encoding="utf-8")
    calls = 0

    def replace(_source, _destination):
        nonlocal calls
        calls += 1
        raise _windows_permission_error(5)

    delays: list[float] = []
    monkeypatch.setattr(atomic_module.os, "replace", replace)

    with pytest.raises(PermissionError) as exc_info:
        atomic_write_text(target, "新内容", sleep=_no_sleep(delays))

    assert calls == DEFAULT_ATTEMPTS
    assert len(delays) == DEFAULT_ATTEMPTS - 1
    assert all(delay <= MAX_DELAY_SECONDS for delay in delays)
    assert getattr(exc_info.value, "winerror", None) == 5
    assert target.read_text(encoding="utf-8") == "旧内容"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_does_not_retry_permanent_errors(tmp_path: Path, monkeypatch):
    target = tmp_path / "publish-journal.json"
    calls = 0

    def replace(_source, _destination):
        nonlocal calls
        calls += 1
        raise FileNotFoundError(2, "系统找不到指定的文件。")

    delays: list[float] = []
    monkeypatch.setattr(atomic_module.os, "replace", replace)

    with pytest.raises(FileNotFoundError):
        atomic_write_text(target, "新内容", sleep=_no_sleep(delays))

    assert calls == 1
    assert delays == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_rejects_invalid_attempt_budget(tmp_path: Path):
    with pytest.raises(ValueError):
        atomic_write_text(tmp_path / "publish-journal.json", "内容", attempts=0)


def test_transient_contention_classification():
    assert is_transient_contention(_windows_permission_error(5)) is True
    assert is_transient_contention(_windows_permission_error(32)) is True
    assert is_transient_contention(_windows_permission_error(33)) is True
    assert is_transient_contention(_windows_permission_error(2)) is False
    assert is_transient_contention(OSError(13, "拒绝访问")) is True
    assert is_transient_contention(FileNotFoundError(2, "不存在")) is False
    assert is_transient_contention(ValueError("非文件错误")) is False
