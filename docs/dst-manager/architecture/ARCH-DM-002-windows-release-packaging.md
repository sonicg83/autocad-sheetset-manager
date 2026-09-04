---
id: ARCH-DM-002
title: Windows 绿色分发包与一键 release 流程
status: accepted
owners:
  - dst-manager
created: 2026-09-04
updated: 2026-09-04
related:
  - ARCH-DM-001
  - SPEC-DM-007
document_kind: architecture
---

# Windows 绿色分发包与一键 release 流程

> 状态：已接受（2026-09-04 用户确认）
> 定位：为 DST Manager 建立 Windows 免安装绿色分发包（PyInstaller onedir）与本地一键 release 流程，作为项目第一条 release 链路
> 交付形态：`dst-manager-v<版本>-win64.zip`，解压即用；单个 `dst-manager.exe` 兼任桌面壳、CAD Worker 与 CLI 自检

## 1. 目标与边界

### 1.1 目标

- 内部少量同事分发：免安装绿色包，解压即用，无安装向导、无代码签名依赖。
- 一键 release：一条命令完成门禁校验、构建、版本化命名与本地 tag，保证"有 tag 必有可用 zip"。
- 开发态工作流零破坏：`uv run dst-manager ...` 与现有 start.ps1 用法不变。

### 1.2 范围外（YAGNI）

代码签名、安装向导（Inno Setup/NSIS/MSI）、自动更新、应用图标、单文件 exe（onefile）、CI 自动构建（GitHub Actions / Gitea Actions）与远程 Release 发布。后续需要时另行立项。

## 2. 打包方案选型

采用 **PyInstaller onedir + zip 绿色包**。

- 否决 onefile：每次启动解压上百 MB 到临时目录导致启动慢、杀软误报率高、Worker 子进程与 Alembic 数据文件定位需经 `sys._MEIPASS` 临时目录，排查困难；内部分发场景单文件收益不成立。
- 否决嵌入式 Python 直发：无 exe 入口、目录结构混乱，且后续若做正式安装器需要重做。
- onedir 优势：启动快、可就地替换单个 DLL 排查、Worker 直接复用同一个 exe。

运行时前提：Windows 11 自带 WebView2（pywebview 壳无额外运行时负担）；SQLite 随 Python 内嵌；目标机器需要各自安装 AutoCAD（提供 Core Console），本包只携带 Worker 插件 DLL。

## 3. 打包必须适配的代码改动

### 3.1 新增运行时路径模块 `src/dst_manager/runtime.py`

- `is_frozen()`：返回 `getattr(sys, "frozen", False)`。
- `resource_dir()`：打包资源基准目录。开发态返回仓库根（由 `__file__` 向上推导）；frozen 态返回 `Path(sys._MEIPASS)`（onedir 下即 `_internal` 目录）。

三处既有定位逻辑改为经由该模块：

| 位置 | 现状 | 打包后 |
| --- | --- | --- |
| `interfaces/api.py` 静态挂载 | `Path(__file__).parents[3] / "web" / "dist"` | `resource_dir() / "web" / "dist"`（`web/dist` 作为数据文件打入） |
| `infrastructure/persistence/database.py` `migrate_database` | `Path(__file__).parents[4]` 下取 `alembic.ini` 与 `migrations/` | 两者作为数据文件打入，从 `resource_dir()` 定位 |
| `interfaces/shell.py` `_spawn_worker` | `sys.executable -m dst_manager.interfaces.cli worker ...` | frozen 态改为 `[sys.executable, "worker", "--project-root", ...]` 复用同一 exe；开发态不变 |

### 3.2 exe 入口 `packaging/entry.py`

```python
import sys

if getattr(sys, "frozen", False) and len(sys.argv) == 1:
    sys.argv.append("desktop")  # 双击 exe = 打开桌面壳

from dst_manager.interfaces.cli import app

app()
```

复用既有 `cli.py` 的 `desktop`（壳）、`worker`（Worker 子进程）、`doctor`（配置自检）命令；`main.py` 开发态语义不变。

### 3.3 PyInstaller spec `packaging/dst-manager.spec`

- `datas`：`web/dist`（构建脚本先产出）、`alembic.ini`、`migrations/`（含 `versions/`）。
- `hiddenimports`：静态分析探测不到的动态导入，至少包含 `uvicorn.loops.auto`、`uvicorn.protocols.*`、`uvicorn.lifespan.on`、`webview.platforms.edgechromium`、`sqlalchemy.dialects.sqlite`。
- `excludes`：`tavily_cli`、`pytest` 等纯开发依赖（`tavily-cli` 目前在生产依赖中，打包阶段排除以免白占体积；是否从生产依赖移除另行处理）。
- `console=True`：保留控制台窗口。Worker 日志与启动警告（如 Worker 提前退出的 stderr 提示）必须可观察，这是现有设计明确要求；内部分发阶段不做 windowed 美化。

### 3.4 分发包内配置默认值

frozen 态下调整两个默认值，开发态不变：

- `autocad_2016_plugin` / `autocad_2020_plugin`：默认指向 exe 同级的 `autocad2016/`、`autocad2020/` 目录（随包分发的 Worker 插件 DLL）；`.env` 与环境变量覆盖路径保持不变。
- `data_dir`：frozen 态默认改为 `%LOCALAPPDATA%/dst-manager/data`（与既有 `_default_draft_dir` 同风格），避免双击启动时数据写入程序目录、zip 更新时被覆盖。
- Core Console（`accoreconsole.exe`）来自目标机器的 AutoCAD 安装，保持显式配置 + `doctor` 自检，不在包内猜测（对齐 ARCH-DM-001"不通过注册表或 PATH 猜测 AutoCAD"的约束）。

## 4. 构建脚本 `scripts/build_release.ps1`

风格对齐既有 `scripts/build_plugins.ps1`。流程：

1. `web/` 内 `npm ci && npm run build` 产出 `web/dist`。
2. `uv sync --dev`（pyinstaller 加入 `[dependency-groups] dev`，同步更新 `pyproject.toml` 与 `uv.lock`）。
3. 调用 `build_plugins.ps1` 编译双版本插件（支持 `-SkipPlugins` 直接复用已编译产物）。
4. `uv run pyinstaller packaging/dst-manager.spec`。
5. 将 `plugins/autocad2016/`、`plugins/autocad2020/` 的 DLL 拷入 dist 目录，产出 `dist/releases/dst-manager-v<版本>-win64.zip`。

## 5. 一键 release 流程 `scripts/release.ps1`

`build_release.ps1` 只管构建（可独立运行、不做 git 操作）；`release.ps1 -Version 0.3.1` 在其外包一层门禁与版本管理：

1. **前置校验**（任一不过即中止，不产生半成品）：
   - 工作区干净（`git status --porcelain` 为空）且当前在 `main` 分支；
   - `pyproject.toml` 的 `version` 与 `-Version` 一致（版本号由人工修改，脚本只校验，不自动 bump，避免与 changelog 手写内容脱节）；
   - `changelog.md` 已包含该版本章节标题（对齐"每次修改更新 changelog"的仓库约定）；
   - 本地 tag `v<版本>` 不存在。
2. **测试门禁**：`uv run ruff check .` + `uv run pytest -q`（不含真实 CAD 系统测试，按既有约定由运行环境显式启用）。
3. **构建**：调用 `build_release.ps1 -Version <版本>`。
4. **收尾**：打本地 annotated tag `v<版本>`。

失败语义：任何一步失败立即停止并保留现场；tag 是最后一步，保证"有 tag 必有可用 zip"。脚本不自动 push、不发布远程 Release——tag 推送与 zip 分发渠道由人工决定。

## 6. 测试与验证

- `runtime.py` 路径解析单测：`resource_dir()` 支持注入基准，通过 monkeypatch 模拟 frozen/开发两态；三处调用点的既有 pytest 回归全量通过。
- 构建链路验证：`build_release.ps1` 在本机完整跑通一次，产物 zip 解压后：
  - 空库首次启动自动完成 Alembic 迁移并打开壳窗口；
  - `dst-manager.exe doctor` 正确报告随包插件与已配置 Core Console；
  - 拖拽 DST 打开工作区，Worker 认领日志在控制台可见。
- 真实 AutoCAD 2016/2020 发布全流程按既有约定由用户显式启用（`DST_MANAGER_RUN_AUTOCAD=1`），打包链路本身不阻塞于 CAD 环境。
- 交付时更新 `changelog.md` 并记录实际验证结果。

## 7. 与既有架构的关系

- 桌面壳作为唯一交付入口的定位（SPEC-DM-007）不变，本设计只是为其提供分发载体。
- Worker 进程族生命周期（壳拉起、租约、关闭回收）不变，仅 frozen 态下的拉起命令形态改变。
- 发布安全基线（永久快照、锁、发布事务）不涉及；本设计只影响应用自身的分发，不影响 DST/DWG 发布器。
