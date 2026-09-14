import hashlib
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.publish_primitives import (
    capture_file_baseline,
    file_sha256,
    move_no_replace,
    replace_existing,
)
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    RecoverablePublisher,
)


def _identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


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


def test_caller_identity_baseline_allows_unchanged_target(tmp_path: Path):
    target = tmp_path / "caller-baseline.dwg"
    staged = tmp_path / "staged-caller-baseline.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    expected = capture_file_baseline(target)

    RecoverablePublisher().publish(
        "caller-baseline-unchanged",
        tmp_path,
        {target: staged},
        attempt=1,
        expected_baselines={target: expected},
    )

    assert target.read_bytes() == b"published"


def test_caller_identity_baseline_rejects_same_bytes_replacement_before_publish(tmp_path: Path):
    target = tmp_path / "caller-race.dwg"
    staged = tmp_path / "staged-caller-race.dwg"
    external = tmp_path / "external-caller-race.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"baseline")
    expected = capture_file_baseline(target)
    external_identity = _identity(external)
    os.replace(external, target)

    with pytest.raises(PublishBaselineError) as exc_info:
        RecoverablePublisher().publish(
            "caller-identity-race",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: expected},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"baseline"
    assert _identity(target) == external_identity
