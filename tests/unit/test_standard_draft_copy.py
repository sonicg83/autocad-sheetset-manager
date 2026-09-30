"""复制已发布标准时的模板副本与整批创建边界。"""

import copy
import json
import shutil
from pathlib import Path

import pytest

from dst_manager.infrastructure.standards.store import StandardStore, StandardStoreError

SOURCE_ID = "123e4567-e89b-42d3-a456-426614174101"
TARGET_ID = "123e4567-e89b-42d3-a456-426614174102"


@pytest.fixture
def store(tmp_path: Path) -> StandardStore:
    return StandardStore(
        official_root=tmp_path / "standards" / "official",
        user_root=tmp_path / "standards" / "user",
    )


def published_source(store: StandardStore, *, official=False, schema_version=4):
    document = {
        "schema_version": schema_version,
        "standard_id": SOURCE_ID,
        "name": "原标准",
        "description": "模板说明",
        "published_at": 1_800_000_000_123,
        "supported_cad_versions": ["2020"],
        "properties": [],
        "dwg_naming": {"segments": [{"system_field": "subset.name"}]},
        "numbering": {"sequence_field": "subset.sequence", "digits": 3, "start": 7},
        "assets": [
            {"asset_id": "base", "kind": "base-template", "file": "assets/基础.dwt"},
            {
                "asset_id": "layout", "kind": "layout-template",
                "file": "assets/图框/布局.dwg", "paper_layouts": ["A2", "A1"],
            },
        ],
        "custom_metadata": {"说明": "未知字段保留"},
    }
    root = (store.official_root if official else store.published_root) / SOURCE_ID
    root.mkdir(parents=True)
    (root / "document.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    for index, asset in enumerate(document["assets"]):
        file = root / asset["file"]
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(f"template-{index}".encode())
    request = copy.deepcopy(document)
    request.update(standard_id=TARGET_ID, name="新草稿", published_at=None)
    return root, document, request


@pytest.mark.parametrize("official", [False, True])
@pytest.mark.parametrize("schema_version", [3, 4])
def test_copy_preserves_content_and_independent_files(store, official, schema_version):
    root, document, request = published_source(store, official=official, schema_version=schema_version)
    originals = {file: (file.read_bytes(), file.stat().st_mtime_ns) for file in root.rglob("*") if file.is_file()}
    # 创建只从请求中取新身份和名称，内容与资产由服务端源标准决定。
    request["assets"] = []
    request["numbering"]["digits"] = 9
    result = store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    expected = {**document, "standard_id": TARGET_ID, "name": "新草稿", "published_at": None}
    assert result.document == expected
    assert store.get_draft("copy").document == expected
    destination = store.drafts_root / "copy"
    for asset in document["assets"]:
        original = root / asset["file"]
        copied = destination / asset["file"]
        assert copied.read_bytes() == original.read_bytes()
        assert not copied.samefile(original)
        copied.write_bytes(b"changed")
    for file, (data, mtime) in originals.items():
        assert file.read_bytes() == data
        assert file.stat().st_mtime_ns == mtime
    store.delete_draft("copy")
    assert all(file.exists() for file in originals)


def test_copy_shared_file_once_and_excludes_undeclared_files(store, monkeypatch):
    root, document, request = published_source(store)
    document["assets"].append({"asset_id": "base-2", "kind": "base-template", "file": "assets/基础.dwt"})
    (root / "document.json").write_text(json.dumps(document), encoding="utf-8")
    (root / "assets" / "unused.dwg").write_bytes(b"unused")
    copied_paths = []
    original_copy = shutil.copyfile

    def record_copy(source, target, **kwargs):
        copied_paths.append(source)
        return original_copy(source, target, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", record_copy)
    result = store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert len(result.document["assets"]) == 3
    assert len(copied_paths) == 2
    assert not (store.drafts_root / "copy" / "assets" / "unused.dwg").exists()


def test_missing_asset_rejects_creation_without_partial_draft(store):
    root, _, request = published_source(store)
    (root / "assets" / "图框" / "布局.dwg").unlink()
    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_FILE_MISSING"):
        store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert not (store.drafts_root / "copy").exists()


def test_second_copy_failure_removes_whole_draft_and_allows_retry(store, monkeypatch):
    root, _, request = published_source(store)
    original_copy = shutil.copyfile
    calls = 0

    def fail_second(source, target, **kwargs):
        nonlocal calls
        calls += 1
        # 文档应在所有模板写完后才出现；半成品不能被读取或列出。
        assert store.get_draft("copy") is None
        if calls == 2:
            Path(target).write_bytes(b"partial")
            raise OSError("模拟第二个模板复制失败")
        return original_copy(source, target, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", fail_second)
    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_COPY_FAILED"):
        store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert not (store.drafts_root / "copy").exists()
    assert (root / "assets" / "基础.dwt").read_bytes() == b"template-0"
    monkeypatch.setattr(shutil, "copyfile", original_copy)
    store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert store.get_draft("copy") is not None


def test_document_write_failure_removes_copied_assets(store, monkeypatch):
    _, _, request = published_source(store)

    def fail_write(*args):
        raise OSError("模拟草稿文档写入失败")

    monkeypatch.setattr(store, "_write_document", fail_write)
    with pytest.raises(OSError, match="文档写入失败"):
        store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert not (store.drafts_root / "copy").exists()


def test_copy_rejects_missing_standard_and_escaping_asset(store):
    root, document, request = published_source(store)
    with pytest.raises(StandardStoreError, match="STANDARD_ID_NOT_FOUND"):
        store.create_draft(request, "copy", source_standard_id=TARGET_ID)
    document["assets"][0]["file"] = "../outside.dwg"
    (root / "document.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_PATH_INVALID"):
        store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert not (store.drafts_root / "copy").exists()


def test_copy_rejects_same_identity_without_touching_source(store):
    root, _, request = published_source(store)
    request["standard_id"] = SOURCE_ID
    with pytest.raises(StandardStoreError, match="STANDARD_ID_EXISTS"):
        store.create_draft(request, "copy", source_standard_id=SOURCE_ID)
    assert (root / "document.json").is_file()
    assert not (store.drafts_root / "copy").exists()
