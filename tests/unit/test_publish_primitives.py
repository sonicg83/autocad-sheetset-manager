import hashlib
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.publish_primitives import (
    capture_file_baseline,
    file_sha256,
    move_no_replace,
    replace_existing,
)


def test_file_sha256_matches_known_digest(tmp_path: Path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"known-bytes")
    assert file_sha256(target) == hashlib.sha256(b"known-bytes").hexdigest()


def test_capture_file_baseline_distinguishes_existing_and_missing(tmp_path: Path):
    target = tmp_path / "a.txt"
    assert capture_file_baseline(target) is None
    target.write_bytes(b"payload")
    baseline = capture_file_baseline(target)
    assert baseline is not None and baseline.sha256 == file_sha256(target)


def test_move_no_replace_rejects_existing_target(tmp_path: Path):
    source = tmp_path / "src.txt"
    source.write_text("moved")
    existing = tmp_path / "dst.txt"
    existing.write_text("occupied")
    with pytest.raises(FileExistsError):
        move_no_replace(source, existing)
    assert source.exists() and existing.read_text() == "occupied"


def test_replace_existing_preserves_previous_content_in_backup(tmp_path: Path):
    source = tmp_path / "new.txt"
    source.write_text("new")
    target = tmp_path / "formal.txt"
    target.write_text("old")
    backup = tmp_path / "backup.txt"
    replace_existing(source, target, backup)
    assert target.read_text() == "new"
    assert backup.read_text() == "old"
    assert not source.exists()
