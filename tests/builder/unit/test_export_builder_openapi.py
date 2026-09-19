"""Builder OpenAPI 导出与漂移校验脚本测试。"""

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest


def _load_exporter() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "export_builder_openapi.py"
    spec = importlib.util.spec_from_file_location("export_builder_openapi", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_builder_openapi_check_detects_drift(tmp_path: Path) -> None:
    main = _load_exporter().main
    output = tmp_path / "openapi.json"

    assert main(["--output", str(output)]) == 0
    assert main(["--check", "--output", str(output)]) == 0

    output.write_text("{}\n", encoding="utf-8")

    assert main(["--check", "--output", str(output)]) == 1


def test_builder_openapi_declares_corrupt_build_status_response() -> None:
    schema = json.loads(_load_exporter().rendered_schema())

    responses = schema["paths"]["/api/builds/{build_id}"]["get"]["responses"]
    assert responses["500"]["description"] == "构建状态记录不完整"


def test_export_builder_openapi_refuses_manager_contract() -> None:
    main = _load_exporter().main
    manager_contract = Path("web/src/api/openapi.json").resolve()

    with pytest.raises(SystemExit, match="禁止改写 Manager"):
        main(["--output", str(manager_contract)])


def test_export_builder_openapi_refuses_manager_contract_hard_link(
    tmp_path: Path, monkeypatch
) -> None:
    exporter = _load_exporter()
    manager_contract = tmp_path / "manager-openapi.json"
    manager_contract.write_text('{"manager": true}\n', encoding="utf-8")
    alias = tmp_path / "builder-alias.json"
    os.link(manager_contract, alias)
    monkeypatch.setattr(exporter, "_FORBIDDEN", manager_contract)

    with pytest.raises(SystemExit, match="禁止改写 Manager"):
        exporter.main(["--output", str(alias)])

    assert manager_contract.read_text(encoding="utf-8") == '{"manager": true}\n'
