---
id: PLAN-DM-011
title: DST Manager v0.3.1 桌面壳与操作易用性迭代实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-03
updated: 2026-09-03
related:
  - SPEC-DM-007
  - ROADMAP-DM-001
---

# DST Manager v0.3.1 桌面壳与操作易用性迭代实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 [SPEC-DM-007](../../../docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md) 交付 WebView2 桌面壳（唯一入口）、DST 文件选择/关闭确认交互、草稿恢复可发现性改进、来源文件与布局下拉选择及布局全局缓存。

**Architecture:** 后端新增同步 `POST /api/layout-names` 端点（SHA-256 缓存 + accoreconsole 读取 DWG 布局名到临时副本）；桌面壳为 pywebview 模块挂接现有 FastAPI 应用（uvicorn 线程 + 随机端口）；前端在 `web/src/App.vue` 既有单文件风格内落地两态状态机、关闭确认与恢复提示。不改变发布事务、CAD 分流与安全门禁。

**Tech Stack:** Python 3.12 + uv、FastAPI、SQLAlchemy 2 + Alembic、pywebview（WebView2）、Vue 3 + TypeScript + Vite、Playwright。

**Spec:** `docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md`

## Global Constraints

- 全程简体中文注释、commit message 与用户文案；标识符保持英文。
- 后端只监听 `127.0.0.1`；壳与后端同机通信，不得开放外部访问。
- 不修改 DST/DWG 写入路径、发布事务、`DST -> XML DOM -> DST` 受控流程与 CAD 分流门禁。
- SCR 文件编码为 `mbcs`（跟随 `ScriptRenderer.render_rename` 既有写法，`src/dst_manager/infrastructure/autocad/worker.py:94-114`）。
- 插件命令只做只读枚举，不修改图纸、不调用 QSAVE。
- 布局缓存与草稿均存应用数据目录，不触碰工作区旁目录。
- Python 依赖用 `uv add`/`uv remove` 同步 `pyproject.toml` 与 `uv.lock`；前端依赖同步 `package.json` 与 `package-lock.json`。
- 每个任务完成时更新根目录 `changelog.md`（在 2026-09-03 章节追加）；commit message 简体中文、动词开头。
- 生成契约文件保持 LF（Windows `core.autocrlf=true` 漂移门禁，见 changelog 2026-09-01 条目）。
- 验证基线：`uv run ruff check .`、`uv run pytest -q`、`uv lock --check`；前端 `npm run build`、`npm run test:e2e`。

---

### Task 1: 布局缓存表迁移与 ORM 模型

**Files:**
- Create: `migrations/versions/0004_dm007_layout_name_cache.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`（新增 `LayoutNameCacheRow`、`Database.get_layout_names`/`save_layout_names`、`LATEST_SCHEMA_REVISION`）
- Test: `tests/unit/test_database.py`（追加用例）

**Interfaces:**
- Consumes: 现有 `Base`、`Database`（`database.py:30`）、迁移链 `0003_dm008_job_file_cadop`。
- Produces: `LayoutNameCacheRow`（表 `layout_name_cache`）；`Database.get_layout_names(file_hash: str) -> list[str] | None`；`Database.save_layout_names(file_hash: str, source_path: str, layouts: list[str]) -> None`；`LATEST_SCHEMA_REVISION = "0004_dm007_layout_name_cache"`。Task 3 依赖这三个名字。

- [ ] **Step 1: 写失败的迁移一致性测试**

在 `tests/unit/test_database.py` 追加（跟随文件内既有全新库升级用例的写法）：

```python
def test_fresh_upgrade_includes_layout_name_cache(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 't.db').resolve().as_posix()}")
    db.migrate_database()
    with db.session() as session:
        rows = session.execute(sqlalchemy.text("SELECT name FROM sqlite_master WHERE type='table' AND name='layout_name_cache'")).fetchall()
    assert rows, "layout_name_cache 表应存在"
```

（`session()` 的实际获取方式以文件内既有用例为准，保持一致。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_database.py -q`
Expected: FAIL（表不存在 / `LATEST_SCHEMA_REVISION` 未更新导致 check 一致性失败）

- [ ] **Step 3: 写迁移与模型**

`migrations/versions/0004_dm007_layout_name_cache.py`（跟随 0003 的 batch 风格）：

```python
"""layout name cache for SPEC-DM-007"""

import sqlalchemy as sa
from alembic import op

revision = "0004_dm007_layout_name_cache"
down_revision = "0003_dm008_job_file_cadop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "layout_name_cache",
        sa.Column("file_hash", sa.String(64), primary_key=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("layouts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("layout_name_cache")
```

`database.py`：在既有行模型之后新增（跟随既有 mapped_column 风格）：

```python
class LayoutNameCacheRow(Base):
    __tablename__ = "layout_name_cache"

    file_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_path: Mapped[str] = mapped_column(Text)
    layouts: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
```

`Database` 新增方法（session 获取与提交写法跟随文件内既有 `Database` 方法的惯例）：

```python
def get_layout_names(self, file_hash: str) -> list[str] | None:
    with self._session() as session:  # session 上下文名以文件内既有方法为准
        row = session.get(LayoutNameCacheRow, file_hash)
        return list(row.layouts) if row else None

def save_layout_names(self, file_hash: str, source_path: str, layouts: list[str]) -> None:
    with self._session() as session:
        row = session.get(LayoutNameCacheRow, file_hash)
        if row is None:
            row = LayoutNameCacheRow(file_hash=file_hash, source_path=source_path,
                                     layouts=layouts, created_at=datetime.now())
            session.add(row)
        else:
            row.source_path = source_path
            row.layouts = layouts
            row.created_at = datetime.now()
        session.commit()
```

并把 `LATEST_SCHEMA_REVISION` 更新为 `"0004_dm007_layout_name_cache"`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_database.py -q && uv run alembic upgrade head`
Expected: PASS；全新数据库升级成功

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0004_dm007_layout_name_cache.py src/dst_manager/infrastructure/persistence/database.py tests/unit/test_database.py changelog.md
git commit -m "新增布局名全局缓存表迁移"
```

---

### Task 2: Worker 插件布局枚举命令与 sidecar 解析

**Files:**
- Modify: `plugins/src/DstManager.AutoCAD/Commands.cs`（新增 `DstGetLayoutNames` 命令）
- Modify: `src/dst_manager/infrastructure/autocad/worker.py`（`ScriptRenderer.render_layout_names`、`parse_layout_names`）
- Test: `tests/unit/test_autocad_worker.py`（追加）

**Interfaces:**
- Consumes: `CadCapability`（`worker.py:151-159`）、`CoreConsoleExecutor.run(capability, drawing, script, timeout)`（`worker.py:176`）、sidecar 惯例（`DstGetLayoutHandles` 写 `<drawing>.dst-handles.txt`，`Commands.cs:79-80`）。
- Produces: `ScriptRenderer.render_layout_names(capability: CadCapability, work_dir: Path) -> Path`（在 `work_dir` 生成 SCR，期望对 `work_dir` 内的 `source.dwg` 执行）；`parse_layout_names(path: Path) -> list[str]`（解析 `<drawing>.dst-layout-names.json`）。Task 3 依赖这两个函数。

- [ ] **Step 1: 写失败的渲染与解析单测**

在 `tests/unit/test_autocad_worker.py` 追加（跟随文件内既有 `render_rename`/`parse_handles` 用例结构）：

```python
def test_render_layout_names_script(tmp_path, fake_capability):
    renderer = ScriptRenderer()
    script = renderer.render_layout_names(fake_capability, tmp_path)
    text = script.read_text(encoding="mbcs")
    assert "_.NETLOAD" in text and fake_capability.plugin in text
    assert "DstGetLayoutNames" in text
    assert "_.QSAVE" not in text, "布局枚举为只读命令，不得保存图纸"

def test_parse_layout_names(tmp_path):
    sidecar = tmp_path / "source.dst-layout-names.json"
    sidecar.write_text('{"version":1,"layouts":["A-01","A-02"]}', encoding="utf-8")
    assert parse_layout_names(sidecar) == ["A-01", "A-02"]

def test_parse_layout_names_rejects_unknown_version(tmp_path):
    sidecar = tmp_path / "source.dst-layout-names.json"
    sidecar.write_text('{"version":99,"layouts":[]}', encoding="utf-8")
    with pytest.raises(ApplicationError):
        parse_layout_names(sidecar)
```

（`fake_capability` 构造方式跟随文件内既有 fixture；无则按 `CadCapability(version="2020", console=Path("console"), plugin=Path("plugin"), available=True)` 的实际字段新建。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_autocad_worker.py -q`
Expected: FAIL（`render_layout_names` / `parse_layout_names` 未定义）

- [ ] **Step 3: 实现 renderer 与 parser**

`worker.py` 在 `render_handles`（`worker.py:133-134`）之后新增，跟随既有 mbcs/换行惯例（参考最近一次修复"Windows 生成契约换行漂移"的提交，行尾用 `\n`）：

```python
def render_layout_names(self, capability, work_dir: Path) -> Path:
    script = work_dir / "layout-names.scr"
    lines = [
        "FILEDIA 0",
        "SECURELOAD 0",
        f"_.NETLOAD {capability.plugin}",
        "DstGetLayoutNames",
    ]
    script.write_text("\n".join(lines) + "\n", encoding="mbcs")
    return script
```

`parse_layout_names` 跟随 `parse_handles`（`worker.py:137`）的容错风格：读 JSON、校验 `version == 1`、返回 `layouts` 字符串列表；未知版本或解析失败抛 `ApplicationError("LAYOUT_READ_FAILED", ...)`。

- [ ] **Step 4: 实现插件命令**

`Commands.cs` 跟随 `DstGetLayoutHandles`（`Commands.cs:62-82`）的结构新增：

```csharp
[CommandMethod("DstGetLayoutNames")]
public void GetLayoutNames()
{
    // 遍历 db.LayoutDictionaryId（OpenMode.ForRead），排除模型空间布局（Layout.LayoutName == "Model" 或 db.ModelSpaceLayoutId 对应项），
    // 收集纸张空间布局名并排序；
    // 按 LayoutRenameCommand.WriteResult 的序列化惯例（Commands.cs 同项目 LayoutRenameCommand.cs:266-279）
    // 写 sidecar JSON：<文档全路径>.dst-layout-names.json，UTF-8，结构 {"version":1,"layouts":[...]}；
    // editor.WriteMessage("DST_MANAGER_LAYOUT_NAMES=" + count)（跟随既有标记输出惯例）。
}
```

命令体只读：不 StartTransaction 写入、不 QSAVE、不改 Layout。

- [ ] **Step 5: 运行单测与插件构建**

Run: `uv run pytest tests/unit/test_autocad_worker.py -q`
Expected: PASS

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1`
Expected: 2016/2020 双版本构建成功（本机具备构建环境时；否则记录跳过原因）

- [ ] **Step 6: 真实 CAD 系统测试（环境具备时）**

在 `tests/system_autocad/test_capabilities.py` 既有门禁风格内（`DST_MANAGER_RUN_AUTOCAD=1` + 本机 Core Console/插件/私有样本）追加用例：对私有样本 DWG 执行 `render_layout_names` 渲染的 SCR，断言 sidecar 产出、布局名非空且与官方 Sheet Manager 显示一致、原 DWG 时间戳不变。环境不具备时记录跳过条件（跟随 PLAN-DM-009 先例，保留为验证项而非通过项）。

- [ ] **Step 7: Commit**

```bash
git add plugins/src/DstManager.AutoCAD/Commands.cs src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_autocad_worker.py tests/system_autocad/test_capabilities.py changelog.md
git commit -m "新增 Worker 插件只读布局枚举命令与 SCR 渲染"
```

---

### Task 3: 布局名读取服务与 API 端点

**Files:**
- Modify: `src/dst_manager/application/service.py`（新增 `get_layout_names`）
- Modify: `src/dst_manager/interfaces/contracts.py`、`src/dst_manager/interfaces/responses.py`、`src/dst_manager/interfaces/api.py`
- Test: `tests/integration/test_api.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `Database.get_layout_names`/`save_layout_names`；Task 2 的 `ScriptRenderer.render_layout_names`、`parse_layout_names`；既有 `_capability(version)`（`service.py:1291-1296`）与 `CoreConsoleExecutor`。
- Produces: `POST /api/layout-names`，请求 `{"file_path": "<绝对路径>", "cad_version": "2016"|"2020"}`，响应 `{"layouts": ["..."], "cached": bool, "file_hash": "<sha256>"}`；错误码 `LAYOUT_SOURCE_TYPE_INVALID`、`LAYOUT_SOURCE_NOT_FOUND`、`LAYOUT_READ_FAILED`。前端 Task 7 依赖此契约。

- [ ] **Step 1: 写失败的集成测试**

在 `tests/integration/test_api.py` 追加（跟随既有 `TestClient(create_app(Settings(data_dir=tmp_path/"data")))` 惯例，`test_api.py:53`）：

```python
def test_layout_names_rejects_non_dwg(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    other = tmp_path / "x.txt"
    other.write_text("x")
    resp = client.post("/api/layout-names", json={"file_path": str(other), "cad_version": "2020"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "LAYOUT_SOURCE_TYPE_INVALID"

def test_layout_names_missing_file(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    resp = client.post("/api/layout-names", json={"file_path": str(tmp_path / "a.dwg"), "cad_version": "2020"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "LAYOUT_SOURCE_NOT_FOUND"
```

（accocreconsole 命中路径不入集成测试；缓存命中路径可用注入假 executor 的 service 单测覆盖，放入 `tests/unit/` 新文件 `test_layout_names.py`：monkeypatch `CoreConsoleExecutor.run` 为写 sidecar 后返回 0，断言第二次调用 `cached=True` 且 layouts 一致、原 DWG 未被修改。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/integration/test_api.py -q`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现服务与端点**

`service.py` 新增（`self` 上 Database 实例与 settings 的属性名以 `service.py:75-78` 既有代码为准）：

```python
def get_layout_names(self, file_path: Path, cad_version: str) -> dict:
    resolved = file_path.resolve()
    # 复用 open_workspace（service.py:94 起）对用户路径的同一校验（危险名称/越界），保持一处逻辑
    if resolved.suffix.casefold() not in {".dwg", ".dwt"}:
        raise ApplicationError("LAYOUT_SOURCE_TYPE_INVALID", "来源文件必须是 .dwg 或 .dwt", 422)
    if not resolved.is_file():
        raise ApplicationError("LAYOUT_SOURCE_NOT_FOUND", "来源文件不存在", 404)
    digest = _sha256_of(resolved)  # 文件内新增辅助函数，64KB 分块避免大文件整读：
    # def _sha256_of(path: Path) -> str:
    #     h = hashlib.sha256()
    #     with path.open("rb") as fh:
    #         for chunk in iter(lambda: fh.read(65536), b""):
    #             h.update(chunk)
    #     return h.hexdigest()
    cached = self._database.get_layout_names(digest)  # Database 实例属性名以 service.py:75 处赋值为准
    if cached is not None:
        return {"layouts": cached, "cached": True, "file_hash": digest}
    capability = self._capability(cad_version)
    renderer, executor = ScriptRenderer(), CoreConsoleExecutor()
    with tempfile.TemporaryDirectory(prefix="dst-layouts-") as tmp:
        work_dir = Path(tmp)
        shutil.copy2(resolved, work_dir / "source.dwg")  # .dwt 同样复制为 source.dwg（同格式），避免 /i 按模板新建图形；在副本上运行，原文件不产生锁/临时文件
        script = renderer.render_layout_names(capability, work_dir)
        executor.run(capability, work_dir / "source.dwg", script, self.settings.cad_timeout_seconds)
        sidecar = work_dir / "source.dst-layout-names.json"
        if not sidecar.is_file():
            raise ApplicationError("LAYOUT_READ_FAILED", "布局枚举未产出结果，请确认 Core Console 与插件配置", 502)
        layouts = parse_layout_names(sidecar)
    self._database.save_layout_names(digest, str(resolved), layouts)
    return {"layouts": layouts, "cached": False, "file_hash": digest}
```

`executor.run` 失败（非零/超时）时 `CoreConsoleExecutor` 的既有行为会抛出或返回错误——在 except 中转换为 `ApplicationError("LAYOUT_READ_FAILED", "读取布局失败：DWG 可能正被 AutoCAD 占用或 CAD 环境不可用", 502)`。

`contracts.py`：

```python
class LayoutNamesRequest(ContractModel):
    file_path: Path
    cad_version: Literal["2016", "2020"] = "2020"
```

`responses.py`：

```python
class LayoutNamesResponse(ResponseModel):
    layouts: list[str]
    cached: bool
    file_hash: str
```

`api.py`（跟随既有端点风格，`api.py:83` 附近）：

```python
@app.post("/api/layout-names", response_model=LayoutNamesResponse, response_model_exclude_unset=True)
def read_layout_names(request: LayoutNamesRequest):
    return service.get_layout_names(request.file_path, request.cad_version)
```

（同步 `def` 由 FastAPI 放入线程池，不阻塞事件循环。）

- [ ] **Step 4: 再生成前端契约并验证漂移门禁**

Run: `cd web && npm run generate:api`
Expected: `web/src/api/schema.d.ts`（按项目实际生成路径）更新并包含 `LayoutNamesResponse`；生成文件保持 LF

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/integration/test_api.py tests/unit/test_layout_names.py -q && uv run ruff check .`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dst_manager/application/service.py src/dst_manager/interfaces/contracts.py src/dst_manager/interfaces/responses.py src/dst_manager/interfaces/api.py tests/integration/test_api.py tests/unit/test_layout_names.py web/src/api changelog.md
git commit -m "新增布局名读取端点与全局缓存"
```

---

### Task 4: pywebview 桌面壳

**Files:**
- Create: `src/dst_manager/interfaces/shell.py`
- Modify: `src/dst_manager/interfaces/cli.py`（新增 `desktop` 命令）
- Modify: `pyproject.toml` / `uv.lock`（`uv add "pywebview>=5,<6"`）
- Test: `tests/unit/test_shell.py`（新建，轻量）

**Interfaces:**
- Consumes: `create_app()`（`api.py:56-58`、`api.py:301`）、`Settings`（`config.py`）。
- Produces: `ShellBridge.select_file(file_types: list[str]) -> str | None`（js_api 桥，前端经 `window.pywebview.api.select_file` 调用）；CLI 命令 `uv run dst-manager desktop`。前端 Task 5/7 依赖 `select_file` 签名；Task 8 依赖 shell 模块。

- [ ] **Step 1: 添加依赖**

```bash
uv add "pywebview>=5,<6"
```

Expected: `pyproject.toml` 与 `uv.lock` 更新；`uv lock --check` 通过

- [ ] **Step 2: 写轻量单测（桥可导入、端口绑定逻辑可测）**

`tests/unit/test_shell.py`：

```python
def test_shell_bridge_select_file_requires_window():
    from dst_manager.interfaces.shell import ShellBridge

    bridge = ShellBridge()
    with pytest.raises(RuntimeError):
        bridge.select_file(["DST 文件|*.dst"])  # 未绑定窗口时给出明确错误而非 AttributeError
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/unit/test_shell.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 shell 模块与 CLI 命令**

`src/dst_manager/interfaces/shell.py`：

```python
"""桌面壳：pywebview（WebView2）承载本地 Web 界面。壳为 v0.3.1 唯一交付入口。"""

import threading
import time

import uvicorn
import webview

from .api import create_app
from ..config import Settings


class ShellBridge:
    """暴露给 window.pywebview.api 的最小原生能力面（SPEC-DM-007 §3.2）。"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def bind(self, window: webview.Window) -> None:
        self._window = window

    def select_file(self, file_types: list[str]) -> str | None:
        if self._window is None:
            raise RuntimeError("文件对话框窗口尚未就绪")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
        )
        return result[0] if result else None


def run_desktop(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    bridge = ShellBridge()
    window = webview.create_window("DST Manager", f"http://127.0.0.1:{port}/", js_api=bridge, width=1280, height=800)
    bridge.bind(window)
    try:
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
```

`cli.py` 跟随既有 `serve` 命令（`cli.py:28-43`）风格新增：

```python
@app.command()
def desktop() -> None:
    """启动桌面壳（WebView2）窗口。"""
    from .shell import run_desktop

    run_desktop()
```

- [ ] **Step 5: 运行单测与手动冒烟**

Run: `uv run pytest tests/unit/test_shell.py -q && uv run ruff check .`
Expected: PASS

手动冒烟（写入 changelog 记录结果）：`uv run dst-manager desktop`——窗口打开、界面加载、`select_file` 弹出原生对话框并可返回绝对路径、关闭窗口后进程退出。本机无 WebView2 Runtime 时记录跳过原因（Windows 11 默认内置）。

- [ ] **Step 6: Commit**

```bash
git add src/dst_manager/interfaces/shell.py src/dst_manager/interfaces/cli.py pyproject.toml uv.lock tests/unit/test_shell.py changelog.md
git commit -m "新增 pywebview 桌面壳入口"
```

---

### Task 5: 前端两态状态机、DST 文件选择与关闭确认

**Files:**
- Create: `web/src/api/shell.ts`
- Modify: `web/src/App.vue`（`.section.open` 两处：约 664 与 820 行；`openWorkspace` 约 231-245 行；新增 `closeWorkspace`）
- Modify: `web/tests/e2e/main.spec.ts`（更新既有助手 + 新用例）

**Interfaces:**
- Consumes: 既有 `POST /api/workspaces/open`、`request()`（`web/src/api/client.ts:11-21`）、`openWorkspace`（`App.vue:231-245`）、`loadDraft`（`App.vue:267`）。
- Produces: `getShellBridge(): { select_file(fileTypes: string[]): Promise<string | null> } | null`（`web/src/api/shell.ts`）；`openByPath(path: string)` 与 `closeWorkspace()`（App.vue 内部函数，Task 6/7 复用）。Task 7 的来源文件选择复用 `getShellBridge`。

- [ ] **Step 1: 写失败的 e2e 用例**

`main.spec.ts` 先在既有 init 注入处（`installMockEventSource` 所在 beforeEach，`main.spec.ts:4-17`）统一注入壳桥假件：

```typescript
await page.addInitScript(() => {
  (window as any).pywebview = {
    api: {
      select_file: async (fileTypes: string[]) => (window as any).__fakeSelectResult ?? null,
    },
  };
});
```

并把既有 `openWorkspace()` 助手改为经假桥路径（不再向已删除的路径输入框打字）：

```typescript
async function openWorkspace(page: Page, dst = "C:/sample/project1.dst") {
  await page.evaluate((p) => { (window as any).__fakeSelectResult = p; }, dst);
  await page.goto("/");
  await page.getByRole("button", { name: "选择 DST 文件" }).click();
  await page.waitForSelector("text=已打开");  // 以实际已打开态标志为准，跟随既有断言风格
}
```

新用例：

```typescript
test("未打开态只有文件选择区，不显示修订历史", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "选择 DST 文件" })).toBeVisible();
  await expect(page.getByRole("button", { name: "修订历史" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "打开项目" })).toHaveCount(0);
});

test("选择非 .dst 文件给出提示且不发起打开", async ({ page }) => {
  let opened = false;
  await page.route("**/api/workspaces/open", (route) => { opened = true; return route.fulfill({ json: {} }); });
  await page.goto("/");
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:/x/proj.txt"; });
  await page.getByRole("button", { name: "选择 DST 文件" }).click();
  await expect(page.getByText("仅支持 DST 文件")).toBeVisible();
  expect(opened).toBeFalsy();
});

test("关闭且有未发布改动时弹确认，放弃后回未打开态", async ({ page }) => {
  // mock open + workspace + draft（草稿 actions 非空，跟随 beforeEach 既有 draft mock 改造）
  await openWorkspace(page);
  await page.getByRole("button", { name: "关闭" }).click();
  page.once("dialog", (d) => d.accept());
  await expect(page.getByRole("button", { name: "选择 DST 文件" })).toBeVisible();
});
```

（既有用例若依赖路径输入框，逐一改用 `openWorkspace` 助手；预期改动集中在 `main.spec.ts`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e`
Expected: FAIL（按钮/文案不存在）

- [ ] **Step 3: 实现 shell 桥与前端状态机**

`web/src/api/shell.ts`：

```typescript
type ShellBridge = { select_file(fileTypes: string[]): Promise<string | null> };

export function getShellBridge(): ShellBridge | null {
  const api = (window as unknown as { pywebview?: { api?: ShellBridge } }).pywebview?.api;
  return api ?? null;
}

export const DST_FILE_FILTERS = ["DST 文件|*.dst"];
export const TEMPLATE_FILE_FILTERS = ["DWG/DWT 文件|*.dwg;*.dwt"];
```

`App.vue`（跟随既有压缩单行风格，保持文件内一致性）：

1. 从 `openWorkspace` 中抽出 `async function openByPath(path: string)`（保留 `beginWorkspaceLoad` 代次保护、`resetEditingState`、`loadDraft` 顺序，`App.vue:231-245`）；`openWorkspace` 改为 `openByPath(dstPath.value)` 仅服务无壳回退。
2. 新增 `const hasShell = computed(() => getShellBridge() !== null)`。
3. 新增：

```typescript
const DST_EXT = /\.dst$/i;
async function selectAndOpenDst(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪，请通过 dst-manager desktop 启动";return}
  const path=await bridge.select_file(DST_FILE_FILTERS);
  if(!path)return;
  if(!DST_EXT.test(path)){error.value="仅支持 DST 文件";return}
  await openByPath(path);
}
async function closeWorkspace(){
  const pending=draftActions.value.length>draftCursor.value||draftSaveFailed.value||draftStale.value;
  if(pending){
    const ok=confirm("存在未发布完毕的改动。改动已自动保存，重新打开同一 DST 可继续处理。确定关闭并放弃当前改动？");
    if(!ok)return;
    await discardDraft();
  }
  resetDraftState();resetEditingState();baseWorkspace.value=null;workspace.value=null;
}
```

（`discardDraft`/`resetDraftState`/`resetEditingState` 用既有函数名，见 `App.vue:223`、`App.vue:314`。）

4. 模板：两处 `.section.open`（`App.vue:664`、`App.vue:820`）——先核对各自外层 `v-if` 条件确认未打开/已打开归属，然后：
   - 未打开态块：删除 `<input v-model="dstPath">` 与"打开项目"按钮，替换为 `<button @click="selectAndOpenDst">选择 DST 文件</button>`（保留拖拽热区样式类占位，拖拽能力由 Task 8 决定）；无壳回退时在此块内保留原输入框（`v-if="!hasShell"`）。
   - 已打开态块：`<button @click="openWorkspace">打开项目</button>` 改为 `<button @click="closeWorkspace">关闭</button>`；"修订历史"按钮保留不动。

- [ ] **Step 4: 运行 e2e 与构建**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS（`vue-tsc` 无类型错误）

- [ ] **Step 5: Commit**

```bash
git add web/src/api/shell.ts web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "前端落地 DST 文件选择与关闭确认状态机"
```

---

### Task 6: 草稿恢复提示与保存状态可见性

**Files:**
- Modify: `web/src/App.vue`（`loadDraft` 约 267 行起；新增恢复横幅状态与保存状态展示）
- Modify: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: 既有 `loadDraft`（`App.vue:267-`）、`draftSaving`/`draftSaveFailed`/`draftStale`（`App.vue:42-45,118`）、`discardDraft`（`App.vue:314`）、`DraftActionsPanel` 的 `commandCount`。
- Produces: 恢复横幅状态 `draftRecovered: Ref<number | null>`（恢复的待处理条数，`null` 为不显示）；保存状态文案 `saveStatusText`。仅 App.vue 内部，无跨任务消费。

- [ ] **Step 1: 写失败的 e2e 用例**

```typescript
test("打开时恢复非空草稿显示恢复提示", async ({ page }) => {
  // beforeEach 的 draft mock 改为可注入：本用例 mock GET draft 返回 {schema_version:1,base_revision_id:"r1",expected_version:3,cursor:0,actions:[{...至少一条合法动作}]}
  await openWorkspace(page);
  await expect(page.getByText(/已恢复上次未完成的改动/)).toBeVisible();
  await page.getByRole("button", { name: "清空重来" }).click();
  await expect(page.getByText(/已恢复上次未完成的改动/)).toHaveCount(0);
});

test("草稿保存失败时显示保存失败与重试入口", async ({ page }) => {
  await page.route("**/api/workspaces/**/draft", (route, req) => {
    if (req.method() === "PUT") return route.fulfill({ status: 409, json: { code: "DRAFT_CONFLICT", message: "冲突" } });
    return route.continue();
  });
  await openWorkspace(page);
  // 触发一次动作后断言保存状态展示"保存失败"与"重试"按钮可见
  await expect(page.getByText("保存失败")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
});
```

（draft mock 的具体响应结构以 `loadDraft` 对 `DraftEnvelope` 的消费字段为准：`schema_version/base_revision_id/expected_version/cursor/actions`，`App.vue:299`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e`
Expected: FAIL

- [ ] **Step 3: 实现横幅与保存状态**

`App.vue`：

1. `const draftRecovered=ref<number|null>(null)`；`loadDraft` 恢复非空 actions 后置为待处理条数（跟随既有 `projectCommands(actions,cursor)` 的计数方式，`web/src/drafts.ts:23-38`）；`resetDraftState` 中重置为 `null`。
2. 模板加横幅（已打开态、`draftRecovered!==null && draftRecovered>0` 时显示）：

```html
<div class="recover-banner" role="status">已恢复上次未完成的改动（{{draftRecovered}} 条待处理）<button @click="draftRecovered=null">继续</button><button @click="clearDraftRestart">清空重来</button></div>
```

`clearDraftRestart` 调用既有 `clear` 逻辑（`DraftActionsPanel` 的 clear 事件处理函数，`App.vue` 对应 `@clear`）+ `discardDraft()`，并重置 `draftRecovered=null`。

3. 保存状态常驻展示（草稿工具栏附近，消费既有 `draftSaving`/`draftSaveFailed`/`draftStale`）：

```html
<span class="save-status" role="status">{{saveStatusText}}</span><button v-if="draftSaveFailed" @click="scheduleSave">重试</button>
```

`saveStatusText` 计算属性：`draftSaveFailed ? "保存失败" : draftSaving ? "保存中" : draftStale ? "草稿已过期" : "已保存"`。`scheduleSave` 即既有 `PUT /draft` 自动保存队列的入口函数（`App.vue:299` 所在的队列推进函数，保持既有重试幂等语义）。

- [ ] **Step 4: 运行 e2e 与构建**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "新增草稿恢复提示与保存状态展示"
```

---

### Task 7: 来源文件选择与布局下拉

**Files:**
- Modify: `web/src/App.vue`（`insertSheetForm` 相关：约 371-381、702-706、863 行）
- Modify: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: Task 3 的 `POST /api/layout-names`（响应 `{layouts, cached, file_hash}`）；Task 5 的 `getShellBridge`/`TEMPLATE_FILE_FILTERS`（`web/src/api/shell.ts`）；既有 `queueInsertSheet`（`App.vue:371-381`）。
- Produces: 无跨任务接口；`insertSheetForm.sourceFile` 语义不变（仍为绝对路径字符串）。

- [ ] **Step 1: 写失败的 e2e 用例**

```typescript
test("选择来源文件后加载布局下拉", async ({ page }) => {
  await page.route("**/api/layout-names", (route) =>
    route.fulfill({ json: { layouts: ["A-01", "A-02"], cached: false, file_hash: "abc" } }));
  await openWorkspace(page);
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:/tpl/frame.dwg"; });
  await page.getByRole("button", { name: "选择模板文件" }).click();
  await expect(page.getByRole("combobox", { name: /来源布局/ })).toBeEnabled();
  await expect(page.getByRole("combobox", { name: /来源布局/ })).toContainText("A-01");
});

test("布局读取失败回退手动输入", async ({ page }) => {
  await page.route("**/api/layout-names", (route) =>
    route.fulfill({ status: 502, json: { code: "LAYOUT_READ_FAILED", message: "读取布局失败" } }));
  await openWorkspace(page);
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:/tpl/frame.dwg"; });
  await page.getByRole("button", { name: "选择模板文件" }).click();
  await expect(page.getByText("读取布局失败")).toBeVisible();
  await expect(page.getByRole("textbox", { name: /来源布局/ })).toBeVisible();
});
```

（`combobox`/`textbox` 的 accessible name 以模板实际 `aria-label` 或 label 关联为准，落地时保持一致。）

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e`
Expected: FAIL

- [ ] **Step 3: 实现（注意模板两处表单：约 702-706 与 863 行都要改）**

`App.vue`：

1. 新增状态与函数：

```typescript
const layoutOptions=ref<string[]>([]);
const layoutLoading=ref(false);
const layoutError=ref("");
const layoutManual=ref(false);
const DWG_DWT_EXT=/\.(dwg|dwt)$/i;
async function selectTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪";return}
  const path=await bridge.select_file(TEMPLATE_FILE_FILTERS);
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value="仅支持 .dwg/.dwt 模板文件";return}
  insertSheetForm.sourceFile=path;layoutError.value="";layoutManual.value=false;
  await loadLayoutOptions(path);
}
async function loadLayoutOptions(path:string){
  layoutLoading.value=true;layoutOptions.value=[];
  try{const r=await request<{layouts:string[];cached:boolean;file_hash:string}>(`/api/layout-names`,{method:"POST",body:JSON.stringify({file_path:path,cad_version:workspace.value?.default_cad_version??"2020"})});layoutOptions.value=r.layouts}
  catch(e){layoutError.value=e instanceof ApiError?e.message:"读取布局失败";layoutManual.value=true}
  finally{layoutLoading.value=false}
}
```

（`cad_version` 字段名以 workspace 响应实际字段为准；若响应无此字段则固定 `"2020"` 并在 Task 3 端点保持默认。）

2. 模板（两处）："来源文件" `<input v-model="insertSheetForm.sourceFile">` 改为 `<button @click="selectTemplateFile">选择模板文件</button>` + 只读路径回显 `<span>{{insertSheetForm.sourceFile}}</span>`；"来源布局"：`layoutLoading` 时显示 `<span>正在读取布局…</span>`（进度提示，SPEC-DM-007 §6.2）；`layoutOptions.length && !layoutManual` 时渲染 `<select v-model="insertSheetForm.sourceLayout"><option v-for="l in layoutOptions" :value="l">{{l}}</option></select>`；`layoutError` 时显示错误文案并提供手动输入 `<input v-model="insertSheetForm.sourceLayout">` 回退。

- [ ] **Step 4: 运行 e2e 与构建**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "来源文件改为选择并下拉加载布局"
```

---

### Task 8: 拖拽路径 Spike 与降级决策

**Files:**
- Modify: `src/dst_manager/interfaces/shell.py`（若可行：`ShellBridge.on_files_dropped`）
- Modify: `web/src/api/shell.ts`、`web/src/App.vue`（若可行：拖拽热区接桥）
- Create: `.planning/memos/dst-manager/DMv031-drag-drop-spike.md`（决策记录）

**Interfaces:**
- Consumes: Task 4 的 `ShellBridge`；Task 5 的 `selectAndOpenDst`（App.vue）。
- Produces: 决策记录（可行 → 拖拽路径桥；不可行 → 维持"拖拽热区点击即打开对话框"降级，更新 SPEC-DM-007 §3.2 修订记录）。不产生跨任务代码契约。

- [ ] **Step 1: 时间盒验证（上限半天）**

依次尝试（按可行性排序），每步记录结论：

1. pywebview ≥5 的 `webview.settings` / EdgeChromium 后端是否原生暴露拖拽文件路径（查 changelog 与 issue，写最小 demo 验证：拖一个文件进窗口，控制台打印 bridge 收到的内容）。
2. 若不暴露：在 WinForms 宿主上注册 `IDropTarget`（`DragDropEffects.Copy` + `DataFormats.FileDrop`）拦截后经 `window.evaluate_js()` 转发路径数组——验证 WebView2 窗口句柄可挂接且不与 HTML5 drop 冲突。
3. 任一可行路径需同时验证：拖拽期间页面 JS 不被原生 drop 触发默认导航行为。

- [ ] **Step 2: 落地或降级**

可行：`ShellBridge.on_files_dropped(callback_id)` 注册回调，前端 `selectAndOpenDst` 逻辑抽出 `acceptDstPath(path)` 供 drop 回调复用（含同样的 `.dst` 校验）；e2e 不覆盖拖拽（Playwright 无法模拟 OS 级 drop），手动冒烟记录。

不可行：在 `App.vue` 拖拽热区上保持 `@click="selectAndOpenDst"`（Task 5 已实现），视觉文案注明"点击选择文件"；写决策 memo，并在 SPEC-DM-007 §10 追加修订记录（拖拽降级为点击选择，依据 §3.2 预案）。

- [ ] **Step 3: Commit**

```bash
git add .planning/memos/dst-manager/DMv031-drag-drop-spike.md src/dst_manager/interfaces/shell.py web/src/api/shell.ts web/src/App.vue docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md changelog.md
git commit -m "拖拽路径 spike 结论与落地决策"
```

---

### Task 9: 交付收尾与全量验证

**Files:**
- Modify: `changelog.md`（汇总条目）
- Modify: `docs/dst-manager/README.md`（定位与当前状态章节补 v0.3.1 交付说明）
- Modify: `.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md`（状态 `proposed` → `completed`，记录实际验证）
- Modify: `.planning/roadmaps/dst-manager.md`（v0.3.1 行状态 → 已完成）

**Interfaces:** 无代码接口；文档收尾。

- [ ] **Step 1: 全量验证**

```powershell
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
cd web; npm ci; npm run build; npm run test:e2e
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Expected: 全部通过（真实 AutoCAD 系统测试按 `DST_MANAGER_RUN_AUTOCAD=1` 环境可用性执行或记录跳过）。

- [ ] **Step 2: 手动壳验收**

`uv run dst-manager desktop` 走查 SPEC-DM-007 §9 壳冒烟项：启动后端、加载界面、选择 `.dst` 打开、选择模板 `.dwg` 读布局（首次读真实读、二次命中缓存）、关闭确认、退出清理。结果写入 changelog。

- [ ] **Step 3: 更新文档与计划状态**

按 AGENTS.md 规则更新上述四个文档；PLAN-DM-011 正文追加"实际验证"小节（命令与结果、跳过项及原因）。

- [ ] **Step 4: Commit**

```bash
git add changelog.md docs/dst-manager/README.md .planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md .planning/roadmaps/dst-manager.md
git commit -m "v0.3.1 交付收尾与验证记录"
```

---

## 实际验证（2026-09-03）

Task 1-8 已按各自提交记录交付（HEAD=b3deffd），本 Task 9 在仓库主分支完成全量验证与收尾。

### 命令与结果

| 命令 | 结果 |
| --- | --- |
| `uv sync --dev` | 通过（Audited 47 packages） |
| `uv run ruff check .` | 通过（All checks passed） |
| `uv run pytest -q`（默认，未启用真实 CAD） | 退出码 0；**566 tests，500 passed / 66 skipped，0 failures、0 errors** |
| `uv run pytest -q`（`DST_MANAGER_RUN_AUTOCAD=1`，真实 AutoCAD） | 退出码 0；**566 tests，562 passed / 4 skipped，0 failures、0 errors**；62 项真实 AutoCAD 2016/2020 系统测试全数通过 |
| `uv lock --check` | 通过 |
| `cd web && npm ci` | 通过 |
| `cd web && npm run build` | 通过（vue-tsc + vite，零类型错误；`npm run generate:api` 契约漂移门禁保持 LF） |
| `cd web && npm run test:e2e` | **35/35 passed**（47.1s） |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1` | 2016/2020 双版本构建成功，0 error、2 warning（并发真实 CAD 运行占用 DLL 触发的 MSBuild 复制重试，均自动重试成功） |
| 桌面壳启动冒烟 `uv run dst-manager desktop` | 通过：uvicorn 在 `127.0.0.1` 临时端口（本次 2036）承载 `create_app()`，Alembic 迁移（含 0004）执行完成，`/api/health` 返回 `{"status":"ok",...}`，WebView2 窗口创建（标题 `DST Manager`、句柄有效），终止后进程树退出干净、日志无报错 |

真实 AutoCAD 环境：本机 AutoCAD 2016/2020 Core Console（`C:/Program Files/Autodesk/AutoCAD 2016|2020/accoreconsole.exe`）可用，双版本插件 DLL 构建产物在位，私有 `sample/project1` 样本存在；因此本次真实 CAD 测试按环境可用执行并通过，非跳过。关键新增用例 `test_read_layout_names_is_read_only_and_matches_sheet_set`（2016/2020）实测产出 sidecar `{"layouts":["0000 封面"],"version":1}`，与原 Sheet Set 布局一致且原 DWG 时间戳/大小不变。

### 跳过项及原因

- 默认全量 pytest 中的 62 项真实 AutoCAD 系统测试（`tests/system_autocad/test_capabilities.py`）：因未设置 `DST_MANAGER_RUN_AUTOCAD=1` 按门禁跳过；已在上文独立真实 CAD 全量运行中全部执行并通过。
- `tests/unit/test_start_script.py` 4 项真实进程生命周期测试（行 93/157/172）：需另行显式启用，与本次迭代范围无关，维持既有跳过。

### 遗留人工验收项（需活跃桌面人工走查，本会话无法完成）

交互式文件对话框、OS 级拖拽与关闭确认依赖活跃输入桌面的人工操作，本会话仅完成启动冒烟（见上表）；以下按 SPEC-DM-007 §9 与 Task 8 审查决议列为人工验收清单：

1. 启动壳 → 选择 `.dst` 文件打开工作区（原生对话框返回绝对路径后自动打开）。
2. 选择模板 `.dwg`/`.dwt` 读布局：首次真实读取、二次命中缓存（界面可感知，无需 CAD 二次启动）。
3. 拖拽 4 项冒烟（Task 8 审查决议，OS 级拖拽最后一跳需活跃桌面）：(1) 未打开态拖入 `.dst` 直接打开；(2) 拖入非 `.dst` 给出"仅支持 DST 文件"提示且不发起打开；(3) 已打开工作区时拖入被拒绝且不破坏当前工作区；(4) 中文/空格文件名的 `.dst` 拖入正常打开。
4. 关闭确认：存在未发布改动时弹确认框，放弃后回未打开态；确认后工作区与草稿清理。
5. 退出清理：关闭窗口后 uv/应用进程全部退出、临时端口释放。

以上结果验证通过后无需改动代码；若发现回归再单独立项处理。
