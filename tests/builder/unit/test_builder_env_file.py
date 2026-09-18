"""dst_builder.runtime 的 .env 配置文件加载（方案 C：setup.bat 兼供 Builder）。

契约：
- 定位：frozen 态 = exe 同目录（setup.bat "与本程序 exe 放同一目录"约定），
  开发态 = 仓库根（与 Manager pydantic-settings 的 env_file 同位）。
- 语义：只补缺失键，进程已有环境变量优先（与 pydantic-settings 默认一致）。
- 容错：文件缺失/不可读 → 静默跳过，绝不阻断启动；空行与 # 注释跳过。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from dst_builder import runtime


def test_env_file_path_dev_uses_repo_root() -> None:
    """开发态 .env 位于仓库根（与 Builder 迁移/pyproject 资源基准一致）。"""
    assert runtime.env_file_path() == runtime._DEV_ROOT / ".env"


def test_env_file_path_base_injection(tmp_path: Path) -> None:
    assert runtime.env_file_path(tmp_path) == tmp_path / ".env"


def test_env_file_path_frozen_uses_exe_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frozen 态 .env 在 exe 同目录（setup.bat 与 DSTManager.exe 同目录的既有约定）。"""
    exe_dir = tmp_path / "dist"
    exe_dir.mkdir()
    fake_exe = exe_dir / "dst-builder.exe"
    fake_exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    assert runtime.env_file_path() == exe_dir / ".env"


def test_apply_env_file_fills_missing_keys_and_skips_comments(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment line\n"
        "\n"
        "DST_BUILDER_AUTOCAD_2020_CONSOLE=C:\\Program Files\\Autodesk\\AutoCAD 2020\\accoreconsole.exe\n"
        "  EnableAddNumberSuffix = true  \n",
        encoding="utf-8",
    )
    environ: dict[str, str] = {}

    assert runtime.apply_env_file(environ, base=tmp_path) is True
    assert (
        environ["DST_BUILDER_AUTOCAD_2020_CONSOLE"]
        == "C:\\Program Files\\Autodesk\\AutoCAD 2020\\accoreconsole.exe"
    )
    assert environ["EnableAddNumberSuffix"] == "true"


def test_apply_env_file_never_overrides_existing_keys(tmp_path: Path) -> None:
    """进程已有环境变量优先（pydantic-settings 同语义）：.env 不得覆盖。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DST_BUILDER_AUTOCAD_2016_CONSOLE=X:\\from-file\\accoreconsole.exe\n",
        encoding="utf-8",
    )
    environ = {"DST_BUILDER_AUTOCAD_2016_CONSOLE": "X:\\from-process\\accoreconsole.exe"}

    assert runtime.apply_env_file(environ, base=tmp_path) is False
    assert environ["DST_BUILDER_AUTOCAD_2016_CONSOLE"] == "X:\\from-process\\accoreconsole.exe"


def test_apply_env_file_missing_file_is_noop(tmp_path: Path) -> None:
    environ: dict[str, str] = {}
    assert runtime.apply_env_file(environ, base=tmp_path) is False
    assert environ == {}


def test_apply_env_file_invalid_utf8_is_tolerated(tmp_path: Path) -> None:
    """编码非法的 .env 不阻断启动（setup.bat 保证 UTF-8，防御手工编辑事故）。"""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"\xff\xfe\x00bad")
    environ: dict[str, str] = {}
    assert runtime.apply_env_file(environ, base=tmp_path) is False


def test_load_cad_configuration_reads_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """集成：进程环境缺少 CONSOLE 键时，仓库根 .env 中的值被读取。"""
    console = tmp_path / "accoreconsole.exe"
    console.write_bytes(b"MZ")
    env_repo = tmp_path / "repo"
    env_repo.mkdir()
    (env_repo / ".env").write_text(
        f"DST_BUILDER_AUTOCAD_2020_CONSOLE={console}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "_DEV_ROOT", env_repo)
    for key in ("DST_BUILDER_AUTOCAD_2020_CONSOLE", "DST_BUILDER_AUTOCAD_2020_PLUGIN"):
        monkeypatch.delenv(key, raising=False)

    from dst_builder.infrastructure.autocad.capabilities import load_cad_configuration

    configuration = load_cad_configuration()

    assert configuration.console_2020 == console.resolve()


def test_load_cad_configuration_never_mutates_process_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 是 Manager/Builder 共享文件：合并视图读取，绝不回写真实进程环境。

    回归背景：共享 .env 中的 DST_MANAGER_* 键被写进 os.environ 后，依赖
    "环境未设置 → None" 的 Manager 配置测试在测试进程内被跨用例污染。
    """
    console = tmp_path / "accoreconsole.exe"
    console.write_bytes(b"MZ")
    env_repo = tmp_path / "repo"
    env_repo.mkdir()
    (env_repo / ".env").write_text(
        "DST_MANAGER_AUTOCAD_2016_CONSOLE=X:\\manager\\accoreconsole.exe\n"
        f"DST_BUILDER_AUTOCAD_2020_CONSOLE={console}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "_DEV_ROOT", env_repo)
    for key in (
        "DST_BUILDER_AUTOCAD_2020_CONSOLE",
        "DST_MANAGER_AUTOCAD_2016_CONSOLE",
    ):
        monkeypatch.delenv(key, raising=False)

    from dst_builder.infrastructure.autocad.capabilities import load_cad_configuration

    configuration = load_cad_configuration()

    assert configuration.console_2020 == console.resolve()
    assert "DST_MANAGER_AUTOCAD_2016_CONSOLE" not in os.environ
    assert "DST_BUILDER_AUTOCAD_2020_CONSOLE" not in os.environ
