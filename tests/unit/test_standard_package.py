"""标准包（.dststandard）安全读取测试（PLAN-DM-035 Task 3）。"""

import json
import zipfile
from pathlib import Path

import pytest

from dst_manager.infrastructure.standards.package import (
    StandardPackageError,
    StandardPackageReader,
)

VALID_MANIFEST = json.dumps(
    {
        "schema_version": 1,
        "standard_id": "szmedi.gas",
        "version": "2.1.0",
        "name": "市政燃气施工图",
        "supported_cad_versions": ["2016", "2020"],
        "properties": [{"name": "专业名称", "scope": "sheetset", "required": True}],
        "rules": [],
        "assets": [
            {
                "asset_id": "layouts",
                "kind": "layout-template",
                "files": [{"path": "assets/A2.dwg", "role": "A2"}],
            }
        ],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
    },
    ensure_ascii=False,
)

EXECUTABLE_EXTENSIONS = [".py", ".dll", ".scr", ".lsp", ".exe", ".bat", ".ps1"]


def write_zip(tmp_path: Path, entries: dict[str, str | bytes]) -> Path:
    package = tmp_path / "sample.dststandard"
    with zipfile.ZipFile(package, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return package


def test_package_rejects_parent_path(tmp_path: Path) -> None:
    package = write_zip(tmp_path, {"manifest.json": VALID_MANIFEST, "../escape.dwg": b"x"})
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_PATH_INVALID"):
        StandardPackageReader().read(package)


def test_package_rejects_absolute_path(tmp_path: Path) -> None:
    package = write_zip(tmp_path, {"manifest.json": VALID_MANIFEST, "/etc/passwd": b"x"})
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_PATH_INVALID"):
        StandardPackageReader().read(package)


@pytest.mark.parametrize("extension", EXECUTABLE_EXTENSIONS)
def test_package_rejects_executable_extension(tmp_path: Path, extension: str) -> None:
    package = write_zip(
        tmp_path,
        {"manifest.json": VALID_MANIFEST, f"assets/payload{extension}": b"x"},
    )
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_EXTENSION_FORBIDDEN"):
        StandardPackageReader().read(package)


def test_package_rejects_duplicate_normalized_paths(tmp_path: Path) -> None:
    package = write_zip(
        tmp_path,
        {
            "manifest.json": VALID_MANIFEST,
            "assets/./A2.dwg": b"a",
            "assets/A2.dwg": b"b",
        },
    )
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_PATH_INVALID"):
        StandardPackageReader().read(package)


def test_package_rejects_missing_manifest(tmp_path: Path) -> None:
    package = write_zip(tmp_path, {"assets/A2.dwg": b"a"})
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_MANIFEST_MISSING"):
        StandardPackageReader().read(package)


def test_package_rejects_invalid_manifest_schema(tmp_path: Path) -> None:
    package = write_zip(
        tmp_path,
        {"manifest.json": json.dumps({"schema_version": 9})},
    )
    with pytest.raises(StandardPackageError, match="STANDARD_SCHEMA_VERSION_UNSUPPORTED"):
        StandardPackageReader().read(package)


def test_package_rejects_oversized_entry(tmp_path: Path) -> None:
    package = write_zip(
        tmp_path,
        {"manifest.json": VALID_MANIFEST, "assets/huge.dwg": b"x" * (65 * 1024 * 1024)},
    )
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_TOO_LARGE"):
        StandardPackageReader().read(package)


def test_package_lists_declared_entries(tmp_path: Path) -> None:
    package = write_zip(
        tmp_path,
        {"manifest.json": VALID_MANIFEST, "assets/A2.dwg": b"dwg-bytes"},
    )
    loaded = StandardPackageReader().read(package)
    assert loaded.standard.standard_id == "szmedi.gas"
    assert loaded.standard.version == "2.1.0"
    entries = {entry.path: entry.size for entry in loaded.entries}
    assert entries == {"assets/A2.dwg": len(b"dwg-bytes")}
