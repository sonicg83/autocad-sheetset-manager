"""PLAN-DM-020 Task 8：一次性保存授权（进程内、随机、单次消费、目标基线）。

覆盖 ARCH-DM-006 §9.1：授权不持久化；随机 ID 与固定 .xlsx 后缀；TTL 过期；
伪造/复用/扩展/动作/工作区错配拒绝；选择时记录目标存在性、规范路径、文件
身份（device/inode/size/mtime_ns）与 SHA-256；消费时目标漂移拒绝（
EXPORT_DESTINATION_CHANGED）。并发语义（§11）：同一授权恰有一个消费者成功；
两个不同授权可并发消费、不取得工作区写锁。
"""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dst_manager.extensions.save_grants import (
    SaveGrantError,
    SaveGrantReceipt,
    SaveGrantStore,
    TargetBaseline,
    capture_baseline,
)

WORKSPACE_ID = "workspace-1"
EXTENSION_ID = "dst-manager.sheet-catalog"
ACTION_ID = "export-xlsx"


def make_target(tmp_path: Path, name: str = "out.xlsx", content: bytes | None = None) -> Path:
    target = tmp_path / name
    if content is not None:
        target.write_bytes(content)
    return target


def create_grant(store: SaveGrantStore, target: Path, **overrides) -> SaveGrantReceipt:
    return store.create(
        overrides.get("extension_id", EXTENSION_ID),
        overrides.get("action_id", ACTION_ID),
        overrides.get("workspace_id", WORKSPACE_ID),
        target,
        ttl_seconds=overrides.get("ttl_seconds", 300),
    )


# ---------------------------------------------------------------------------
# 创建：随机 ID、固定后缀、TTL
# ---------------------------------------------------------------------------


def test_create_returns_receipt_with_random_id_fixed_suffix_and_ttl(tmp_path: Path):
    store = SaveGrantStore()
    before = datetime.now(UTC)
    receipt = create_grant(store, tmp_path / "out")
    after = datetime.now(UTC)

    assert isinstance(receipt, SaveGrantReceipt)
    assert receipt.file_name == "out.xlsx"  # 固定 .xlsx 后缀
    assert receipt.save_grant_id
    assert receipt.expires_at > before + timedelta(seconds=295)
    assert receipt.expires_at <= after + timedelta(seconds=300)

    other = create_grant(store, tmp_path / "other.xlsx")
    assert other.save_grant_id != receipt.save_grant_id  # 随机不重复


def test_create_binds_identity_and_resolves_target(tmp_path: Path):
    store = SaveGrantStore()
    # 故意用含 .. 的非规范路径：授权必须记录规范化的目标
    target = tmp_path / "sub" / ".." / "out.xlsx"
    receipt = create_grant(store, target)
    consumed = store.consume(
        receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID
    )
    assert consumed.target == (tmp_path / "out.xlsx").resolve()
    assert consumed.extension_id == EXTENSION_ID
    assert consumed.action_id == ACTION_ID
    assert consumed.workspace_id == WORKSPACE_ID
    assert consumed.save_grant_id == receipt.save_grant_id


def test_grants_are_process_local_and_never_persisted(tmp_path: Path):
    """授权只存在当前 SaveGrantStore 实例内：新实例不认识旧授权（不落库）。"""
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path))
    fresh = SaveGrantStore()
    with pytest.raises(SaveGrantError) as exc:
        fresh.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "SAVE_GRANT_INVALID"


# ---------------------------------------------------------------------------
# 消费拒绝矩阵
# ---------------------------------------------------------------------------


def test_consume_rejects_forged_unknown_grant():
    with pytest.raises(SaveGrantError) as exc:
        SaveGrantStore().consume("forged-id", EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "SAVE_GRANT_INVALID"


def test_consume_rejects_expired_grant(tmp_path: Path):
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path), ttl_seconds=0)
    with pytest.raises(SaveGrantError) as exc:
        store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "SAVE_GRANT_INVALID"


def test_consume_is_single_use_second_attempt_rejected(tmp_path: Path):
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path, content=b"x"))
    store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    with pytest.raises(SaveGrantError) as exc:
        store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "SAVE_GRANT_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extension_id", "dst-manager.other"),
        ("action_id", "other-action"),
        ("workspace_id", "workspace-2"),
    ],
)
def test_consume_rejects_identity_mismatch(tmp_path: Path, field: str, value: str):
    """扩展/动作/工作区任一错配都拒绝，且错配尝试同样烧毁授权（防探测）。"""
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path, content=b"x"))
    kwargs = {
        "extension_id": EXTENSION_ID,
        "action_id": ACTION_ID,
        "workspace_id": WORKSPACE_ID,
    }
    kwargs[field] = value
    with pytest.raises(SaveGrantError) as exc:
        store.consume(receipt.save_grant_id, **kwargs)
    assert exc.value.code == "SAVE_GRANT_INVALID"
    with pytest.raises(SaveGrantError):
        store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)


# ---------------------------------------------------------------------------
# 目标基线：存在性、规范路径、文件身份、SHA-256
# ---------------------------------------------------------------------------


def test_consume_records_baseline_identity_and_sha256(tmp_path: Path):
    content = b"existing-bytes"
    target = make_target(tmp_path, content=content)
    stat = target.stat()
    store = SaveGrantStore()
    receipt = create_grant(store, target)
    consumed = store.consume(
        receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID
    )
    baseline = consumed.baseline
    assert isinstance(baseline, TargetBaseline)
    assert baseline.existed is True
    assert baseline.size_bytes == len(content)
    assert baseline.modified_ns == stat.st_mtime_ns
    assert baseline.device == stat.st_dev
    assert baseline.inode == stat.st_ino  # Windows/NTFS 上可能为 0，不假设恒非零
    assert baseline.sha256 == hashlib.sha256(content).hexdigest()
    assert consumed.target.is_absolute()


def test_capture_baseline_reports_missing_target(tmp_path: Path):
    baseline = capture_baseline(tmp_path / "missing.xlsx")
    assert baseline.existed is False
    assert baseline.device is None
    assert baseline.inode is None
    assert baseline.size_bytes is None
    assert baseline.modified_ns is None
    assert baseline.sha256 is None


def test_capture_baseline_reports_unreadable_target_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """目标存在但打开失败（AV/Excel 独占锁定、权限变化、stat/open 竞态）时
    返回"存在但基线不可读"基线，绝不裸抛 OSError（fix round 3：非契约 500
    逃逸窗口的源头封堵）。"""
    target = make_target(tmp_path, content=b"base")
    real_open = Path.open

    def locked_open(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "被其他程序占用")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", locked_open)

    baseline = capture_baseline(target)
    assert baseline.existed is True  # 文件在：不是 MISSING 语义
    assert baseline.device is None
    assert baseline.inode is None
    assert baseline.size_bytes is None
    assert baseline.modified_ns is None
    assert baseline.sha256 is None  # 身份无法确认，由调用方归类


# ---------------------------------------------------------------------------
# 目标漂移拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["created", "modified", "deleted"])
def test_consume_rejects_target_drift(tmp_path: Path, mode: str):
    target = make_target(tmp_path, content=b"base")
    if mode == "created":
        target = tmp_path / "new.xlsx"
    store = SaveGrantStore()
    receipt = create_grant(store, target)

    if mode == "created":
        target.write_bytes(b"brand new")
    elif mode == "modified":
        target.write_bytes(b"base-changed")
    else:
        target.unlink()

    with pytest.raises(SaveGrantError) as exc:
        store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "EXPORT_DESTINATION_CHANGED"


def test_consume_wraps_unreadable_target_io_as_contract_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """消费时目标哈希读取 IO 失败（锁定/权限/竞态）：按契约化
    EXPORT_DESTINATION_CHANGED 拒绝（fail-closed），绝不裸抛 OSError 逃逸到
    execute 通道的 OSError 兜底；授权随消费烧毁。"""
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path, content=b"base"))
    real_open = Path.open

    def locked_open(self, *args, **kwargs):
        if self.name.endswith(".xlsx"):
            raise PermissionError(13, "被其他程序占用")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", locked_open)

    with pytest.raises(SaveGrantError) as exc:
        store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)
    assert exc.value.code == "EXPORT_DESTINATION_CHANGED"
    assert "不可读" in str(exc.value)
    # 授权已随消费烧毁（消费即销毁，任何后续尝试一律 INVALID）
    assert store.active_count() == 0


# ---------------------------------------------------------------------------
# 并发语义（ARCH-DM-006 §11）
# ---------------------------------------------------------------------------


def test_single_grant_exactly_one_consumer_succeeds(tmp_path: Path):
    store = SaveGrantStore()
    receipt = create_grant(store, make_target(tmp_path, content=b"x"))
    barrier = threading.Barrier(8)

    def attempt() -> str:
        barrier.wait()
        consumed = store.consume(
            receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID
        )
        return consumed.save_grant_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _collect(attempt), range(8)))

    winners = [value for value, _ in results if value is not None]
    losers = [error for _, error in results if error is not None]
    assert len(winners) == 1  # 同一授权只有一个消费者成功
    assert winners[0] == receipt.save_grant_id
    assert len(losers) == 7
    assert all(error.code == "SAVE_GRANT_INVALID" for error in losers)


def _collect(callable_):
    try:
        return callable_(), None
    except SaveGrantError as exc:
        return None, exc


def test_two_grants_consume_concurrently_without_workspace_lock(tmp_path: Path):
    """两个不同授权并发导出互不阻塞（§11）：不取得任何工作区写锁、DST 不被触碰。"""
    dst = make_target(tmp_path, name="project.dst", content=b"dst-bytes")
    dst_sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    store = SaveGrantStore()
    receipt_a = create_grant(store, make_target(tmp_path, name="a.xlsx", content=b"a"))
    receipt_b = create_grant(store, make_target(tmp_path, name="b.xlsx", content=b"b"))
    start = threading.Barrier(2)

    def consume(receipt: SaveGrantReceipt) -> str:
        start.wait()
        return store.consume(
            receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID
        ).save_grant_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(consume, receipt_a)
        future_b = pool.submit(consume, receipt_b)
        assert future_a.result(timeout=5) == receipt_a.save_grant_id
        assert future_b.result(timeout=5) == receipt_b.save_grant_id

    assert store.active_count() == 0
    assert hashlib.sha256(dst.read_bytes()).hexdigest() == dst_sha
