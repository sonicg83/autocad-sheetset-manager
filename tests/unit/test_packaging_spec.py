"""打包 spec 静态守护：acsm-v1.xsd 必须随分发包打入（防回归）。

守护意图：
- PyInstaller onedir 打包后 `__file__` 指向 `_internal` 内的 .pyc，代码里
  `Path(__file__)... / "某资源"` 定位的静态资源必须同时出现在
  `packaging/dst-manager.spec` 的 `datas`（或改走 `runtime.resource_dir`），
  否则真实 DST 加载（load_acsm → validate_schema）在打包后必崩。
- 本测试不运行 PyInstaller（太慢），只做静态断言：spec datas 覆盖
  `acsm_xml/schema`；`src/dst_manager` 中新增 `Path(__file__)` 资源定位时
  必须先补齐 spec datas 或改走 `runtime.resource_dir`（允许清单见下）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SPEC = ROOT / "packaging" / "dst-manager.spec"
SCHEMA_FILE = (
    ROOT / "src" / "dst_manager" / "infrastructure" / "acsm_xml" / "schema" / "acsm-v1.xsd"
)

# 允许使用 `Path(__file__)` 的文件（相对 src/dst_manager 的 posix 相对路径，
# 按 basename 匹配会误放行任意子包下的同名文件）。
# - infrastructure/acsm_xml/contract.py 的 schema 资源已由 spec datas 覆盖（下方断言）；
# - interfaces/api.py / infrastructure/persistence/database.py 走 runtime.resource_dir
#   （源码树 / sys._MEIPASS 两态）；
# - runtime.py 自身 `_DEV_ROOT` 只用于源码树路径、无打包资源。
# 新增 `Path(__file__)` 资源定位必须：登记在此 + 保证 spec datas / resource_dir 覆盖。
# 覆盖边界：扫描正则只识别 `Path(__file__)` 字面写法；`os.path.dirname(__file__)`
# 等等价写法不在守护范围内，新增资源定位请统一用 `Path(__file__)` 或 resource_dir。
ALLOWED_FILES = {
    "infrastructure/acsm_xml/contract.py",
    "interfaces/api.py",
    "infrastructure/persistence/database.py",
    "runtime.py",
}


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_schema_xsd_exists_in_source_tree():
    """XSD 真实存在于源码树，是 spec datas 能打进去的前提。"""
    assert SCHEMA_FILE.is_file(), "acsm-v1.xsd 缺失：请确认 schema 目录仍在源码树"


def test_spec_datas_include_acsm_xml_schema():
    """spec datas 必须显式包含 acsm_xml/schema 路径条目（源文件路径，反斜杠转义）。"""
    text = _spec_text()
    # 文件内双反斜杠转义（acsm_xml\\schema 字面两杠），正则兼容单/双杠写法
    assert re.search(r"acsm_xml\\+schema", text), (
        "packaging/dst-manager.spec 的 datas 缺少 acsm_xml\\schema 条目："
        "frozen 态 validate_schema 将因找不到 XSD 崩溃"
    )


def test_no_unlisted_file_resolves_resources_via___file__():
    """扫描守护：src/dst_manager 内 `Path(__file__)` 资源定位必须登记且被 spec 覆盖。"""
    pattern = re.compile(r"Path\(__file__\)")
    hits = [py for py in (ROOT / "src" / "dst_manager").rglob("*.py") if pattern.search(py.read_text(encoding="utf-8"))]
    assert hits, "未发现任何 Path(__file__) 定位：请确认扫描正则仍有效"
    for py in hits:
        rel = py.relative_to(ROOT / "src" / "dst_manager").as_posix()
        assert rel in ALLOWED_FILES, (
            f"{py.relative_to(ROOT)} 通过 Path(__file__) 定位资源，但 spec datas 未覆盖："
            "请补 packaging/dst-manager.spec 的 datas 条目，或改走 runtime.resource_dir"
        )
    # contract.py 的 schema 资源必须已由 spec datas 覆盖，且 datas 目标路径
    # 与 frozen 态 _load_schema() 的 __file__ 相对定位逐级吻合
    # （frozen __file__ = _internal/dst_manager/infrastructure/acsm_xml/contract.pyc）。
    text = _spec_text()
    assert "dst_manager/infrastructure/acsm_xml/schema" in text, (
        "spec datas 的目标路径须为 dst_manager/infrastructure/acsm_xml/schema："
        "frozen 态 schema/ 目录必须落在 contract.pyc 同级才能被 _load_schema() 找到"
    )


def test_spec_disables_console_window():
    """console=False（ARCH-DM-002 §3.3）：双击 exe 无终端黑窗，输出走日志文件通道。"""
    assert re.search(r"console\s*=\s*False", _spec_text()), (
        "spec 必须保持 console=False：壳与 Worker 的输出依赖 entry.py 的 stdio 重定向，"
        "改回 True 前需先修订 ARCH-DM-002 的日志可观察决策"
    )


def test_entry_redirects_windowless_stdio_before_imports():
    """entry.py 必须在导入业务代码（含 uvicorn 日志接管）之前完成 desktop/worker 的 stdio 重定向。"""
    text = (ROOT / "packaging" / "entry.py").read_text(encoding="utf-8")
    assert "redirect_frozen_stdio" in text, "entry.py 缺少无窗 stdio 重定向：console=False 下日志会全部丢失"
    assert text.index("redirect_frozen_stdio") < text.index("from dst_manager.interfaces.cli import app"), (
        "重定向必须发生在导入 dst_manager.interfaces.cli 之前，否则 uvicorn 等库在导入期绑定的 stderr 已指向丢失的控制台"
    )
