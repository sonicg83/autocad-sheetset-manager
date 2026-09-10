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


# ---------------------------------------------------------------------------
# PLAN-DM-021 Task 12（I18N-01/18）：生产 Web 产物多语言静态守护。
# 打包只 datas web/dist，不打包 web/src；两套语言资源必须已随构建嵌入 JS 产物，
# 产物不得回指源码目录（frozen 态没有 web/src，任何源码路径依赖都是运行期断链）。
# ---------------------------------------------------------------------------

WEB_DIST = ROOT / "web" / "dist"
LOCALES_DIR = ROOT / "web" / "src" / "i18n" / "locales"
I18N_LOCALES = ("zh-CN", "en-US")
I18N_DOMAINS = ("common", "errors", "jobs", "properties", "revisions", "settings", "shell", "sheets")


def _bundle_text() -> str:
    """读取 web/dist 全部 JS 产物文本；产物缺失时按打包前置条件报错。"""
    js_files = sorted((WEB_DIST / "assets").glob("*.js"))
    assert js_files, "web/dist/assets 缺少 JS 产物：打包前必须先 `npm --prefix web run build`（spec datas 依赖 web/dist）"
    return "".join(js.read_text(encoding="utf-8") for js in js_files)


def _domain_literals(locale: str, domain: str) -> list[str]:
    """提取语言资源文件中的字符串字面量（排除插值模板标记 '@' 开头与转义片段）。"""
    source = (LOCALES_DIR / locale / f"{domain}.ts").read_text(encoding="utf-8")
    return [
        value
        for value in re.findall(r'"([^"\\\n]{6,})"', source)
        if not value.startswith("@")
    ]


def test_spec_datas_bundles_web_dist():
    """spec datas 必须包含 web\\dist：两套语言资源随产物整体入包（I18N-01）。"""
    assert re.search(r"web\\+dist", _spec_text()), (
        "packaging/dst-manager.spec 的 datas 缺少 web\\dist 条目："
        "frozen 态 api.py 的 StaticFiles 将无前端可挂载"
    )


def test_production_bundle_contains_both_locales():
    """生产 JS 产物必须同时嵌入 zh-CN 与 en-US 全部 8 个域的语言资源（I18N-01/18）。"""
    bundle = _bundle_text()
    for locale in I18N_LOCALES:
        for domain in I18N_DOMAINS:
            literals = _domain_literals(locale, domain)
            assert literals, f"{locale}/{domain}.ts 未扫描到可断言字面量：请确认提取正则仍有效"
            marker = max(literals, key=len)
            assert marker in bundle, (
                f"生产 Web 产物缺少 {locale}/{domain} 语言资源（基准文案 {marker!r} 不在 dist JS 中）："
                "语言资源必须随构建嵌入 bundle，不得依赖源码目录或运行期外链"
            )


def test_production_bundle_does_not_reference_source_tree():
    """dist 产物不得回指 web/src / node_modules / 绝对源码路径（frozen 态无源码目录）。"""
    bundle = _bundle_text()
    for needle in ("web/src", "/@fs/", "node_modules"):
        assert needle not in bundle, f"生产 Web 产物引用了源码目录标记 {needle!r}：frozen 态会断链"
    assert not re.search(r"[A-Za-z]:[\\/](?:Users|Windows|workspace)", bundle), (
        "生产 Web 产物包含绝对盘符路径：疑似把源码目录地址打进 bundle"
    )


def test_i18n_resources_statically_bundled_not_runtime_fetched():
    """i18n/index.ts 必须静态 import 全部 16 个域资源；不得运行期 fetch/动态 import 语言文件。"""
    index_text = (ROOT / "web" / "src" / "i18n" / "index.ts").read_text(encoding="utf-8")
    for locale in I18N_LOCALES:
        for domain in I18N_DOMAINS:
            assert f'locales/{locale}/{domain}' in index_text, (
                f"i18n/index.ts 缺少 locales/{locale}/{domain} 的静态导入："
                "唯一 i18n 实例必须在构建期装配两套同构资源（I18N-01）"
            )
    assert not re.search(r"import\(\s*[\"'`]\./locales", index_text), (
        "i18n/index.ts 出现 locales 动态 import：语言资源会脱离主 bundle，frozen 产物可能缺语言"
    )
    assert not re.search(r"fetch\([^)]*locales", index_text), (
        "i18n/index.ts 运行期 fetch 语言资源：违背构建期装配唯一实例的架构约束"
    )


# ---------------------------------------------------------------------------
# PLAN-DM-020 Task 12（EP-01/SC-09 打包守护）：随包清单、openpyxl 收集与许可证
# 追溯、固定索引资源存在、不扫描用户扩展目录。
# manifest.py 经 importlib.resources 按 `dst_manager/extensions/builtin/...`
# 包内路径加载清单；frozen 态该资源必须以「包内相对路径」进入 spec datas，
# 否则 ExtensionRegistry.discover() 在打包后必然降级为占位 FAILED 描述符。
# ---------------------------------------------------------------------------

MANIFEST_RESOURCE = "dst_manager/extensions/builtin/sheet_catalog/manifest.yaml"
MANIFEST_FILE = ROOT / "src" / MANIFEST_RESOURCE
INDEX_FILE = ROOT / "src" / "dst_manager" / "extensions" / "builtin" / "index.py"
RUNTIME_FILE = ROOT / "src" / "dst_manager" / "application" / "extensions" / "runtime.py"


def _normalized_spec_text() -> str:
    """spec 文本中 `..\\x\\y` 的双反斜杠转义归一为 posix 路径，便于断言源/目标。"""
    return _spec_text().replace("\\\\", "/")


def test_builtin_manifest_yaml_exists():
    """随包清单真实存在于源码树，是 spec datas 能打进去的前提。"""
    assert MANIFEST_FILE.is_file(), "内置扩展 manifest.yaml 缺失：固定索引引用的资源必须先在源码树"


def test_spec_datas_include_builtin_manifest_yaml():
    """spec datas 必须把 manifest.yaml 打进包内同路径（frozen 态 importlib.resources 可定位）。"""
    normalized = _normalized_spec_text()
    assert f"src/{MANIFEST_RESOURCE}" in normalized, (
        "packaging/dst-manager.spec 的 datas 缺少内置扩展 manifest.yaml 源条目："
        "frozen 态 discover() 将因清单不可读降级为占位 FAILED"
    )
    # PyInstaller datas 的二元组是 (源文件, 目标目录)：文件被复制进目标目录并保留
    # basename。目标若写成 manifest.yaml 结尾会被当作目录名，产出
    # manifest.yaml/manifest.yaml 双层路径，frozen 态清单读取必然失败
    # （实测 build_release 后在 dist 树复核过两种形态）。
    entry = re.search(r'\("([^"]*manifest\.ya?ml)",\s*"([^"]+)"\)', _spec_text())
    assert entry, "未找到 manifest.yaml 的 datas 条目：请确认 datas 列表结构"
    source = entry.group(1).replace("\\\\", "/")
    target = entry.group(2).replace("\\\\", "/")
    assert source == f"../src/{MANIFEST_RESOURCE}", f"manifest.yaml datas 源路径错误：{source}"
    assert target == "dst_manager/extensions/builtin/sheet_catalog", (
        f"manifest.yaml datas 目标必须是包内目录 dst_manager/extensions/builtin/sheet_catalog"
        f"（实际 {target}）：目标目录下文件名固定为 manifest.yaml，落到别处等价于缺失"
    )


def test_openpyxl_collected_with_license_provenance():
    """openpyxl 必须可收集（生产依赖 + 未被排除）且许可证/版本记录可追溯。"""
    import tomllib

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"openpyxl>=', pyproject), "openpyxl 未声明为生产依赖：打包后 XLSX 生成将 ImportError"
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock["package"]}
    assert "openpyxl" in packages, "uv.lock 缺少 openpyxl 条目：版本来源不可追溯"
    root = packages.get("autocad-sheetset")
    assert root is not None and any(dep["name"] == "openpyxl" for dep in root.get("dependencies", [])), (
        "openpyxl 不在根包生产依赖组：会被误判为可裁剪的传递依赖"
    )
    spec = _spec_text()
    assert not re.search(r"excludes\s*=\s*\[[^\]]*openpyxl", spec, re.DOTALL), "spec excludes 排除了 openpyxl"
    # 许可证记录可追溯：spec datas 必须携带 LICENSE 与 pyproject.toml
    # （设置中心 /api/about 的 frozen 态协议全文与版本兜底来源，spec 既有注释）
    normalized = _normalized_spec_text()
    assert '../LICENSE' in normalized and '../pyproject.toml' in normalized, (
        "spec datas 缺少 LICENSE/pyproject.toml：许可证与版本记录在分发包内不可追溯"
    )


def test_fixed_index_resources_exist_and_are_packaged():
    """固定索引列出的每个清单资源必须在源码树存在且被 spec datas 覆盖。"""
    resources = re.findall(r'manifest_resource="([^"]+)"', INDEX_FILE.read_text(encoding="utf-8"))
    assert resources, "固定索引未列出任何随包清单资源：扫描正则失效或索引被清空"
    normalized = _normalized_spec_text()
    for resource in resources:
        assert (ROOT / "src" / resource).is_file(), f"固定索引资源 {resource} 在源码树缺失"
        assert f"src/{resource}" in normalized, f"固定索引资源 {resource} 未进入 spec datas：frozen 态清单加载必失败"


def test_spec_does_not_package_or_scan_user_extension_directories():
    """分发包只携带固定索引资源：datas 条目不含用户可写目录，运行期发现不扫描文件系统。"""
    datas_block = re.search(r"datas=\[(.*?)\n    \]", _spec_text(), re.DOTALL)
    assert datas_block, "未解析到 spec datas 块：请确认 datas 列表结构仍为缩进 4 的列表字面量"
    entries = [item.lower().replace("\\\\", "/") for item in re.findall(r'"([^"]+)"', datas_block.group(1))]
    assert entries, "datas 块为空：解析正则失效"
    for marker in ("localappdata", "appdata/", "site-packages", "extensions/user", "user_extensions"):
        assert not any(marker in entry for entry in entries), (
            f"spec datas 疑似打包用户可写目录标记 {marker!r}：包中不得携带用户扩展目录"
        )
    runtime = RUNTIME_FILE.read_text(encoding="utf-8")
    for call in ("glob(", "iterdir(", "listdir(", "scandir("):
        assert call not in runtime, (
            f"runtime.py 出现 {call}：扩展发现必须只经 BUILTIN_EXTENSION_INDEX 固定索引（ARCH-DM-006 §4.1），"
            "不得扫描文件系统或用户扩展目录"
        )
