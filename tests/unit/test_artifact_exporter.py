"""PLAN-DM-020 Task 8：宿主原子成果发布（ArtifactExporter）故障注入与成功路径。

覆盖 ARCH-DM-006 §9.2：候选不存在/验证失败、目标目录不可写、复制/flush/fsync/
replace/哈希/Artifact 插入各阶段故障注入；断言旧目标字节保持或新目标不存在、
临时文件清理（finally）、失败不登记 Artifact。成功路径：目标目录唯一临时文件 →
复制 → flush → 尽力 fsync → 重新核对基线 → os.replace → 最终哈希/大小登记。
日志关联 invocation ID/扩展 ID/版本/workspace/来源修订/artifact ID，且普通日志
不含求值属性值或完整输出路径。
"""

import hashlib
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dst_manager.extensions.artifacts import (
    ArtifactExporter,
    ArtifactExportError,
    ArtifactMetadata,
)
from dst_manager.extensions.save_grants import SaveGrantStore
from dst_manager.infrastructure.persistence.database import Database
from dst_manager.infrastructure.persistence.extensions import ExtensionStore

WORKSPACE_ID = "workspace-1"
EXTENSION_ID = "dst-manager.sheet-catalog"
EXTENSION_VERSION = "0.1.0"
ACTION_ID = "export-xlsx"
INVOCATION_ID = "inv-123"
SECRET_VALUE = "敏感属性值-求值结果-7f3a"

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_store(tmp_path: Path) -> ExtensionStore:
    return ExtensionStore(Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}").sessions)


def make_metadata(**overrides) -> ArtifactMetadata:
    values = {
        "extension_id": EXTENSION_ID,
        "extension_version": EXTENSION_VERSION,
        "workspace_id": WORKSPACE_ID,
        "source_revision_id": "rev-42",
        "kind": "sheet-catalog",
        "media_type": XLSX_MEDIA_TYPE,
    }
    values.update(overrides)
    return ArtifactMetadata(**values)


def make_grant(tmp_path: Path, target: Path) -> object:
    store = SaveGrantStore()
    receipt = store.create(EXTENSION_ID, ACTION_ID, WORKSPACE_ID, target)
    return store.consume(receipt.save_grant_id, EXTENSION_ID, ACTION_ID, WORKSPACE_ID)


def make_exporter(tmp_path: Path, **kwargs) -> ArtifactExporter:
    return ArtifactExporter(make_store(tmp_path), **kwargs)


class _RecordingArtifactStore:
    """只记录 create_artifact 调用的仓储替身（日志断言用，避开 Database 迁移）。"""

    def __init__(self) -> None:
        self.records: list = []

    def create_artifact(self, record):
        self.records.append(record)
        return record


def temp_leftovers(target_dir: Path) -> list[str]:
    """目录中残留的发布器临时文件（mkstemp 后缀 .part）。"""
    return [entry.name for entry in target_dir.iterdir() if entry.name.endswith(".part")]


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


def test_publish_replaces_target_atomically_and_registers_artifact(tmp_path: Path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old-bytes")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"new-xlsx-bytes")

    exporter = make_exporter(tmp_path, invocation_id=INVOCATION_ID)
    record = exporter.publish(grant, candidate, make_metadata())

    assert target.read_bytes() == b"new-xlsx-bytes"
    assert record.artifact_id
    assert record.extension_id == EXTENSION_ID
    assert record.extension_version == EXTENSION_VERSION
    assert record.workspace_id == WORKSPACE_ID
    assert record.source_revision_id == "rev-42"
    assert record.kind == "sheet-catalog"
    assert record.media_type == XLSX_MEDIA_TYPE
    assert record.management_relation == "external"
    assert record.output_path == str(target)
    assert record.file_name == "out.xlsx"
    assert record.size_bytes == len(b"new-xlsx-bytes")
    assert record.sha256 == hashlib.sha256(b"new-xlsx-bytes").hexdigest()
    created_at = record.created_at
    assert created_at.tzinfo is not None and created_at <= datetime.now(UTC)
    # 临时文件被清理：目录无 .part 残留（候选由 Task 9 的提案目录清理负责）
    assert temp_leftovers(target.parent) == []
    # Artifact 登记可回查
    store = ExtensionStore(Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}").sessions)
    assert store.get_artifact(record.artifact_id) == record


def test_publish_creates_unique_temp_file_in_target_directory(tmp_path: Path, monkeypatch):
    """临时文件必须在目标目录内创建（同卷，保证 os.replace 原子性）。"""
    target = tmp_path / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    grant = make_grant(tmp_path, target)
    seen_dirs: list[Path] = []

    real_mkstemp = tempfile.mkstemp

    def spy_mkstemp(*args, **kwargs):
        seen_dirs.append(kwargs.get("dir"))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("dst_manager.extensions.artifacts.tempfile.mkstemp", spy_mkstemp)
    make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
        grant, candidate, make_metadata()
    )
    assert seen_dirs == [tmp_path]


def test_publish_logs_identity_without_values_or_full_paths(tmp_path: Path, caplog):
    # 已知环境行为：migrations/env.py 的 fileConfig（disable_existing_loggers=True）
    # 在 Database 初始化时禁用既有 logger 并移除根处理器；本测试用仓储替身避免
    # 同测试内 Database 迁移，并在捕获前显式恢复模块 logger。
    artifacts_logger = logging.getLogger("dst_manager.extensions.artifacts")
    artifacts_logger.disabled = False
    target = tmp_path / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(SECRET_VALUE.encode())
    grant = make_grant(tmp_path, target)
    recording = _RecordingArtifactStore()
    with caplog.at_level(logging.INFO, logger="dst_manager.extensions.artifacts"):
        record = ArtifactExporter(recording, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    text = caplog.text
    assert INVOCATION_ID in text
    assert EXTENSION_ID in text
    assert EXTENSION_VERSION in text
    assert WORKSPACE_ID in text
    assert "rev-42" in text
    assert record.artifact_id in text
    assert str(target) not in text  # 完整输出路径不入普通日志
    assert str(candidate) not in text
    assert SECRET_VALUE not in text  # 求值属性值不入日志


# ---------------------------------------------------------------------------
# 故障注入：候选与验证
# ---------------------------------------------------------------------------


def test_publish_rejects_missing_candidate(tmp_path: Path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    grant = make_grant(tmp_path, target)
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, tmp_path / "missing.xlsx", make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert target.read_bytes() == b"old"
    assert temp_leftovers(tmp_path) == []
    store = make_store(tmp_path)
    assert store.get_artifact("any") is None


def test_publish_wraps_candidate_validation_failure(tmp_path: Path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"broken")

    def broken_validator(path: Path) -> None:
        raise ValueError("SHEET_CATALOG_XLSX_INVALID")

    exporter = ArtifactExporter(
        make_store(tmp_path),
        invocation_id=INVOCATION_ID,
        candidate_validator=broken_validator,
    )
    with pytest.raises(ArtifactExportError) as exc:
        exporter.publish(grant, candidate, make_metadata())
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert target.read_bytes() == b"old"
    assert temp_leftovers(tmp_path) == []


# ---------------------------------------------------------------------------
# 故障注入：目标目录不可写 / 复制 / flush / fsync / replace / 哈希 / 登记
# ---------------------------------------------------------------------------


def test_publish_fails_when_target_directory_not_writable(tmp_path: Path):
    target = tmp_path / "missing-dir" / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    grant = make_grant(tmp_path, target)
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert not target.exists()


def test_publish_fails_on_copy_error_and_keeps_old_target(tmp_path: Path, monkeypatch):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")

    def broken_copyfileobj(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        "dst_manager.extensions.artifacts.shutil.copyfileobj", broken_copyfileobj
    )
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert target.read_bytes() == b"old"
    assert temp_leftovers(tmp_path) == []


def test_publish_fails_on_flush_error_and_cleans_temp(tmp_path: Path, monkeypatch):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")

    def broken_flush(stream):
        raise OSError("flush failed")

    monkeypatch.setattr("dst_manager.extensions.artifacts._flush", broken_flush)
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert target.read_bytes() == b"old"
    assert temp_leftovers(tmp_path) == []


def test_publish_tolerates_fsync_failure_best_effort(tmp_path: Path, monkeypatch):
    """fsync 是尽力落盘（平台能力差异）：失败不阻断发布，但必须清理临时文件。"""
    target = tmp_path / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    grant = make_grant(tmp_path, target)

    def broken_fsync(stream):
        raise OSError("fsync unsupported")

    monkeypatch.setattr("dst_manager.extensions.artifacts._fsync", broken_fsync)
    record = make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
        grant, candidate, make_metadata()
    )
    assert target.read_bytes() == b"data"
    assert record.sha256 == hashlib.sha256(b"data").hexdigest()
    assert temp_leftovers(tmp_path) == []


def test_publish_fails_on_replace_error_and_keeps_old_target(tmp_path: Path, monkeypatch):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"old")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")

    def broken_replace(src, dst):
        raise OSError("replace locked")

    monkeypatch.setattr("dst_manager.extensions.artifacts.os.replace", broken_replace)
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert target.read_bytes() == b"old"
    assert temp_leftovers(tmp_path) == []
    assert make_store(tmp_path).get_artifact("any") is None


def test_publish_fails_on_hash_error_without_artifact(tmp_path: Path, monkeypatch):
    target = tmp_path / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    grant = make_grant(tmp_path, target)

    def broken_measure(path):
        raise OSError("read failed")

    monkeypatch.setattr("dst_manager.extensions.artifacts._measure", broken_measure)
    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert make_store(tmp_path).get_artifact("any") is None


def test_publish_fails_on_artifact_insert_error(tmp_path: Path, monkeypatch):
    """Artifact 插入失败同样按 ARTIFACT_WRITE_FAILED 契约化：不登记成功 Artifact。"""
    target = tmp_path / "out.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    grant = make_grant(tmp_path, target)
    store = make_store(tmp_path)
    attempts = {"count": 0}
    original = store.create_artifact

    def failing_create_artifact(record):
        attempts["count"] += 1
        raise RuntimeError("database locked")

    monkeypatch.setattr(store, "create_artifact", failing_create_artifact)
    with pytest.raises(ArtifactExportError) as exc:
        ArtifactExporter(store, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "ARTIFACT_WRITE_FAILED"
    assert attempts["count"] == 1
    monkeypatch.setattr(store, "create_artifact", original)
    assert store.get_artifact("any") is None  # 失败无 Artifact


# ---------------------------------------------------------------------------
# 基线复核（发布前再核对目标漂移）
# ---------------------------------------------------------------------------


def test_publish_rejects_when_target_drifted_before_replace(tmp_path: Path):
    target = tmp_path / "out.xlsx"
    target.write_bytes(b"at-grant-time")
    grant = make_grant(tmp_path, target)
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"data")
    target.write_bytes(b"user changed it after save dialog")

    with pytest.raises(ArtifactExportError) as exc:
        make_exporter(tmp_path, invocation_id=INVOCATION_ID).publish(
            grant, candidate, make_metadata()
        )
    assert exc.value.code == "EXPORT_DESTINATION_CHANGED"
    # 旧目标字节保持（未被新候选覆盖）
    assert target.read_bytes() == b"user changed it after save dialog"
    assert temp_leftovers(tmp_path) == []
    assert make_store(tmp_path).get_artifact("any") is None
