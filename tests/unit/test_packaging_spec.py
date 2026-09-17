"""打包 spec 静态守护：acsm-v1.xsd 必须随分发包打入（防回归）。

守护意图：
- PyInstaller onedir 打包后 `__file__` 指向 `_internal` 内的 .pyc，代码里
  `Path(__file__)... / "某资源"` 定位的静态资源必须同时出现在
  `packaging/dst-manager.spec` 的 `datas`（或改走 `runtime.resource_dir`），
  否则真实 DST 加载（load_acsm → validate_schema）在打包后必崩。
- 本测试不运行 PyInstaller（太慢），只做静态断言：spec datas 覆盖
  `dst_platform/acsm/schema`（PLAN-DB-001 Task 6 起 XSD 所有权在 dst_platform）；
  `src` 各包中新增 `Path(__file__)` 资源定位时必须先补齐 spec datas 或改走
  `runtime.resource_dir`（允许清单见下）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
SPEC = ROOT / "packaging" / "dst-manager.spec"
# PLAN-DB-001 Task 6：XSD 所有权随 contract 实现迁至 dst_platform/acsm/schema。
SCHEMA_FILE = ROOT / "src" / "dst_platform" / "acsm" / "schema" / "acsm-v1.xsd"

# 允许使用 `Path(__file__)` 的文件（相对各包根的 posix 相对路径，
# 按 basename 匹配会误放行任意子包下的同名文件）。
# - dst_platform/acsm/contract.py 的 schema 资源已由 spec datas 覆盖（下方断言）；
# - dst_manager interfaces/api.py / infrastructure/persistence/database.py 走
#   runtime.resource_dir（源码树 / sys._MEIPASS 两态）；
# - dst_manager/runtime.py 自身 `_DEV_ROOT` 只用于源码树路径、无打包资源。
# 新增 `Path(__file__)` 资源定位必须：登记在此 + 保证 spec datas / resource_dir 覆盖。
# 覆盖边界：扫描正则只识别 `Path(__file__)` 字面写法；`os.path.dirname(__file__)`
# 等等价写法不在守护范围内，新增资源定位请统一用 `Path(__file__)` 或 resource_dir。
ALLOWED_FILES = {
    "dst_manager": {
        "interfaces/api.py",
        "infrastructure/persistence/database.py",
        "runtime.py",
    },
    "dst_platform": {
        "acsm/contract.py",
    },
}


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_schema_xsd_exists_in_source_tree():
    """XSD 真实存在于源码树，是 spec datas 能打进去的前提。"""
    assert SCHEMA_FILE.is_file(), "acsm-v1.xsd 缺失：请确认 schema 目录仍在源码树"


def test_spec_datas_include_acsm_xml_schema():
    """spec datas 必须显式包含 dst_platform/acsm/schema 路径条目（源文件路径，反斜杠转义）。"""
    text = _spec_text()
    # 文件内双反斜杠转义（acsm\\schema 字面两杠），正则兼容单/双杠写法
    assert re.search(r"dst_platform\\+acsm\\+schema", text), (
        "packaging/dst-manager.spec 的 datas 缺少 dst_platform\\acsm\\schema 条目："
        "frozen 态 validate_schema 将因找不到 XSD 崩溃"
    )
    # Manager 侧历史路径不得回潮：实现已迁 dst_platform，Manager 只剩薄 re-export
    assert not re.search(r"acsm_xml\\+schema", text), (
        "spec datas 仍引用已迁移的 dst_manager acsm_xml\\schema：XSD 所有权在 dst_platform/acsm/schema"
    )


def test_no_unlisted_file_resolves_resources_via___file__():
    """扫描守护：src 各包内 `Path(__file__)` 资源定位必须登记且被 spec 覆盖。"""
    pattern = re.compile(r"Path\(__file__\)")
    for package, allowed in ALLOWED_FILES.items():
        package_dir = ROOT / "src" / package
        hits = [py for py in package_dir.rglob("*.py") if pattern.search(py.read_text(encoding="utf-8"))]
        assert hits, f"src/{package} 未发现任何 Path(__file__) 定位：请确认扫描正则仍有效"
        for py in hits:
            rel = py.relative_to(package_dir).as_posix()
            assert rel in allowed, (
                f"{py.relative_to(ROOT)} 通过 Path(__file__) 定位资源，但 spec datas 未覆盖："
                "请补 packaging/dst-manager.spec 的 datas 条目，或改走 runtime.resource_dir"
            )
    # contract.py 的 schema 资源必须已由 spec datas 覆盖，且 datas 目标路径
    # 与 frozen 态 _load_schema() 的 __file__ 相对定位逐级吻合
    # （frozen __file__ = _internal/dst_platform/acsm/contract.pyc）。
    text = _spec_text()
    assert "dst_platform/acsm/schema" in text, (
        "spec datas 的目标路径须为 dst_platform/acsm/schema："
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
CATALOG_SETTINGS_FILE = (
    ROOT / "src" / "dst_manager" / "extensions" / "builtin" / "sheet_catalog" / "settings.py"
)
HOST_FILE = ROOT / "web" / "src" / "components" / "settings" / "ExtensionSettingsHost.vue"

# 随包清单不得出现可执行入口/模块定位字段（ARCH-DM-006 §4.2）：这些键的值必然是
# Python 模块名、类名、脚本路径或命令，一旦允许就把「数据契约」变成隐式代码入口。
MANIFEST_FORBIDDEN_KEYS = {
    "module",
    "module_name",
    "module_path",
    "class",
    "class_name",
    "script",
    "script_path",
    "command",
    "entry_point",
    "entrypoint",
    "provider",
    "settings_provider",
    "import",
    "import_path",
    "python_path",
    "executable",
    "path",
    "file",
}

# 键名按词段（下划线/连字符 + 驼峰边界）切开后的**词段**黑名单：`provider_class`、
# `modulePath`、`exec_path`、`handler_class` 这类变体在精确名匹配下会漏过，而它们
# 的语义与禁用键完全相同。按词段（而非子串）匹配：`description_key` 的词段是
# `description`/`key`，不会被 `script` 子串误伤。
MANIFEST_FORBIDDEN_KEY_TOKENS = (
    "module",
    "class",
    "script",
    "command",
    "entry",
    "point",
    "handler",
    "provider",
    "import",
    "executable",
    "exec",
    "python",
    "path",
    "file",
)


def _key_segments(key: str) -> tuple[str, ...]:
    """把键名切成可比对的词段：`modulePath` -> (module, path)，`exec_path` -> (exec, path)。"""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key)
    segments = re.split(r"[^A-Za-z0-9]+", spaced)
    return tuple(segment.casefold() for segment in segments if segment)
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


# ---------------------------------------------------------------------------
# PLAN-DM-025 任务 9（步骤 1）：扩展全局设置框架的打包守护。
# 设置语义（默认值/迁移/校验/解析）由 Provider 独占，Provider 与工厂一样是
# 固定索引里的**编译期引用**；清单只声明呈现。frozen 态下 Provider 模块被
# 排除、或 custom 呈现的路由键脱离前端编译期白名单，都会让设置入口静默失效。
# 扫描口径说明：索引/清单用 AST 与 YAML 解析（识别等价写法），前端 .vue 含
# TypeScript 语法无法用 AST，故只用文本正则做「不得出现」类断言。
# ---------------------------------------------------------------------------


def _manifest_data() -> dict:
    """解析随包清单数据（PyYAML，与 manifest.py 同一加载语义）。"""
    return yaml.safe_load(MANIFEST_FILE.read_text(encoding="utf-8"))


def _walk_manifest(node, path: tuple[str, ...] = ()):
    """深度遍历清单，产出 (键路径, 值) 对：键与值两侧都要守护。"""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + (str(key),), value
            yield from _walk_manifest(value, path + (str(key),))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk_manifest(item, path + (str(index),))


def _module_level_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """模块级 `from <module> import <name>`：返回 本地名 -> (模块点分路径, 原名)。

    保留 `as` 别名映射：`from m import f as g` 时本地名是 `g`，但目标模块里被定义
    的符号是 `f`。只记本地名会让合法的别名导入被误判为「符号不存在」。
    """
    imported: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.module, alias.name)
    return imported


def _bound_expression(node: ast.stmt, name: str) -> ast.expr | None:
    """该语句是否把模块级名字 `name` 绑定到某个表达式；是则返回右值。"""
    if isinstance(node, ast.Assign):
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value
        return None
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
    ):
        return node.value
    return None


def _module_level_binding(module: str, name: str) -> str:
    """目标模块里模块级符号 `name` 的绑定形态。

    返回值：`missing`、`literal`（绑定到字符串/数字等字面量）、`call`（构造或调用
    结果）、`name`（指向另一个模块级名字）、`def`（函数/类定义）、`assign`（其他
    赋值）。`literal` 必须被守护拒绝：把 Provider 登记成模块级字符串常量，静态分析
    与打包收集都跟随不了，等价于运行期按名解析。
    """
    target = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
    if not target.is_file():
        return "missing"
    tree = ast.parse(target.read_text(encoding="utf-8"))
    for node in tree.body:
        bound = _bound_expression(node, name)
        if bound is None:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and node.name == name:
                return "def"
            continue
        if isinstance(bound, ast.Constant):
            return "literal"
        if isinstance(bound, ast.Call):
            return "call"
        if isinstance(bound, ast.Name):
            return "name"
        return "assign"
    return "missing"


def _module_level_name_target(module: str, name: str) -> tuple[str, str] | None:
    """模块级 `name` 的重导出目标：`name = <其他名字>` 时给出该名字的解析坐标。

    两种目标都要跟随：指向本模块别名的（继续在同一模块内追踪），以及指向导入
    符号的（跳到被导入模块里的原名）。`AnnAssign`（`x: T = y`）与 `Assign` 的
    形态必须同等处理，否则生成器为空会抛裸 `StopIteration` 而不是给出诊断。
    """
    target = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
    if not target.is_file():
        return None
    tree = ast.parse(target.read_text(encoding="utf-8"))
    for node in tree.body:
        bound = _bound_expression(node, name)
        if isinstance(bound, ast.Name):
            imported = _module_level_imports(tree)
            if bound.id in imported:
                return imported[bound.id]
            return (module, bound.id)
    return None


def _transitive_literal(module: str, name: str, *, max_hops: int = 4) -> str | None:
    """沿模块级重导出链追踪 `name`，返回第一个字面量落点的可读描述；否则 None。

    链路可以任意长：`X = Y`、`Y = "<模块:符号>"` 这类「本地常量再导出」与
    「导入别的模块里的再导出」都要看穿。只跟一跳、且只跟「内层名是导入符号」
    的写法会让字符串入口从第二跳起静默绕过守护。
    """
    seen: set[tuple[str, str]] = set()
    current: tuple[str, str] | None = (module, name)
    for _ in range(max_hops):
        if current is None or current in seen:
            return None
        seen.add(current)
        kind = _module_level_binding(*current)
        if kind == "literal":
            return f"{current[0]}.{current[1]}"
        if kind != "name":
            return None
        current = _module_level_name_target(*current)
    return None


def test_fixed_index_registers_factory_and_provider_as_compile_time_references():
    """固定索引的 factory/settings_provider 必须是模块级导入的标识符，不得是字符串。

    守护意图（ARCH-DM-006 §4.1/§8.1）：宿主绝不从清单或字符串导入模块。若把
    Provider 写成字符串路径，frozen 态只能靠运行期动态导入解析——那就是「清单
    携带可执行入口」的变体，且打包分析无法跟随，Provider 会静默丢失（设置 CRUD
    降级为不可用而不是报错）。
    """
    source = INDEX_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    entries = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BuiltinExtensionEntry"
    ]
    assert entries, "固定索引未找到 BuiltinExtensionEntry 调用：请确认索引仍以构造器登记条目"
    imported = _module_level_imports(tree)
    seen = set()
    for entry in entries:
        for keyword in entry.keywords:
            if keyword.arg not in ("factory", "settings_provider"):
                continue
            seen.add(keyword.arg)
            value = keyword.value
            assert isinstance(value, (ast.Name, ast.Attribute)), (
                f"固定索引 {keyword.arg}= 必须是编译期引用（模块级导入的标识符），"
                f"实际是 {type(value).__name__}：字符串形式的入口等价于运行期动态加载"
            )
            if isinstance(value, ast.Name):
                resolved = imported.get(value.id)
                assert resolved, f"固定索引 {keyword.arg}={value.id} 不是模块级导入的标识符"
                module, original = resolved
                kind = _module_level_binding(module, original)
                assert kind != "missing", (
                    f"{module} 未在模块级定义 {original}：索引引用的编译期符号必须真实存在"
                )
                assert kind != "literal", (
                    f"{module}.{original} 绑定到字面量（字符串/数字）：入口必须是编译期可跟随的"
                    "构造结果或函数/类，字符串形式的入口等价于运行期按名动态加载"
                )
                # 重导出链：`X = Y`、`X = Y = Z`、`X = 导入符号` 都要追到落点，
                # 各模块内再导出很常见，字符串入口正是从第二跳起容易漏掉。
                literal_origin = _transitive_literal(module, original)
                assert literal_origin is None, (
                    f"{module}.{original} 的重导出链最终落在字面量 {literal_origin}："
                    "入口必须是编译期可跟随的构造结果或函数/类，字符串形式的入口等价于"
                    "运行期按名动态加载"
                )
    assert {"factory", "settings_provider"} <= seen, (
        "固定索引未同时登记 factory 与 settings_provider：设置语义必须由 Provider 在"
        "编译期登记（ARCH-DM-006 §8.1），不得回退到按扩展 ID 的宿主特判"
    )
    for forbidden in ("importlib", "__import__", "import_module"):
        assert not re.search(rf"\b{re.escape(forbidden)}\b", source), (
            f"固定索引出现 {forbidden}：白名单索引不得按名动态加载（ARCH-DM-006 §4.1）"
        )


def test_builtin_manifest_carries_no_executable_entry_or_url_fields():
    """随包清单是数据契约：不得携带 module/class/script/command/url 一类字段。

    守护意图（ARCH-DM-006 §4.2）：清单只声明身份、能力、权限与呈现；扩展实例与
    设置 Provider 由固定索引的编译期引用创建，URL 会破坏离线可审计与无动态加载。
    """
    data = _manifest_data()
    assert data.get("extension_type") == "builtin", "清单解析异常：extension_type 不再是 builtin"
    for path, _ in _walk_manifest(data):
        # 词段切分必须在原键名上做（`modulePath` → module/path）：先 casefold 会把
        # 驼峰边界抹平成一个词段，`modulePath`/`providerClass` 一类变体就会漏判。
        key = str(path[-1]).casefold()
        normalized_segments = _key_segments(str(path[-1]))
        assert key not in MANIFEST_FORBIDDEN_KEYS, (
            f"随包清单出现可执行入口字段 {'.'.join(path)}：清单是数据契约，"
            "扩展实例与 Provider 只能由固定索引的编译期引用创建"
        )
        hits = [token for token in MANIFEST_FORBIDDEN_KEY_TOKENS if token in normalized_segments]
        assert not hits, (
            f"随包清单字段 {'.'.join(path)} 命中入口词段 {hits}："
            "`provider_class`/`modulePath`/`exec_path` 一类变体与禁用键语义相同，同样不得出现"
        )
    for path, value in _walk_manifest(data):
        if isinstance(value, str):
            assert "://" not in value, (
                f"随包清单字段 {'.'.join(path)} 含外部地址：清单不得携带 URL（离线可审计）"
            )


def test_custom_settings_route_hits_frontend_compile_time_whitelist():
    """custom 呈现的路由键必须在前端编译期白名单里，且前端不得动态 import 组件。

    守护意图（ARCH-DM-006 §8.2 / SPEC-DM-011 SC-17）：未知 route_key 必须
    fail-closed。路由键脱离白名单时，用户点「配置」只会看到稳定诊断；若为了
    "修好"它而改成 import(route_key) 动态加载，则等于把服务端字符串当代码入口。
    """
    contribution = _manifest_data()["settings_contribution"]
    host = HOST_FILE.read_text(encoding="utf-8")
    assert "CUSTOM_SETTINGS_PANELS" in host, (
        "ExtensionSettingsHost.vue 未找到 custom 白名单常量：custom 呈现必须经编译期白名单解析"
        "（计划正文里的旧名 CUSTOM_EXTENSION_SETTINGS_COMPONENTS 已废弃）"
    )
    assert contribution["presentation"] == "custom", (
        "本守护针对图纸目录的 custom 呈现：清单呈现类型变化时请同步改断言口径"
    )
    route_key = contribution["route_key"]
    assert f'"{route_key}"' in host or f"'{route_key}'" in host, (
        f"前端白名单未登记 route_key {route_key!r}：声明 custom 的扩展点「配置」会 fail-closed"
    )
    assert not re.search(r"\bimport\s*\(|\bimport\s*\.\s*meta", host), (
        "ExtensionSettingsHost.vue 出现动态 import / import.meta：custom 组件解析必须是编译期事实"
        "（ARCH-DM-006 §8.2），不得按服务端字符串加载模块"
    )
    assert "defineAsyncComponent" not in host, (
        "ExtensionSettingsHost.vue 使用 defineAsyncComponent：组件解析变成运行期事实，"
        "与编译期白名单 fail-closed 契约冲突"
    )


def test_spec_excludes_and_pathex_keep_builtin_extension_provider_packaged():
    """spec 不得排除 dst_manager 包，且 ..\\src 必须在 pathex 上。

    守护意图：Provider 是编译期引用，PyInstaller 只能沿静态导入收集；若 excludes
    排掉 dst_manager.extensions.builtin（或其子模块），frozen 态设置校验与读写全部
    失效，而源码树测试不会有任何察觉。
    """
    text = _spec_text()
    excludes_block = re.search(r"excludes=\[(.*?)\]", text, re.DOTALL)
    assert excludes_block, "未解析到 spec excludes 块：请确认 excludes 仍为列表字面量"
    for entry in re.findall(r'"([^"]+)"', excludes_block.group(1)):
        assert "dst_manager" not in entry, (
            f"spec excludes 排除了 {entry}：内置扩展 Provider 是固定索引的编译期引用，"
            "被排除后 frozen 态设置框架不可用"
        )
    assert re.search(r'pathex\s*=\s*\[\s*[rR]?["\']\.\.[\\/]+src["\']', text), (
        "spec pathex 缺少 ../src：源码树不在分析路径上，静态导入的 Provider 无法被收集"
        "（断言允许 raw/单斜杠等等价写法）"
    )
    assert f"src/{MANIFEST_RESOURCE}" in _normalized_spec_text(), (
        "spec datas 不再包含内置扩展清单资源：frozen 态 discover() 会降级为占位 FAILED"
    )
    assert CATALOG_SETTINGS_FILE.is_file(), (
        "目录设置 Provider 模块不存在：固定索引的编译期引用会直接 ImportError"
    )
