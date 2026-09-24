"""标准包导入预检的限时快照与凭证单测（PLAN-DM-041 Task 5）。"""

from pathlib import Path

import pytest

from dst_manager.infrastructure.standards.import_previews import (
    MAX_PACKAGE_SOURCE_BYTES,
    ImportPreviewError,
    ImportPreviewStore,
)


def make_store(tmp_path: Path, *, ttl_seconds: float = 900, clock=None) -> ImportPreviewStore:
    root = tmp_path / "tmp" / "standard-import-previews"
    if clock is None:
        return ImportPreviewStore(root, ttl_seconds=ttl_seconds)
    return ImportPreviewStore(root, ttl_seconds=ttl_seconds, clock=clock)


def write_source(tmp_path: Path, name: str = "sample.dststandard", size: int = 8) -> Path:
    source = tmp_path / name
    source.write_bytes(b"x" * size)
    return source


# ---- 快照复制 -----------------------------------------------------------------


def test_snapshot_copies_bytes_outside_the_source_directory(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = write_source(tmp_path, size=16)

    snapshot = store.snapshot_source(source)

    assert snapshot.is_file()
    assert snapshot.read_bytes() == b"x" * 16
    assert snapshot.parent == store.root
    # 快照与来源目录彼此隔离：来源仍在原处且未被改写。
    assert source.read_bytes() == b"x" * 16
    assert snapshot != source


def test_snapshot_rejects_non_dststandard_suffix(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = write_source(tmp_path, name="sample.zip")
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_SOURCE_INVALID"):
        store.snapshot_source(source)
    assert store.snapshot_files() == ()


def test_snapshot_rejects_missing_and_directory_sources(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_SOURCE_NOT_FOUND"):
        store.snapshot_source(tmp_path / "absent.dststandard")
    directory = tmp_path / "looks-like.dststandard"
    directory.mkdir()
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_SOURCE_NOT_FOUND"):
        store.snapshot_source(directory)


def test_snapshot_rejects_oversized_source(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = write_source(tmp_path, size=MAX_PACKAGE_SOURCE_BYTES + 1)
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_SOURCE_TOO_LARGE"):
        store.snapshot_source(source)
    assert store.snapshot_files() == ()


def test_snapshot_leaves_no_partial_file_on_copy_failure(
    tmp_path: Path, monkeypatch
) -> None:
    store = make_store(tmp_path)
    source = write_source(tmp_path, size=32)
    monkeypatch.setattr(
        "shutil.copyfileobj",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected copy failure")),
    )
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_COPY_FAILED"):
        store.snapshot_source(source)
    assert store.snapshot_files() == ()
    assert list(store.root.glob(".*")) == []


# ---- 凭证生命周期 -------------------------------------------------------------


def test_unknown_credential_is_not_found(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_PREVIEW_NOT_FOUND"):
        store.require("forged")


def test_restart_clears_unreachable_snapshots(tmp_path: Path) -> None:
    """重启后凭证全部失效，快照根里剩下的文件按定义已不可达：新实例必须清空它们。"""
    store = make_store(tmp_path)
    snapshot = store.snapshot_source(write_source(tmp_path))
    store.register(snapshot, {"standard_id": "a.b"})
    assert store.snapshot_files() == (snapshot,)

    restarted = make_store(tmp_path)

    assert restarted.snapshot_files() == ()
    assert not snapshot.exists()


def test_fresh_process_loses_credentials(tmp_path: Path) -> None:
    """凭证只存在于内存：新建 Store 实例（模拟重启）后同一凭证必须失效。"""
    store = make_store(tmp_path)
    record = store.register(write_source(tmp_path), {"standard_id": "a.b"})

    restarted = make_store(tmp_path)
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_PREVIEW_NOT_FOUND"):
        restarted.require(record.preview_id)


def test_expired_credential_is_rejected_and_snapshot_removed(tmp_path: Path) -> None:
    now = {"value": 1000.0}
    store = make_store(tmp_path, ttl_seconds=10, clock=lambda: now["value"])
    snapshot = store.snapshot_source(write_source(tmp_path))
    record = store.register(snapshot, {"standard_id": "a.b"})

    now["value"] += 11
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_PREVIEW_EXPIRED"):
        store.require(record.preview_id)
    assert not snapshot.exists()


def test_cancel_removes_credential_and_snapshot(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    snapshot = store.snapshot_source(write_source(tmp_path))
    record = store.register(snapshot, {"standard_id": "a.b"})

    store.cancel(record.preview_id)

    assert not snapshot.exists()
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_PREVIEW_NOT_FOUND"):
        store.require(record.preview_id)
    # 重复取消是幂等的。
    store.cancel(record.preview_id)


def test_cleanup_keeps_fresh_records_and_drops_expired_ones(tmp_path: Path) -> None:
    now = {"value": 500.0}
    store = make_store(tmp_path, ttl_seconds=100, clock=lambda: now["value"])
    snapshot = store.snapshot_source(write_source(tmp_path))
    record = store.register(snapshot, {"standard_id": "a.b"})

    # 未过期：cleanup 不动凭证与快照。
    store.cleanup()
    assert store.require(record.preview_id).preview_id == record.preview_id
    assert snapshot.is_file()

    # 过期后：cleanup 删除快照，凭证变为未知（已清理 ≠ 仍可探到过期）。
    now["value"] += 101
    store.cleanup()
    assert not snapshot.exists()
    with pytest.raises(ImportPreviewError, match="STANDARD_IMPORT_PREVIEW_NOT_FOUND"):
        store.require(record.preview_id)


def test_remembered_result_is_returned_for_repeat_confirmation(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    record = store.register(store.snapshot_source(write_source(tmp_path)), {})

    stored = store.remember_result(record.preview_id, {"standard_id": "a.b", "version": 1})

    assert stored == {"standard_id": "a.b", "version": 1}
    assert store.require(record.preview_id).consumed == {"standard_id": "a.b", "version": 1}


def test_preview_ids_are_random_and_unguessable(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    ids = {
        store.register(store.snapshot_source(write_source(tmp_path, f"s{index}.dststandard")), {}).preview_id
        for index in range(6)
    }
    assert len(ids) == 6
    assert all(len(item) == 32 for item in ids)


def test_discard_snapshot_removes_unregistered_copy(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    snapshot = store.snapshot_source(write_source(tmp_path))
    store.discard_snapshot(snapshot)
    assert not snapshot.exists()
    # 不存在时也不报错。
    store.discard_snapshot(snapshot)
