"""DST Builder 打包契约静态守护（PLAN-DB-001 Task 11）。

对 packaging/dst-builder.spec、packaging/builder_entry.py 与
scripts/build_builder_release.ps1 做静态断言（不真跑 PyInstaller）：

- 必须包含：builder-web/dist、builder_migrations、builder_alembic.ini、
  共享 XSD（dst_platform/acsm/schema）、2016/2020 双版本 Builder 插件；
- 不得捆入：Manager 前端（web/dist）、私有样本（sample/）、测试与工具链；
- 发布物命名独立：exe=dst-builder、集合=DSTBuilder、zip=dst-builder-v…；
  Manager 发布脚本（build_release.ps1）行为不受影响。

真实 PyInstaller 构建冒烟（解包敏感文件扫描）默认跳过，设置
``DST_BUILDER_PYINSTALLER_SMOKE=1`` 且本机可用 PyInstaller 时执行。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SPEC = ROOT / "packaging" / "dst-builder.spec"
ENTRY = ROOT / "packaging" / "builder_entry.py"
RELEASE_SCRIPT = ROOT / "scripts" / "build_builder_release.ps1"
MANAGER_RELEASE_SCRIPT = ROOT / "scripts" / "build_release.ps1"


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _normalized_spec_text() -> str:
    """`..\\x\\y` 的双反斜杠转义归一为 posix 路径，便于断言源/目标。"""
    return _spec_text().replace("\\\\", "/")


def _datas_entries() -> list[tuple[str, str]]:
    """解析 spec datas 的 (源, 目标) 二元组列表。"""
    match = re.search(r"datas=\[(.*?)\n    \]", _spec_text(), re.DOTALL)
    assert match, "未解析到 spec datas 块：请确认 datas 仍为缩进 4 的列表字面量"
    pairs = re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', match.group(1))
    assert pairs, "datas 块未解析到任何条目：解析正则失效"
    return [(source.replace("\\\\", "/"), target.replace("\\\\", "/")) for source, target in pairs]


# ---------------------------------------------------------------------------
# 必须随包：Builder 前端、迁移、共享 XSD、双版本插件
# ---------------------------------------------------------------------------


def test_spec_datas_include_builder_web_dist():
    assert any(source.endswith("builder-web/dist") for source, _ in _datas_entries()), (
        "packaging/dst-builder.spec datas 缺少 builder-web/dist：frozen 态壳无前端可挂载"
    )
    # 目标目录必须保持包内 builder-web/dist 路径（shell 的静态挂载按该路径发现）
    assert any(
        source.endswith("builder-web/dist") and target == "builder-web/dist"
        for source, target in _datas_entries()
    ), "builder-web/dist 的 datas 目标必须是 builder-web/dist"


def test_spec_datas_include_builder_migrations_and_alembic_ini():
    entries = _datas_entries()
    assert any("builder_migrations" in source for source, _ in entries), (
        "spec datas 缺少 builder_migrations：frozen 态项目库迁移必失败"
    )
    assert any(source.endswith("builder_alembic.ini") for source, _ in entries), (
        "spec datas 缺少 builder_alembic.ini：alembic Config 以该文件初始化"
    )


def test_spec_datas_include_pyproject_for_version_provenance():
    """pyproject.toml 必须随包：frozen 态版本回退唯一来源（写成果包 builder_version）。"""
    entries = _datas_entries()
    match = [
        (source, target)
        for source, target in entries
        if source.endswith("pyproject.toml")
    ]
    assert match, "spec datas 缺少 pyproject.toml：frozen 态版本探测会退化为 0.0.0.dev0 污染交接包"
    assert all(target == "." for _, target in match), (
        "pyproject.toml 的 datas 目标必须是资源根 .：runtime.app_version 按 resource_dir() 根读取"
    )


def test_spec_datas_include_shared_acsm_schema():
    entries = _datas_entries()
    assert any(
        source.endswith("dst_platform/acsm/schema") and target == "dst_platform/acsm/schema"
        for source, target in entries
    ), "spec datas 缺少 dst_platform/acsm/schema：frozen 态 XSD 校验必失败"


def test_release_script_carries_dual_version_builder_plugins():
    text = RELEASE_SCRIPT.read_text(encoding="utf-8")
    # 插件来源是 plugins/builder/autocad{2016,2020}（build_builder_plugins.ps1 的输出目录）
    assert re.search(r'plugins\\builder\\autocad', text) or "plugins/builder/autocad" in text, (
        "发布脚本未从 plugins/builder 复制 Builder 插件 DLL"
    )
    assert re.search(r'autocad\$v', text) or re.search(r"autocad\$v", text), (
        "发布脚本必须按版本循环复制 autocad$v 插件目录"
    )
    for version in ("2016", "2020"):
        assert version in text, f"发布脚本缺少 AutoCAD {version} 版本插件处理"
    assert "DstBuilder.AutoCAD.dll" in text, "发布脚本未校验 DstBuilder.AutoCAD.dll"
    assert "build_builder_plugins.ps1" in text, "发布脚本必须调用双版本 Builder 插件构建"


# ---------------------------------------------------------------------------
# 不得捆入：Manager 前端、私有样本、测试与构建产物
# ---------------------------------------------------------------------------


def test_spec_does_not_bundle_manager_web_frontend():
    entries = _datas_entries()
    assert any(source.endswith("builder-web/dist") for source, _ in entries), (
        "spec datas 未包含 builder-web/dist（前置条件缺失？）"
    )
    for source, target in entries:
        assert not re.search(r"(?<!builder-)web/dist", source), (
            f"spec datas 源 {source!r} 疑似 Manager 前端 web/dist：Builder 分发包不得携带"
        )
        assert not re.search(r"(?<!builder-)web/dist", target), (
            f"spec datas 目标 {target!r} 疑似 Manager 前端 web/dist：Builder 分发包不得携带"
        )


def test_spec_does_not_reference_private_sample_directory():
    for source, target in _datas_entries():
        assert "sample" not in source.lower(), f"spec datas 源引用 sample/：{source}"
        assert "sample" not in target.lower(), f"spec datas 目标引用 sample/：{target}"


@pytest.mark.parametrize(
    "forbidden",
    ["pytest", "tavily_cli", "playwright"],
)
def test_spec_excludes_dev_toolchain(forbidden):
    text = _spec_text()
    excludes_block = re.search(r"excludes=\[(.*?)\]", text, re.DOTALL)
    assert excludes_block, "未解析到 spec excludes 块"
    entries = re.findall(r'"([^"]+)"', excludes_block.group(1))
    assert forbidden in entries, f"spec excludes 应排除 {forbidden}（开发工具不进分发包）"


def test_release_script_does_not_touch_manager_artifacts():
    text = RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert "web" not in re.sub(r"#.*", "", text).replace("builder-web", ""), (
        "Builder 发布脚本疑似引用 Manager 前端 web/"
    )
    assert "DSTManager" not in text, "Builder 发布脚本不得输出 Manager 的 DSTBuilder 目录名"


# ---------------------------------------------------------------------------
# 命名独立：exe / 集合目录 / 分发 zip 均为 dst-builder 命名空间
# ---------------------------------------------------------------------------


def test_spec_names_exe_and_collect_independently():
    text = _spec_text()
    assert re.search(r'name\s*=\s*"dst-builder"', text), "EXE 名称必须是 dst-builder"
    assert re.search(r'COLLECT\(', text)
    assert re.search(r'name\s*=\s*"DSTBuilder"', text), "COLLECT 目录名必须是 DSTBuilder"
    assert not re.search(r'name\s*=\s*"dst-manager"', text), "spec 不得复用 dst-manager 命名"


def test_spec_disables_console_window():
    assert re.search(r"console\s*=\s*False", _spec_text()), (
        "spec 必须保持 console=False：双击启动无终端黑窗（对齐 Manager 决策）"
    )


def test_release_zip_named_dst_builder_with_version():
    text = RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"dst-builder-v", text), "分发 zip 必须以 dst-builder-v<版本> 命名"
    assert re.search(r"dst-builder-v\$Version-win64\.zip", text), (
        "分发 zip 命名必须是 dst-builder-v$Version-win64.zip"
    )
    # 版本号独立从 pyproject 读取，不读取 Manager 发布脚本的任何状态
    assert "pyproject.toml" in text


def test_release_script_output_directory_is_builder_owned():
    text = RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert "dist\\DSTBuilder" in text or "dist/DSTBuilder" in text, (
        "发布脚本必须组装 dist/DSTBuilder 目录"
    )


def test_manager_release_script_behavior_unchanged():
    """Manager 发布脚本保持既有 dst-manager 命名与 web/dist 前端（行为不变守护）。"""
    text = MANAGER_RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert "dst-manager-v$Version-win64.zip" in text
    assert re.search(r"dist\\DSTManager", text)
    assert "builder" not in text.lower()


# ---------------------------------------------------------------------------
# 入口契约：无参数 = 桌面壳；stdio 重定向先于重量级导入
# ---------------------------------------------------------------------------


def test_entry_redirects_frozen_stdio_before_heavy_imports():
    text = ENTRY.read_text(encoding="utf-8")
    assert "redirect_frozen_stdio" in text, "builder_entry.py 缺少无窗 stdio 重定向"
    heavy_imports = [
        text.index("from dst_builder.interfaces.shell import"),
        text.index("from dst_builder.interfaces.cli import"),
    ]
    assert all(text.index("redirect_frozen_stdio") < i for i in heavy_imports), (
        "重定向必须发生在导入 shell/cli（webview、uvicorn 日志接管）之前"
    )


def test_entry_launches_desktop_shell_without_arguments():
    text = ENTRY.read_text(encoding="utf-8")
    assert "run_desktop" in text, "无参数启动必须进入桌面壳 run_desktop"
    assert "run_desktop()" in text
    # 带参数时仍进入 CLI（serve/doctor 等子命令不受影响）
    assert "from dst_builder.interfaces.cli import app" in text


# ---------------------------------------------------------------------------
# 源码资源定位纪律：dst_builder 一律走 runtime.resource_dir
# ---------------------------------------------------------------------------


def test_builder_package_resolves_resources_only_via_runtime():
    """dst_builder 资源定位统一走 runtime.resource_dir；唯一例外是 runtime.py 自身。"""
    pattern = re.compile(r"Path\(__file__\)")
    package_dir = ROOT / "src" / "dst_builder"
    hits = [
        py.relative_to(package_dir).as_posix()
        for py in package_dir.rglob("*.py")
        if pattern.search(py.read_text(encoding="utf-8"))
    ]
    assert hits == ["runtime.py"], (
        f"dst_builder 内 Path(__file__) 资源定位：{hits}；"
        "请统一改走 dst_builder.runtime.resource_dir（frozen 双路径）"
    )


# ---------------------------------------------------------------------------
# 真实构建冒烟（默认跳过；DST_BUILDER_PYINSTALLER_SMOKE=1 时执行）
# ---------------------------------------------------------------------------

SMOKE_ENABLED = os.environ.get("DST_BUILDER_PYINSTALLER_SMOKE") == "1"


@pytest.mark.skipif(not SMOKE_ENABLED, reason="设置 DST_BUILDER_PYINSTALLER_SMOKE=1 以执行真实 PyInstaller 构建冒烟")
@pytest.mark.skipif(sys.platform != "win32", reason="dst-builder.spec 面向 Windows 分发")
def test_pyinstaller_build_and_unpacked_scan(tmp_path: Path):
    """真实构建 onedir 产物并解包扫描敏感/禁入文件。"""
    if shutil.which("pyinstaller") is None and shutil.which("pyinstaller.exe") is None:
        pytest.skip("PyInstaller 不在 PATH")
    for prerequisite in (
        ROOT / "builder-web" / "dist" / "index.html",
        ROOT / "builder_migrations" / "env.py",
        ROOT / "src" / "dst_platform" / "acsm" / "schema" / "acsm-v1.xsd",
    ):
        if not prerequisite.is_file():
            pytest.skip(f"打包前置条件缺失：{prerequisite}")

    dist_path = tmp_path / "dist"
    work_path = tmp_path / "build"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(dist_path),
            "--workpath",
            str(work_path),
            str(SPEC),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert result.returncode == 0, f"PyInstaller 构建失败：\n{result.stdout}\n{result.stderr}"

    app_dir = dist_path / "DSTBuilder"
    assert app_dir.is_dir(), f"产物目录缺失：{app_dir}"
    assert (app_dir / "dst-builder.exe").is_file(), "dst-builder.exe 缺失"
    internal = app_dir / "_internal"
    # 必须随包
    for required in (
        internal / "builder_alembic.ini",
        internal / "builder_migrations" / "versions",
        internal / "builder-web" / "dist" / "index.html",
        internal / "dst_platform" / "acsm" / "schema" / "acsm-v1.xsd",
        # 版本兜底来源：frozen 态 builder_version provenance 依赖它
        internal / "pyproject.toml",
    ):
        assert required.exists(), f"打包产物缺少 {required}"

    # 敏感/禁入文件扫描
    all_paths = [p.relative_to(app_dir).as_posix().lower() for p in app_dir.rglob("*")]
    assert not any(".env" in Path(p).name for p in all_paths), "产物包含 .env 文件"
    assert not any(p.startswith("web/") for p in all_paths), "产物捆入 Manager 前端 web/dist"
    assert not any("/sample/" in f"/{p}" or p.startswith("sample/") for p in all_paths), "产物包含 sample/"
    for segment in ("/bin/", "/obj/"):
        assert not any(segment in f"/{p}" for p in all_paths), f"产物包含 MSBuild 中间目录 {segment}"
    assert not any(p.endswith((".log", ".pyc.orig")) for p in all_paths)
    # 不携带测试与插件源码
    assert not any(p.startswith("tests/") for p in all_paths)
    assert not any("plugins/src" in p for p in all_paths)
    # 密钥文本轻量扫描（限于打包自带的文本资源）
    for text_file in internal.rglob("*"):
        if text_file.is_file() and text_file.suffix.lower() in {".ini", ".toml", ".json", ".yaml", ".yml", ".txt"}:
            content = text_file.read_text(encoding="utf-8", errors="ignore")
            assert "-----BEGIN" not in content, f"{text_file} 疑似包含私钥"
