"""release 脚本静态契约：UTF-8 BOM、PowerShell 语法可解析、关键步骤齐全。
Task 7 只覆盖 build_release.ps1；release.ps1 的契约用例在 Task 8 追加。"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "build_release.ps1"
POWERSHELLS = [path for path in (shutil.which("powershell"), shutil.which("pwsh")) if path]

REQUIRED_BUILD_STEPS = ["npm ci", "npm run build", "uv sync --dev", "build_plugins.ps1", "pyinstaller", "Compress-Archive"]


def test_build_release_script_is_utf8_bom():
    assert SCRIPT.exists(), "缺少 build_release.ps1"
    assert SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(not POWERSHELLS, reason="需要 Windows PowerShell 或 PowerShell 7")
def test_build_release_script_parses_in_powershell():
    command = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    completed = subprocess.run(
        [POWERSHELLS[0], "-NoProfile", "-Command", command], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_build_release_script_contains_required_steps():
    source = SCRIPT.read_text(encoding="utf-8-sig")
    for marker in REQUIRED_BUILD_STEPS:
        assert marker in source, f"build_release.ps1 缺少步骤：{marker}"
