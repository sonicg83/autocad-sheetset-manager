---
id: PLAN-DM-014
title: DST Manager Windows 绿色分发包与一键 release 流程实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-04
updated: 2026-09-04
related:
  - ARCH-DM-002
  - SPEC-DM-007
---

# DST Manager Windows 绿色分发包与一键 release 流程实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 [ARCH-DM-002](../../../docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md)，交付 PyInstaller onedir 绿色分发包（`dst-manager-v<版本>-win64.zip`，解压即用）与本地一键 release 流程（`scripts/release.ps1`，门禁 + 构建 + 本地 tag）。

**Architecture:** 新增 `runtime.py` 统一开发态/frozen 态资源定位，三处既有路径逻辑（前端静态目录、Alembic 迁移、Worker 子进程拉起）改经它适配；`config.py` 增加 frozen 态默认值；`packaging/` 提供 exe 入口与 PyInstaller spec；`scripts/` 两层构建脚本（纯构建 + 门禁 release）。开发态行为完全不变，全部改动以 frozen 分支或默认值工厂形式叠加。

**Tech Stack:** Python 3.12 + uv、PyInstaller ≥6（onedir）、pywebview/WebView2、PowerShell 5.1+、npm/Vite。

**Spec:** `docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md`（§3 代码改动、§3.3 spec 内容、§4 构建脚本、§5 release 流程为本次验收依据）。

## Global Constraints

- 全程简体中文注释、commit message 与用户文案；标识符保持英文。
- 开发态零行为变化：未 frozen 时所有新增分支必须与现状等价（既有测试不允许因此修改断言，仅允许新增）。
- 依赖变更必须同步更新 `pyproject.toml` 与 `uv.lock`（新增依赖仅 `pyinstaller`，进 `[dependency-groups] dev`）。
- 仓库位于 OneDrive：UV 相关命令前设置 `$env:UV_LINK_MODE = "copy"`。
- 不提交构建产物：`dist/`、`build/`、`web/dist/` 保持忽略；`sample/`、`legacy/` 不进包。
- 发布安全基线不涉及：本计划不改 DST/DWG 发布器、SCR 渲染、锁与事务逻辑。
- 每个 task 完成时更新根目录 `changelog.md`；commit message 简体中文、动词开头。
- Python 验证基线：`uv run ruff check .` 与 `uv run pytest -q` 全绿（当前基线 547 passed / 72 skipped）。
- 首次执行 release 前人工把 `pyproject.toml` 的 `version` 从 `0.3.0` 更新到目标版本（当前落后于 v0.3.3）；脚本只校验不一致即中止。
- 真实 AutoCAD 2016/2020 系统测试不阻塞本计划：仅当用户显式设置 `$env:DST_MANAGER_RUN_AUTOCAD = "1"` 且本机具备 Core Console、插件和私有样本时执行。

---

### Task 1: 运行时路径解析模块 `runtime.py`

**Files:**
- Create: `src/dst_manager/runtime.py`
- Test: `tests/unit/test_runtime.py`

**Interfaces:**
- Consumes: 无（仅标准库 `sys`、`pathlib`）。
- Produces: `is_frozen() -> bool`；`resource_dir(base: Path | None = None) -> Path`（开发态=仓库根；frozen=`sys._MEIPASS`；`base` 仅测试注入）。后续 Task 2/3/4 均从 `dst_manager.runtime` 导入这两个函数。

- [ ] **Step 1: 写失败测试**

```python
"""runtime 路径解析单测：开发态/frozen 态两态定位与测试注入。"""

import sys
from pathlib import Path

from dst_manager.runtime import is_frozen, resource_dir

REPO_ROOT = Path(__file__).parents[2]


def test_dev_state_resource_dir_is_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert is_frozen() is False
    assert resource_dir() == REPO_ROOT


def test_frozen_state_resource_dir_is_meipass(monkeypatch):
    meipass = Path(r"C:\packed\_internal")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert is_frozen() is True
    assert resource_dir() == meipass


def test_explicit_base_overrides_both_states(monkeypatch):
    base = Path(r"D:\inject")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resource_dir(base) == base
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_runtime.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'dst_manager.runtime'`

- [ ] **Step 3: 最小实现**

```python
"""运行时路径解析：统一开发态（源码树）与 PyInstaller frozen 态（onedir）的资源定位。

打包资源（web/dist、alembic.ini、migrations/）在开发态位于仓库根，frozen onedir
态位于 `sys._MEIPASS`（PyInstaller ≥6 默认 contents_directory=`_internal`）。
三处消费方：api.py 静态挂载、database.py 迁移定位、shell.py Worker 拉起（ARCH-DM-002 §3.1）。
"""

import sys
from pathlib import Path

# src/dst_manager/runtime.py -> parents[2] = 仓库根（alembic.ini 所在层）
_DEV_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """PyInstaller 冻结进程会设置 sys.frozen；开发态恒为 False。"""
    return getattr(sys, "frozen", False)


def resource_dir(base: Path | None = None) -> Path:
    """返回打包资源基准目录。base 仅供测试注入，生产代码不得传参。"""
    if base is not None:
        return base
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return _DEV_ROOT
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_runtime.py -q`
Expected: PASS（3 项）

- [ ] **Step 5: 提交**

```bash
git add src/dst_manager/runtime.py tests/unit/test_runtime.py
git commit -m "新增 runtime 模块统一开发态与 frozen 态资源定位"
```

---

### Task 2: 前端静态目录定位适配

**Files:**
- Modify: `src/dst_manager/interfaces/api.py:289`（`web_dist` 定位行）
- Test: `tests/unit/test_runtime.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `resource_dir()`。
- Produces: `create_app()` 静态挂载改从 `resource_dir() / "web" / "dist"` 定位；对外 HTTP 行为不变。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/test_runtime.py`）

```python
def test_api_mounts_web_dist_from_resource_dir(monkeypatch, tmp_path):
    """静态站点目录必须经 resource_dir 定位：frozen 态下 __file__ 不再指向源码树。"""
    from dst_manager.interfaces import api

    web_dist = tmp_path / "web" / "dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(api, "resource_dir", lambda: tmp_path)
    app = api.create_app()
    mounts = [r for r in app.routes if r.path == "/" and r.__class__.__name__ == "Mount"]
    assert mounts, "web/dist 未被挂载到 /"
```

- [ ] **Step 2: 运行测试确认当前通过（开发态等价）**

Run: `uv run pytest tests/unit/test_runtime.py -q`
Expected: 新测试 PASS（monkeypatch 后与定位来源无关）——此测试守护"改经 resource_dir 后仍挂载"，先确认它在当前实现下也通过。

- [ ] **Step 3: 修改实现**

`src/dst_manager/interfaces/api.py` 顶部导入区追加：

```python
from ..runtime import resource_dir
```

`api.py:289` 由：

```python
    web_dist = Path(__file__).parents[3] / "web" / "dist"
```

改为：

```python
    web_dist = resource_dir() / "web" / "dist"
```

- [ ] **Step 4: 回归确认**

Run: `uv run pytest tests/unit/test_runtime.py -q && uv run ruff check src/dst_manager/interfaces/api.py`
Expected: 全部 PASS，Ruff 无告警（`Path` 若在 api.py 其余处仍使用则保留导入，否则按 Ruff 提示清理）。

- [ ] **Step 5: 提交**

```bash
git add src/dst_manager/interfaces/api.py tests/unit/test_runtime.py
git commit -m "前端静态目录改经 runtime.resource_dir 定位"
```

---

### Task 3: Alembic 迁移资源定位适配

**Files:**
- Modify: `src/dst_manager/infrastructure/persistence/database.py:188-190`（`migrate_database` 的 `root` 定位）
- Test: `tests/unit/test_runtime.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `resource_dir()`。
- Produces: `migrate_database(url)` 在 frozen 态从 `resource_dir()` 读取 `alembic.ini` 与 `migrations/`；行为契约（升级到 `LATEST_SCHEMA_REVISION`）不变。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/test_runtime.py`）

```python
def test_migrate_database_uses_resource_dir(monkeypatch, tmp_path):
    """frozen 态下 alembic.ini 与 migrations/ 是打包资源：必须经 resource_dir 定位而非源码树。"""
    import shutil

    from dst_manager.infrastructure.persistence import database as database_module

    shutil.copyfile(REPO_ROOT / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(REPO_ROOT / "migrations", tmp_path / "migrations")
    monkeypatch.setattr(database_module, "resource_dir", lambda: tmp_path)
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    database_module.migrate_database(url)
    assert database_module.LATEST_SCHEMA_REVISION == "0004_dm007_layout_name_cache"
    # 迁移真实发生：alembic_version 表存在且为最新修订
    from sqlalchemy import inspect, create_engine, text

    engine = create_engine(url)
    version = engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == database_module.LATEST_SCHEMA_REVISION
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_runtime.py::test_migrate_database_uses_resource_dir -q`
Expected: FAIL——当前实现读源码树 `Path(__file__).parents[4]`，`alembic_version` 断言仍会通过但 `database_module` 没有 `resource_dir` 属性，monkeypatch 抛 `AttributeError`。

- [ ] **Step 3: 修改实现**

`database.py` 导入区追加：

```python
from ...runtime import resource_dir
```

`migrate_database` 内 `root` 定位由：

```python
    root = Path(__file__).resolve().parents[4]
```

改为：

```python
    root = resource_dir()
```

（开发态 `resource_dir()` 返回仓库根，与 `parents[4]` 等价；确认文件内 `Path` 仍有其他使用处，勿删导入。）

- [ ] **Step 4: 回归确认**

Run: `uv run pytest tests/unit/test_runtime.py tests/unit/test_database.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/dst_manager/infrastructure/persistence/database.py tests/unit/test_runtime.py
git commit -m "Alembic 迁移资源改经 runtime.resource_dir 定位"
```

---

### Task 4: Worker 子进程 frozen 拉起分支

**Files:**
- Modify: `src/dst_manager/interfaces/shell.py:103-117`（`_spawn_worker`）
- Test: `tests/unit/test_shell.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `is_frozen()`。
- Produces: `_spawn_worker(project_root: Path) -> subprocess.Popen`——frozen 态命令为 `[sys.executable, "worker", "--project-root", str(project_root)]`（复用 exe 的 `worker` 子命令），开发态保持 `[sys.executable, "-m", "dst_manager.interfaces.cli", "worker", ...]`。Task 6 的 exe 入口依赖此分支与 `packaging/entry.py` 的 argv 约定（无参数=`desktop`）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/test_shell.py`，复用文件内既有的 `_FakePopen` 与捕获模式）

```python
def test_spawn_worker_frozen_reuses_exe_worker_subcommand(monkeypatch):
    """frozen 态 sys.executable 是 dst-manager.exe 自身：-m 方式失效，必须复用 worker 子命令。"""
    captured = {}

    def fake_popen(args, cwd=None, env=None):
        captured["args"], captured["cwd"], captured["env"] = args, cwd, env
        return _FakePopen(args, cwd=cwd, env=env)

    monkeypatch.setattr("dst_manager.interfaces.shell.is_frozen", lambda: True)
    monkeypatch.setattr("dst_manager.interfaces.shell.subprocess.Popen", fake_popen)
    project_root = Path.cwd()
    _spawn_worker(project_root)
    assert captured["args"] == [sys.executable, "worker", "--project-root", str(project_root)]
    assert captured["cwd"] == str(project_root)
    assert captured["env"].get("PYTHONUTF8") == "1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_shell.py::test_spawn_worker_frozen_reuses_exe_worker_subcommand -q`
Expected: FAIL，`AttributeError: <module 'dst_manager.interfaces.shell'> ... does not have the attribute 'is_frozen'`

- [ ] **Step 3: 修改实现**

`shell.py` 导入区追加：

```python
from ..runtime import is_frozen
```

`_spawn_worker` 改为：

```python
def _spawn_worker(project_root: Path) -> subprocess.Popen:
    """拉起同机 CAD Worker 子进程（对齐 start.ps1 的托管方式）。

    开发态经 `python -m` 进入 `cli worker`；frozen 态 sys.executable 是 exe 自身，
    复用其 `worker` 子命令（entry.py 无参数时默认 desktop，见 packaging/entry.py）。
    `cwd` 与 `--project-root` 都取当前工作目录：`cli worker` 校验二者一致，
    且 `Settings.data_dir` 相对路径按 cwd 解析——与壳内 API 同 cwd，保证
    Worker 与 API 操作同一个 SQLite 任务队列。输出继承父进程终端，便于
    观察 Worker 认领日志。
    """
    if is_frozen():
        args = [sys.executable, "worker", "--project-root", str(project_root)]
    else:
        args = [sys.executable, "-m", "dst_manager.interfaces.cli", "worker", "--project-root", str(project_root)]
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.Popen(
        args,
        cwd=str(project_root),
        env=env,
    )
```

- [ ] **Step 4: 回归确认**

Run: `uv run pytest tests/unit/test_shell.py -q`
Expected: 全部 PASS（既有开发态用例断言 `-m` 分支不变）。

- [ ] **Step 5: 提交**

```bash
git add src/dst_manager/interfaces/shell.py tests/unit/test_shell.py
git commit -m "Worker 子进程支持 frozen 态复用 exe worker 子命令"
```

---

### Task 5: Settings frozen 默认值（插件 DLL 与 data_dir）

**Files:**
- Modify: `src/dst_manager/config.py`
- Test: `tests/unit/test_config.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `is_frozen()`。
- Produces: `Settings` 字段默认值——frozen 态：`autocad_2016_plugin`/`autocad_2020_plugin` 指向 exe 同级 `autocad2016/autocad2020/DstManager.AutoCAD.dll`，`data_dir` 指向 `%LOCALAPPDATA%/dst-manager/data`；开发态与现状完全一致（插件 None、data_dir `.dst-manager-data`）。`.env`/环境变量覆盖路径不变（ARCH-DM-002 §3.4）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/test_config.py`）

```python
def test_frozen_plugin_defaults_point_to_bundled_dlls(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    settings = Settings(_env_file=None)
    assert settings.autocad_2016_plugin == (tmp_path / "autocad2016" / "DstManager.AutoCAD.dll").resolve()
    assert settings.autocad_2020_plugin == (tmp_path / "autocad2020" / "DstManager.AutoCAD.dll").resolve()
    # Core Console 永不猜测，frozen 态同样保持 None
    assert settings.autocad_2016_console is None
    assert settings.autocad_2020_console is None


def test_frozen_data_dir_defaults_to_localappdata(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    settings = Settings(_env_file=None)
    assert settings.data_dir == (tmp_path / "AppData" / "dst-manager" / "data").resolve()


def test_frozen_explicit_config_overrides_defaults(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    plugin = tmp_path / "custom" / "my.dll"
    settings = Settings(_env_file=None, autocad_2020_plugin=str(plugin))
    assert settings.autocad_2020_plugin == plugin.resolve()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: 新增 3 项 FAIL（frozen 态当前仍返回 None/相对路径）。

- [ ] **Step 3: 修改实现**

`config.py` 导入区追加 `import sys` 与：

```python
from .runtime import is_frozen
```

在 `_default_draft_dir` 之后新增三个默认值工厂：

```python
def _frozen_app_dir() -> Path | None:
    """frozen onedir 态的 exe 所在目录；开发态返回 None。"""
    return Path(sys.executable).resolve().parent if is_frozen() else None


def _default_data_dir() -> Path:
    """frozen 态数据落用户目录，避免双击启动把数据写进程序目录、zip 更新时被覆盖。"""
    app_dir = _frozen_app_dir()
    if app_dir is None:
        return Path(".dst-manager-data")
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "dst-manager" / "data").resolve()


def _default_plugin(version: str) -> Path | None:
    """frozen 态默认使用随包分发的 Worker 插件 DLL；开发态保持 None（显式配置）。"""
    app_dir = _frozen_app_dir()
    if app_dir is None:
        return None
    return (app_dir / f"autocad{version}" / "DstManager.AutoCAD.dll").resolve()
```

字段声明改为：

```python
    data_dir: Path = Field(default_factory=_default_data_dir)
    draft_dir: Path = Field(default_factory=_default_draft_dir)
    autocad_2016_console: Path | None = None
    autocad_2016_plugin: Path | None = Field(default_factory=lambda: _default_plugin("2016"))
    autocad_2020_console: Path | None = None
    autocad_2020_plugin: Path | None = Field(default_factory=lambda: _default_plugin("2020"))
```

- [ ] **Step 4: 回归确认**

Run: `uv run pytest tests/unit/test_config.py -q && uv run pytest tests/unit -q`
Expected: 全部 PASS（既有 `test_cad_paths_none_untouched` 等开发态断言不受影响）。

- [ ] **Step 5: 提交**

```bash
git add src/dst_manager/config.py tests/unit/test_config.py
git commit -m "Settings 支持 frozen 态插件 DLL 与数据目录默认值"
```

---

### Task 6: exe 入口、PyInstaller spec 与本地构建冒烟

**Files:**
- Create: `packaging/entry.py`
- Create: `packaging/dst-manager.spec`
- Modify: `pyproject.toml`（dev 组追加 pyinstaller）、`uv.lock`（`uv add` 自动）、`.gitignore`（忽略 PyInstaller 产物）
- Test: 无自动化测试；以本地构建 + exe 冒烟为准（依赖本机 WebView2 与 Node，属环境冒烟）

**Interfaces:**
- Consumes: Task 4 的 argv 约定（frozen 态 `_spawn_worker` 传 `worker` 子命令）；Task 2/3 的 `resource_dir()`（运行期从 `_MEIPASS` 读取 datas）。
- Produces: `dist/DSTManager/` onedir 产物，内含 `dst-manager.exe`；Task 7 的构建脚本调用 `uv run pyinstaller --noconfirm packaging/dst-manager.spec`。

- [ ] **Step 1: 追加依赖与忽略项**

```powershell
$env:UV_LINK_MODE = "copy"
uv add --dev "pyinstaller>=6,<7"
```

核对 `pyproject.toml` 的 `[dependency-groups] dev` 出现 `"pyinstaller>=6,<7"` 且 `uv.lock` 同步（`uv lock --check` 通过）。`.gitignore` 追加两行（PyInstaller 默认输出目录，注意与既有 `web/dist/` 忽略不冲突）：

```gitignore
/build/
/dist/
```

- [ ] **Step 2: 创建 `packaging/entry.py`**

```python
"""PyInstaller exe 入口（ARCH-DM-002 §3.2）。

frozen 态无参数 = 双击启动桌面壳（复用 cli 的 desktop 命令）；
`dst-manager.exe worker` / `doctor` 等子命令原样进入 Typer 解析。
开发态不受影响（main.py 仍是 `dst-manager` script 入口）。
"""

import sys

if getattr(sys, "frozen", False) and len(sys.argv) == 1:
    sys.argv.append("desktop")

from dst_manager.interfaces.cli import app

app()
```

- [ ] **Step 3: 创建 `packaging/dst-manager.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec：DST Manager 绿色分发包（ARCH-DM-002 §3.3）。

运行约定：仓库根执行 `uv run pyinstaller --noconfirm packaging/dst-manager.spec`，
前置条件 web/dist 已构建、migrations/ 与 alembic.ini 在仓库根。
产物 `dist/DSTManager/`，datas 落在 _internal（= 运行期 sys._MEIPASS）。
"""

a = Analysis(
    ["packaging\\entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("web/dist", "web/dist"),
        ("alembic.ini", "."),
        ("migrations", "migrations"),
    ],
    hiddenimports=[
        # uvicorn 运行期动态导入的协议/事件循环实现
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # pywebview Windows 后端（WebView2 走 pythonnet/clr）
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        # SQLAlchemy SQLite 方言按 URL 动态加载
        "sqlalchemy.dialects.sqlite",
    ],
    excludes=[
        "tavily_cli",  # 生产依赖里的开发工具，禁止进包
        "pytest",
        "pytest_cov",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dst-manager",
    console=True,  # 控制台保留：Worker 认领日志与启动警告必须可观察
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DSTManager",
)
```

- [ ] **Step 4: 本地构建冒烟**

```powershell
$env:UV_LINK_MODE = "copy"
Set-Location web; npm ci; npm run build; Set-Location ..
uv run pyinstaller --noconfirm packaging/dst-manager.spec
```

Expected: `dist/DSTManager/dst-manager.exe` 存在；`_internal` 内可见 `web/dist`、`alembic.ini`、`migrations/`。

- [ ] **Step 5: exe 冒烟（人工）**

```powershell
.\dist\DSTManager\dst-manager.exe --help      # Typer 帮助可见
.\dist\DSTManager\dst-manager.exe doctor      # 输出 capabilities JSON
.\dist\DSTManager\dst-manager.exe             # 双击等价：桌面壳窗口打开（空库自动迁移），关闭后无残留 python 进程
```

任何 `ModuleNotFoundError`（如 `clr`/`alembic`/`mako`）按缺什么补进 spec `hiddenimports` 后重打；`web` 页面白屏时核对 `_internal/web/dist` 与浏览器控制台资源路径。

- [ ] **Step 6: 提交**

```bash
git add packaging/entry.py packaging/dst-manager.spec pyproject.toml uv.lock .gitignore
git commit -m "新增 PyInstaller onedir 打包入口与 spec"
```

---

### Task 7: 纯构建脚本 `scripts/build_release.ps1`

**Files:**
- Create: `scripts/build_release.ps1`（UTF-8 with BOM，对齐 `start.ps1`/`build_plugins.ps1` 既有约定）
- Test: `tests/unit/test_release_scripts.py`（新建，语法与 UTF-8 BOM 校验，沿用 `test_start_script.py` 的 PowerShell Parser 模式）

**Interfaces:**
- Consumes: `web/` npm 构建、`uv`、`scripts/build_plugins.ps1`（支持既有产物时传 `-SkipPlugins`）、Task 6 的 spec。
- Produces: `dist/releases/dst-manager-v<版本>-win64.zip`（版本缺省时从 `pyproject.toml` 读取）；Task 8 以 `-Version <版本>` 调用本脚本。

- [ ] **Step 1: 写失败测试**（新建 `tests/unit/test_release_scripts.py`）

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_release_scripts.py -q`
Expected: FAIL（两个脚本不存在）。

- [ ] **Step 3: 创建 `scripts/build_release.ps1`**

```powershell
# DST Manager 纯构建脚本：前端 -> Python 环境 -> 插件 -> PyInstaller -> 分发 zip（ARCH-DM-002 §4）。
# 不做任何 git 操作与门禁校验；release 流程见 scripts/release.ps1。
[CmdletBinding()]
param(
    # 分发 zip 的版本号；缺省从 pyproject.toml 读取
    [string]$Version = "",
    # 插件 DLL 已构建时跳过 MSBuild 重建
    [switch]$SkipPlugins
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

# 1. 前端构建（web/dist 是 spec 的 datas 前置条件）
Push-Location (Join-Path $projectRoot "web")
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
} finally {
    Pop-Location
}

# 2. Python 环境（pyinstaller 在 dev 组）
$env:UV_LINK_MODE = "copy"
uv sync --dev
if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }

# 3. 双版本插件构建
if (-not $SkipPlugins) {
    & (Join-Path $PSScriptRoot "build_plugins.ps1")
    if ($LASTEXITCODE -ne 0) { throw "插件构建失败" }
}

# 4. PyInstaller onedir
uv run pyinstaller --noconfirm (Join-Path $projectRoot "packaging\dst-manager.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

# 5. 版本号
if (-not $Version) {
    $pyproject = Get-Content (Join-Path $projectRoot "pyproject.toml") -Raw
    if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw "无法从 pyproject.toml 读取版本号" }
    $Version = $Matches[1]
}

# 6. 组装：随包插件 DLL + zip
$appDir = Join-Path $projectRoot "dist\DSTManager"
foreach ($v in @("2016", "2020")) {
    $src = Join-Path $projectRoot "plugins\autocad$v"
    if (-not (Test-Path -LiteralPath (Join-Path $src "DstManager.AutoCAD.dll"))) {
        throw "缺少 autocad$v 插件 DLL：$src（先运行 build_plugins.ps1）"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $appDir "autocad$v") -Recurse -Force
}
$releaseDir = Join-Path $projectRoot "dist\releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$zip = Join-Path $releaseDir "dst-manager-v$Version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $appDir "*") -DestinationPath $zip
Write-Host "分发包已生成：$zip"
```

- [ ] **Step 4: 运行脚本测试确认通过**

Run: `uv run pytest tests/unit/test_release_scripts.py -q`
Expected: PASS（本文件仅覆盖 `build_release.ps1`：BOM、语法、构建步骤契约）。

- [ ] **Step 5: 构建冒烟（有插件产物时）**

```powershell
.\scripts\build_release.ps1 -SkipPlugins
```

Expected: `dist/releases/dst-manager-v<pyproject版本>-win64.zip` 生成；解压后 `autocad2016/`、`autocad2020/` 与 `dst-manager.exe` 同级。若 `plugins/autocad2016/autocad2020` 产物缺失，先跑 `.\scripts\build_plugins.ps1`（本机无 VS/AutoCAD 程序集时如实记录跳过，不得伪造产物）。

- [ ] **Step 6: 提交**

```bash
git add scripts/build_release.ps1 tests/unit/test_release_scripts.py
git commit -m "新增纯构建脚本 build_release.ps1"
```

---

### Task 8: 一键 release 脚本 `scripts/release.ps1`

**Files:**
- Create: `scripts/release.ps1`（UTF-8 with BOM）
- Test: `tests/unit/test_release_scripts.py`（Task 7 已覆盖静态契约，本任务确认转绿）

**Interfaces:**
- Consumes: Task 7 的 `build_release.ps1 -Version`。
- Produces: 本地 annotated tag `v<版本>` + `dist/releases/dst-manager-v<版本>-win64.zip`；不 push、不发远程 Release。

- [ ] **Step 1: 写失败测试**（追加到 `tests/unit/test_release_scripts.py`）

```python
RELEASE_SCRIPT = ROOT / "scripts" / "release.ps1"
REQUIRED_RELEASE_STEPS = [
    "git status --porcelain", "rev-parse --abbrev-ref", "git tag -l", "version",
    "changelog.md", "ruff check", "pytest", "build_release.ps1", "git tag -a",
]


def test_release_script_is_utf8_bom():
    assert RELEASE_SCRIPT.exists(), "缺少 release.ps1"
    assert RELEASE_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(not POWERSHELLS, reason="需要 Windows PowerShell 或 PowerShell 7")
def test_release_script_parses_in_powershell():
    command = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{RELEASE_SCRIPT}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    completed = subprocess.run(
        [POWERSHELLS[0], "-NoProfile", "-Command", command], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_release_script_contains_gate_steps_in_order():
    source = RELEASE_SCRIPT.read_text(encoding="utf-8-sig")
    positions = [source.find(marker) for marker in REQUIRED_RELEASE_STEPS]
    assert all(p >= 0 for p in positions), f"release.ps1 缺少步骤：{[m for m, p in zip(REQUIRED_RELEASE_STEPS, positions) if p < 0]}"
    assert positions == sorted(positions), "release.ps1 门禁步骤顺序错误（tag 必须最后）"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_release_scripts.py -q`
Expected: `test_release_script_is_utf8_bom` FAIL（`scripts/release.ps1` 不存在），其余 release 用例连带失败。

- [ ] **Step 3: 创建 `scripts/release.ps1`**

```powershell
# DST Manager 一键 release：前置校验 -> 测试门禁 -> 构建 -> 本地 tag（ARCH-DM-002 §5）。
# tag 是最后一步，保证"有 tag 必有可用 zip"；push 与 zip 分发由人工执行。
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# 1. 前置校验（任一不过即中止，不产生半成品）
if (git status --porcelain) { throw "工作区存在未提交改动，先提交或暂存后再 release" }
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -ne "main") { throw "必须在 main 分支执行 release（当前：$branch）" }
if (git tag -l "v$Version") { throw "tag v$Version 已存在" }
$pyproject = Get-Content (Join-Path $projectRoot "pyproject.toml") -Raw
if ($pyproject -notmatch "(?m)^version\s*=\s*`"$Version`"") {
    throw "pyproject.toml version 与 -Version $Version 不一致：请人工更新版本号后重试（脚本不做自动 bump）"
}
$changelog = Get-Content (Join-Path $projectRoot "changelog.md") -Raw
if (-not $changelog.Contains("v$Version")) {
    throw "changelog.md 未包含 v$Version 记录：先按仓库约定补齐变更记录"
}

# 2. 测试门禁（真实 CAD 系统测试按约定另行显式启用，不在 release 门禁内）
$env:UV_LINK_MODE = "copy"
uv sync --dev
if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }
uv run ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff 未通过" }
uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest 未通过" }

# 3. 构建
& (Join-Path $PSScriptRoot "build_release.ps1") -Version $Version
if ($LASTEXITCODE -ne 0) { throw "构建失败" }

# 4. 收尾：本地 annotated tag（不 push）
$zip = Join-Path $projectRoot "dist\releases\dst-manager-v$Version-win64.zip"
if (-not (Test-Path -LiteralPath $zip)) { throw "未找到分发包：$zip" }
git tag -a "v$Version" -m "release v$Version"
Write-Host "release v$Version 完成：$zip"
Write-Host "tag v$Version 仅保存在本地；推送与 zip 分发由人工执行。"
```

- [ ] **Step 4: 运行脚本测试确认全部转绿**

Run: `uv run pytest tests/unit/test_release_scripts.py -q`
Expected: 全部 PASS（含步骤顺序契约：tag 位于最后）。

- [ ] **Step 5: 前置校验行为冒烟（不真正 release）**

```powershell
.\scripts\release.ps1 -Version 0.0.0
```

Expected: 在"工作区干净、版本不一致"或"changelog 无 v0.0.0"处中止并给出中文错误（**不会**走到构建/tag）。当前工作区若有其他未提交改动，此步会以"工作区存在未提交改动"中止——同样算通过，如实记录实际命中的校验项。

- [ ] **Step 6: 提交**

```bash
git add scripts/release.ps1 tests/unit/test_release_scripts.py
git commit -m "新增一键 release 脚本含门禁校验与本地 tag"
```

---

### Task 9: 文档、changelog 与全量验证

**Files:**
- Modify: `README.md`（新增"打包与 release"小节）
- Modify: `changelog.md`
- Modify: `docs/dst-manager/README.md`（如指南区需链接打包说明）

**Interfaces:**
- Consumes: Task 6-8 的脚本与产物路径。
- Produces: 分发与 release 的操作文档；全量回归结论。

- [ ] **Step 1: 根 README 新增"打包与 release"小节**（放在"一键启动"相关章节之后）

````markdown
## 打包与 release

分发给内部同事使用绿色免安装包；开发环境不需要以下流程。

```powershell
# 构建分发包（版本号缺省取 pyproject.toml）
.\scripts\build_release.ps1                # 首次或插件源码变更后不带 -SkipPlugins
.\scripts\build_release.ps1 -SkipPlugins   # 插件 DLL 无变化时复用既有产物

# 一键 release：前置校验 + Ruff/pytest 门禁 + 构建 + 本地 tag
.\scripts\release.ps1 -Version 0.3.4       # 先人工把 pyproject.toml version 与 changelog 更新到位
```

产物 `dist/releases/dst-manager-v<版本>-win64.zip` 解压即用：双击 `dst-manager.exe` 打开桌面壳；
数据与草稿在 `%LOCALAPPDATA%\dst-manager\`；AutoCAD Core Console 路径在 exe 同级放 `.env`
配置（`autocad_2016_console`/`autocad_2020_console`），可用 `dst-manager.exe doctor` 自检。
tag 仅打在本地，推送与分发由人工执行。
````

- [ ] **Step 2: 全量回归**

```powershell
$env:UV_LINK_MODE = "copy"
uv run ruff check .
uv run pytest -q
```

Expected: Ruff 全绿；pytest 不低于基线（547 passed / 72 skipped + 本计划新增用例：runtime 3 + api 1 + migrate 1 + shell 1 + config 3 + release_scripts 6 项）。

- [ ] **Step 3: 端到端 release 演练（可选但推荐，需用户参与）**

- 人工把 `pyproject.toml` `version` 更新到目标版本（如 `0.3.4`）、changelog 补 `v0.3.4` 章节、提交；
- 在 main 分支执行 `.\scripts\release.ps1 -Version 0.3.4`；
- 核对：门禁全绿、zip 生成、`git tag -l v0.3.4` 存在、无 push 发生。

- [ ] **Step 4: 更新 changelog 与提交**

`changelog.md` 追加本 task 记录（含实际验证数字与跳过项），然后：

```bash
git add README.md changelog.md
git commit -m "新增打包与 release 使用文档并完成全量回归"
```

---

## 自查记录

- Spec 覆盖：ARCH-DM-002 §3.1 → Task 1-4；§3.2 → Task 6；§3.3 → Task 6；§3.4 → Task 5；§4 → Task 7；§5 → Task 8；§6 测试与验证 → 各 task 测试步骤 + Task 9；§1.2 范围外未引入。
- 类型一致性：`resource_dir(base: Path | None = None) -> Path`、`is_frozen() -> bool` 在 Task 1 定义，Task 2-5 的导入与调用一致；`_spawn_worker` frozen 分支 argv 与 Task 6 `entry.py` 的 `desktop` 默认约定互补（有参数时 Typer 正常解析）。
- 已知风险（实现时注意，不构成占位）：PyInstaller 对 `pythonnet`/`mako`/`alembic` 的隐藏导入探测可能不全，按 Task 6 Step 5 的排错路径处理；`tests/unit/test_runtime.py` 中 `create_app()` 会触发真实 `Database` 初始化，与既有测试同环境假设。
