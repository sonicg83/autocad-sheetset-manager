"""标准模板资产检查（PLAN-DM-035 Task 5）：布局严格比较与稳定诊断。

覆盖：声明图幅与非 Model 布局的严格比较（``"A2 " != "A2"``）、能力缺失
转换为 ``STANDARD_CAD_CAPABILITY_MISSING`` 诊断而不抛出、草稿/资产/文件
缺失与非法路径的稳定拒绝。CAD 读取入口经替换注入，不依赖真实 Core Console。
PLAN-DM-040 Task 3 追加：本机模板文件受控复制进草稿（受控副本名、源文件
哈希与 mtime 不变、故障不落半文件）。
"""

import hashlib
import shutil
import typing
import uuid
from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings

#: 单文件上限（与标准包单条目上限一致）：超过即拒绝复制。
MAX_TEMPLATE_BYTES = 64 * 1024 * 1024

DRAFT_DOCUMENT = {
    "schema_version": 2,
    "standard_id": "szmedi.gas",
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [],
    "dwg_naming": {
        "segments": [
            {"system_field": "subset.scope"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    },
    "assets": [
        {
            "asset_id": "layouts",
            "kind": "layout-template",
            "files": [
                {"path": "assets/A2.dwg", "role": "A2"},
                {"path": "assets/A3.dwg", "role": "A3"},
            ],
        },
        {
            "asset_id": "base",
            "kind": "base-template",
            "files": [{"path": "assets/base.dwt", "role": ""}],
        },
    ],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


@pytest.fixture
def fake_reader(service: DstManagerService, monkeypatch):
    """替换 CAD 读取入口；``reader.responses`` 按文件名词干配置布局，
    ``reader.layouts`` 统一覆盖全部文件，``reader.error`` 注入读取失败。"""

    class Reader:
        responses: typing.ClassVar[dict[str, list[str]]] = {
            "A2": ["Model", "A2"],
            "A3": ["Model", "A3"],
            "base": ["Model"],
        }
        layouts: list[str] | None = None
        error: ApplicationError | None = None

    def read(self, file_path: Path, cad_version: str) -> dict:
        if Reader.error is not None:
            raise Reader.error
        if Reader.layouts is not None:
            return {"layouts": list(Reader.layouts), "cached": False, "file_hash": "0" * 64}
        return {
            "layouts": list(Reader.responses[Path(file_path).stem]),
            "cached": False,
            "file_hash": "0" * 64,
        }

    monkeypatch.setattr(DstManagerService, "get_layout_names", read)
    return Reader


@pytest.fixture
def draft(service: DstManagerService) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    assets = store.drafts_root / "draft" / "assets"
    assets.mkdir(parents=True)
    for name in ("A2.dwg", "A3.dwg", "base.dwt"):
        (assets / name).write_bytes(b"fake dwg bytes")


def codes(inspection) -> list[str]:
    return [item.code for item in inspection.diagnostics]


def test_layout_asset_requires_exact_paper_layout(service, fake_reader, draft) -> None:
    fake_reader.layouts = ["Model", "A2 ", "A3"]
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert result.diagnostics[0].code == "STANDARD_LAYOUT_NAME_MISMATCH"
    assert result.layouts == ("Model", "A2 ", "A3")


def test_layout_asset_with_matching_layouts_passes(service, fake_reader, draft) -> None:
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert codes(result) == []
    assert result.kind == "layout-template"
    assert result.layouts == ("Model", "A2", "A3")


def test_layout_asset_case_difference_is_mismatch(service, fake_reader, draft) -> None:
    fake_reader.layouts = ["Model", "a2", "A3"]
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert set(codes(result)) == {"STANDARD_LAYOUT_NAME_MISMATCH"}


@pytest.mark.parametrize("cad_version", ["2016", "2020"])
def test_missing_cad_capability_becomes_diagnostic(
    service, fake_reader, draft, cad_version
) -> None:
    fake_reader.error = ApplicationError(
        "CAD_CAPABILITY_UNAVAILABLE",
        f"AutoCAD {cad_version} 未配置：缺少 Core Console 或 Worker 插件路径",
        503,
    )
    result = service.inspect_standard_asset("draft", "layouts", cad_version)
    assert set(codes(result)) == {"STANDARD_CAD_CAPABILITY_MISSING"}


def test_layout_read_failure_becomes_diagnostic(service, fake_reader, draft) -> None:
    fake_reader.error = ApplicationError(
        "LAYOUT_READ_FAILED", "读取布局失败：DWG 可能正被 AutoCAD 占用", 502
    )
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert set(codes(result)) == {"STANDARD_LAYOUT_READ_FAILED"}


def test_missing_asset_file_becomes_diagnostic(service, fake_reader, draft) -> None:
    (service.standard_store.drafts_root / "draft" / "assets" / "A3.dwg").unlink()
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert codes(result) == ["STANDARD_ASSET_FILE_MISSING"]


def test_base_template_without_roles_skips_layout_comparison(
    service, fake_reader, draft
) -> None:
    fake_reader.layouts = ["Model", "任意布局"]
    result = service.inspect_standard_asset("draft", "base", "2020")
    assert codes(result) == []


def test_unknown_draft_rejected(service, fake_reader) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.inspect_standard_asset("missing", "layouts", "2020")
    assert exc_info.value.code == "STANDARD_DRAFT_NOT_FOUND"


def test_unknown_asset_rejected(service, fake_reader, draft) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.inspect_standard_asset("draft", "no-such-asset", "2020")
    assert exc_info.value.code == "STANDARD_ASSET_NOT_FOUND"


def test_escaping_asset_path_rejected(service, fake_reader, draft) -> None:
    document = dict(DRAFT_DOCUMENT)
    document["assets"] = [
        {
            "asset_id": "evil",
            "kind": "base-template",
            "files": [{"path": "../outside.dwg", "role": ""}],
        }
    ]
    service.standard_store.save_draft("draft", document)
    with pytest.raises(ApplicationError) as exc_info:
        service.inspect_standard_asset("draft", "evil", "2020")
    assert exc_info.value.code == "STANDARD_ASSET_PATH_INVALID"


# ---- 本机模板受控复制（PLAN-DM-040 Task 3，F01） --------------------------


def source_file(tmp_path: Path, name: str = "A2 模板.dwg") -> Path:
    """带中文、空格与多层目录的来源文件（模拟 OneDrive 路径）。"""
    directory = tmp_path / "OneDrive - 项目 资料" / "模板 目录"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(b"dwg-bytes")
    return target


def test_copy_asset_file_creates_managed_copy(service, tmp_path) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    source = source_file(tmp_path)
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before_mtime = source.stat().st_mtime_ns

    result = service.copy_draft_asset_file("draft", source)

    assert result["path"].startswith("assets/managed-")
    assert result["path"].endswith(".dwg")
    copied = store.drafts_root / "draft" / result["path"]
    assert copied.read_bytes() == b"dwg-bytes"
    # 来源文件的哈希与 mtime 不得被改变，绝对路径也不进草稿
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
    assert source.stat().st_mtime_ns == before_mtime
    assert str(source) not in result["path"]


def test_copy_asset_file_supports_dwt(service, tmp_path) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    source = source_file(tmp_path, "基础模板.DWT")

    result = service.copy_draft_asset_file("draft", source)

    assert result["path"].endswith(".dwt")
    assert (store.drafts_root / "draft" / result["path"]).is_file()


def test_copy_asset_file_missing_source_rejected(service, tmp_path) -> None:
    service.standard_store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", tmp_path / "nope.dwg")
    assert exc_info.value.code == "STANDARD_ASSET_SOURCE_NOT_FOUND"


def test_copy_asset_file_rejects_directory_source(service, tmp_path) -> None:
    service.standard_store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    directory = tmp_path / "looks-like.dwg"
    directory.mkdir()
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", directory)
    assert exc_info.value.code == "STANDARD_ASSET_SOURCE_NOT_FOUND"


@pytest.mark.parametrize("name", ["模板.txt", "模板.dwg.exe", "模板"])
def test_copy_asset_file_rejects_other_extensions(service, tmp_path, name: str) -> None:
    service.standard_store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    source = tmp_path / name
    source.write_bytes(b"x")
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", source)
    assert exc_info.value.code == "STANDARD_ASSET_SOURCE_INVALID"


def test_copy_asset_file_rejects_oversized_source(service, tmp_path) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    source = tmp_path / "huge.dwg"
    with source.open("wb") as handle:  # 稀疏文件：只声明大小，不写 64 MiB 字节
        handle.truncate(MAX_TEMPLATE_BYTES + 1)
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", source)
    assert exc_info.value.code == "STANDARD_ASSET_SOURCE_INVALID"
    assert not (store.drafts_root / "draft" / "assets").exists()


def test_copy_asset_file_requires_existing_draft(service, tmp_path) -> None:
    source = source_file(tmp_path)
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("missing", source)
    assert exc_info.value.code == "STANDARD_DRAFT_NOT_FOUND"


def test_copy_asset_file_rejects_illegal_draft_id(service, tmp_path) -> None:
    source = source_file(tmp_path)
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("../outside", source)
    assert exc_info.value.code == "STANDARD_DRAFT_ID_INVALID"


def test_copy_asset_file_aborts_without_partial_files(service, monkeypatch, tmp_path) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    source = source_file(tmp_path)
    baseline = (store.drafts_root / "draft" / "document.json").read_bytes()

    def interrupted(*args: object, **kwargs: object) -> None:
        raise OSError("磁盘写入中断")

    monkeypatch.setattr(shutil, "copyfileobj", interrupted)
    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", source)
    assert exc_info.value.code == "STANDARD_ASSET_COPY_FAILED"
    assets = store.drafts_root / "draft" / "assets"
    assert list(assets.iterdir()) == []
    assert (store.drafts_root / "draft" / "document.json").read_bytes() == baseline


def test_copy_asset_file_never_overwrites_existing_copy(
    service, monkeypatch, tmp_path
) -> None:
    store = service.standard_store
    store.create_draft(DRAFT_DOCUMENT, draft_id="draft")
    assets = store.drafts_root / "draft" / "assets"
    assets.mkdir(parents=True)
    fixed = uuid.UUID(int=0).hex
    occupied = assets / f"managed-{fixed}.dwg"
    occupied.write_bytes(b"keep-me")
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=0))

    with pytest.raises(ApplicationError) as exc_info:
        service.copy_draft_asset_file("draft", source_file(tmp_path))
    assert exc_info.value.code == "STANDARD_ASSET_COPY_FAILED"
    assert occupied.read_bytes() == b"keep-me"
    assert sorted(item.name for item in assets.iterdir()) == [f"managed-{fixed}.dwg"]
