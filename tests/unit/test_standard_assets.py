"""标准模板资产检查（PLAN-DM-035 Task 5）：布局严格比较与稳定诊断。

覆盖：声明图幅与非 Model 布局的严格比较（``"A2 " != "A2"``）、能力缺失
转换为 ``STANDARD_CAD_CAPABILITY_MISSING`` 诊断而不抛出、草稿/资产/文件
缺失与非法路径的稳定拒绝。CAD 读取入口经替换注入，不依赖真实 Core Console。
"""

import typing
from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings

DRAFT_DOCUMENT = {
    "schema_version": 1,
    "standard_id": "szmedi.gas",
    "version": "0.1.0",
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [],
    "rules": [],
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
