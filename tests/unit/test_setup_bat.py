"""setup.bat 静态契约与沙箱集成测试。

守护意图：
- setup.bat 面向打包分发后的最终用户（ARCH-DM-002 §3.4），必须在无 AutoCAD 的
  CI 环境可测：通过 DST_SETUP_AUTODESK_ROOT 指向假安装根、DST_SETUP_SKIP_REGISTRY=1
  跳过注册表探测，用假 accoreconsole.exe 目录结构验证探测、版本映射与 .env 写入。
- 版本映射契约：2015-2019 → 2016 桶；2020-2024 → 2020 桶；2013/2014 警告后仍入
  2016 桶；2025+ 不受支持（.NET 8）；accoreconsole 自 2013 起才有，2013 以前不探测。
- 幂等契约：已有 .env 的既有键绝不覆盖，只补缺失项。

bat 无法用 PowerShell 语法解析器静态校验，静态断言只覆盖关键标记。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "setup.bat"
BUILD_RELEASE = ROOT / "scripts" / "build_release.ps1"

CONSOLE_KEYS = {
    "2016": "DST_MANAGER_AUTOCAD_2016_CONSOLE=",
    "2020": "DST_MANAGER_AUTOCAD_2020_CONSOLE=",
}


def _run_setup(app_dir: Path, autodesk_root: Path) -> subprocess.CompletedProcess[str]:
    """在临时程序目录内运行 setup.bat（跳过注册表与结尾暂停）。

    stdout/stderr 按 GBK 解码：bat 为 ANSI（zh-CN 默认代码页）编码，
    见 setup.bat 文件头的编码说明。
    """
    shutil.copyfile(SCRIPT, app_dir / "setup.bat")
    env = os.environ.copy()
    env["DST_SETUP_AUTODESK_ROOT"] = str(autodesk_root)
    env["DST_SETUP_SKIP_REGISTRY"] = "1"
    env["DST_SETUP_NO_PAUSE"] = "1"
    completed = subprocess.run(
        ["cmd", "/c", ".\\setup.bat"],
        cwd=app_dir,
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        completed.stdout.decode("gbk", errors="replace"),
        completed.stderr.decode("gbk", errors="replace"),
    )


def _env_lines(env_file: Path) -> dict[str, str]:
    lines: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            lines[key] = value
    return lines


def _make_fake_autocad(autodesk_root: Path, *years: str) -> None:
    for year in years:
        console = autodesk_root / f"AutoCAD {year}" / "accoreconsole.exe"
        console.parent.mkdir(parents=True, exist_ok=True)
        console.write_bytes(b"")


def test_setup_bat_exists_and_gbk_no_bom():
    """bat 必须存为 GBK（ANSI）且无 BOM：cmd 对 UTF-8 批处理多字节解析不可靠，
    BOM 会破坏首行 @echo off（编码例外依据见 setup.bat 文件头与 ARCH-DM-002）。"""
    assert SCRIPT.is_file(), "缺少 scripts/setup.bat"
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "setup.bat 不能带 BOM"
    raw.decode("gbk")


def test_setup_bat_contains_required_markers():
    source = SCRIPT.read_text(encoding="gbk")
    # .env 模板注释必须全 ASCII（保证写出的 .env 恒为合法 UTF-8），故无 chcp 依赖
    for marker in CONSOLE_KEYS.values():
        assert marker in source, f"setup.bat 缺少配置键：{marker}"
    assert "accoreconsole.exe" in source
    assert "SOFTWARE\\Autodesk\\AutoCAD" in source, "注册表探测路径缺失"
    for year in ("2013", "2016", "2020", "2024"):
        assert year in source, f"版本映射表缺少 {year}"


def test_build_release_copies_setup_bat_into_package():
    source = BUILD_RELEASE.read_text(encoding="utf-8-sig")
    assert "setup.bat" in source, "build_release.ps1 必须把 setup.bat 复制进分发包"


def test_generates_env_with_version_mapping(tmp_path: Path):
    """2016 + 2021 共存：两桶各自填写；模板含默认项。"""
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    _make_fake_autocad(autodesk_root, "2016", "2021")

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert values["DST_MANAGER_AUTOCAD_2016_CONSOLE"] == str(
        autodesk_root / "AutoCAD 2016" / "accoreconsole.exe"
    )
    assert values["DST_MANAGER_AUTOCAD_2020_CONSOLE"] == str(
        autodesk_root / "AutoCAD 2021" / "accoreconsole.exe"
    )
    assert values["EnableAddNumberSuffix"] == "true"
    assert values["NumberSuffixType"] == "1"


def test_2013_2014_mapped_to_2016_bucket_with_warning(tmp_path: Path):
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    _make_fake_autocad(autodesk_root, "2014")

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert values["DST_MANAGER_AUTOCAD_2016_CONSOLE"] == str(
        autodesk_root / "AutoCAD 2014" / "accoreconsole.exe"
    )
    assert "警告" in result.stdout, "2013/2014 映射必须输出兼容性风险警告"
    assert CONSOLE_KEYS["2020"] not in values


def test_latest_version_wins_within_bucket(tmp_path: Path):
    """同一兼容组内装了 2016 与 2018：取更新的 2018 写入 2016 桶。"""
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    _make_fake_autocad(autodesk_root, "2016", "2018")

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert values["DST_MANAGER_AUTOCAD_2016_CONSOLE"] == str(
        autodesk_root / "AutoCAD 2018" / "accoreconsole.exe"
    )


def test_2025_unsupported(tmp_path: Path):
    """仅装 2025：不写任何 CONSOLE 键（保留注释占位），并提示不支持。"""
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    _make_fake_autocad(autodesk_root, "2025")

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert CONSOLE_KEYS["2016"] not in values
    assert CONSOLE_KEYS["2020"] not in values
    assert "2025" in result.stdout


def test_existing_env_keys_never_overwritten(tmp_path: Path):
    """幂等：已有 .env 的 2016 键保持不变，缺失的 2020 键被补上。"""
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    custom = "X:\\custom\\accoreconsole.exe"
    (app_dir / ".env").write_text(
        "EnableAddNumberSuffix=false\n"
        f"DST_MANAGER_AUTOCAD_2016_CONSOLE={custom}\n",
        encoding="utf-8",
    )
    _make_fake_autocad(autodesk_root, "2016", "2021")

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert values["DST_MANAGER_AUTOCAD_2016_CONSOLE"] == custom, "已有配置不得被探测结果覆盖"
    assert values["DST_MANAGER_AUTOCAD_2020_CONSOLE"] == str(
        autodesk_root / "AutoCAD 2021" / "accoreconsole.exe"
    )
    assert values["EnableAddNumberSuffix"] == "false", "已有配置不得被模板默认值覆盖"


def test_no_autocad_detected_leaves_keys_commented(tmp_path: Path):
    """未发现任何 AutoCAD：生成模板但不写死路径，提示手工填写。"""
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()

    result = _run_setup(app_dir, autodesk_root)
    assert result.returncode == 0, result.stdout + result.stderr

    values = _env_lines(app_dir / ".env")
    assert CONSOLE_KEYS["2016"] not in values
    assert CONSOLE_KEYS["2020"] not in values
    assert "手工" in result.stdout or "手动" in result.stdout
