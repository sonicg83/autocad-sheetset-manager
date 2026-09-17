<p align="center">
  <img src="web/src/assets/brand/dst-manager-logo-512.png" alt="DST Manager 标志" width="128" />
</p>

<h1 align="center">DST Manager — AutoCAD 市政图纸集管理工具</h1>

<p align="center">
  <a href="#readme">简体中文</a> · <a href="README.en.md">English</a>
</p>

DST Manager 面向单人单机的真实工程，为 AutoCAD 图纸集（DST/DWG）提供**可审计、可恢复**的检查、受控编辑和安全发布能力：每次结构性变更都有可理解的预览、明确的执行边界和可追溯的结果。修改先进入草稿并持久保存，正式发布前不改动任何工程文件；发布失败自动恢复整批发布前状态。

## 核心特性

- **受控编辑**：DST 修改严格走 `DST → XML DOM → DST` 链路，不丢弃未知节点、属性和原有顺序；所有写入先预览、后发布。
- **草稿与发布事务**：修改持久化为草稿栈（支持撤销/重做）；正式写入保留永久 before 快照，多文件发布失败恢复整批发布前状态。
- **CAD 安全执行**：需要 AutoCAD 的操作由匹配版本的 Core Console + Worker 插件按固定命令执行，用户输入不直接拼接为 SCR/Shell/路径命令。
- **命名规则统一派生**：图号、范围、标题、后缀和文件/布局命名由受控规则统一生成，支持"不编号图纸关键字"。
- **图纸页单表工作区**：左树右表导航、显示列配置、分页缓冲编辑、批量操作。
- **属性分区编辑**：图纸集/子集/图纸属性按分区查看与编辑。
- **图纸目录 XLSX 导出**：内置扩展，支持字段引用、数字格式码与输出图纸过滤。
- **修订历史与恢复**：每次发布保留完整修订记录，可预览并恢复到历史版本。
- **设置中心**：界面语言（中/英）、AutoCAD 版本（2016/2020）、界面主题（浅色/深色）、编号规则等 13 项配置，持久化并跨进程生效。
- **桌面壳**：pywebview/WebView2 单窗口桌面应用，双击即用，单实例守卫。

## 快速开始

### 普通用户（绿色免安装包）

1. 获取 `dst-manager-v<版本>-win64.zip` 分发包并解压到任意目录。
2. 运行程序目录内的 `setup.bat`：自动搜索本机 AutoCAD（注册表 + 默认安装目录）定位 `accoreconsole.exe` 并写入 `.env`（2015–2019 → 2016 桶，2020–2024 → 2020 桶；2025+ 暂不支持），幂等不覆盖已有配置。
3. 双击 `dst-manager.exe` 启动桌面应用，选择 `.dst` 文件打开工作区。

数据与草稿保存在 `%LOCALAPPDATA%\dst-manager\`，更新 zip 不会覆盖用户数据；可用 `dst-manager.exe doctor` 自检。

日常操作详见 **[使用指南](docs/dst-manager/guides/GUIDE-DM-006-user-guide.md)**。

### 开发者（源码运行）

环境要求：Windows 11、Python ≥ 3.12（UV 管理）、Node.js（Web 前端）、本机 AutoCAD 2016/2020（结构性 CAD 操作需要）。

```powershell
# 一键启动：初始化环境、同步依赖、构建 Web、升级数据库并启动 API 与 CAD Worker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

服务就绪后自动打开 `http://127.0.0.1:8000`。日常重复启动复用已有依赖与构建。

```powershell
.\scripts\start.ps1 -Action Status   # 查看状态
.\scripts\start.ps1 -Action Logs     # 查看当前实例 UTF-8 日志尾部
.\scripts\start.ps1 -Action Stop     # 停止 API 与 Worker
.\scripts\start.ps1 -SkipSync -SkipWebBuild   # 快速启动
.\scripts\start.ps1 -NoWorker -NoBrowser      # 只启动 Web/API
```

每次启动生成独立 `run_id`，运行日志在 `.dst-manager-data/runtime/<run-id>/`。API 健康检查核对 `run_id`，避免误报旧实例；重复执行 `Start` 复用当前实例。

首次开发可先运行环境初始化脚本（幂等，只补缺失项）：

```powershell
. .\scripts\setup-env.ps1   # 从 .env.example 生成 .env、探测本机 AutoCAD、设置 UV 缓存
uv sync
uv run dst-manager doctor
uv run dst-manager serve    # 手工模式：Web/API 与 Worker 分两个终端运行
uv run dst-manager worker
```

`.env` 与 `DST_MANAGER_*` 变量说明见根目录 `.env.example`。

## 启动与日志排障

- `Status` 显示"状态文件失效"时，执行 `Stop` 会按规范化项目根目录和精确命令行清理本项目受管进程树，不会终止无关程序。
- 端口被无关程序占用时，`Start` 显示占用 PID 并失败，可改用 `-Port` 选择其他端口。
- 检测到遗留或重复 Worker 时，先执行 `Stop`，确认 `Status` 中 API 与 Worker 均为"未运行"后再启动。
- 运行日志按实例独立保留；超过 20 个已停止实例或总大小超过 512 MiB 时只清理最旧且已停止的实例。
- 启动会核对 Alembic revision 与关键物理表/列；出现 `DATABASE_SCHEMA_DRIFT` 时，测试数据库可删除 `.dst-manager-data/dst-manager.db` 后重新启动，不要修改已发布的 migration，应新增 revision。

## 打包与 release

分发给内部同事使用绿色免安装包；开发环境不需要以下流程。

```powershell
# 构建分发包（版本号缺省取 pyproject.toml）
.\scripts\build_release.ps1                # 首次或插件源码变更后不带 -SkipPlugins
.\scripts\build_release.ps1 -SkipPlugins   # 插件 DLL 无变化时复用既有产物

# 一键 release：前置校验 + Ruff/pytest 门禁 + 构建 + 本地 tag
.\scripts\release.ps1 -Version 0.3.4       # 先人工把 pyproject.toml version 与 changelog 更新到位
```

产物为 `dist/releases/dst-manager-v<版本>-win64.zip`。tag 仅打在本地，推送与分发由人工执行。详见 [ARCH-DM-002](docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md) 与 [ARCH-DM-003](docs/dst-manager/architecture/ARCH-DM-003-versioning-and-release.md)。

## 常用验证命令

```powershell
# Python 基线
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head    # 数据库迁移

# Web
cd web
npm ci
npm run build
npm run test:e2e

# 双版本插件
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

真实 AutoCAD 系统测试必须显式启用，并要求本机存在对应 Core Console、插件和私有样本：

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad -q
```

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `src/dst_manager/domain/` | 领域模型与确定性规划（不依赖 FastAPI/文件系统/AutoCAD 进程） |
| `src/dst_manager/application/` | 编排工作区、变更预览、任务和 CAD 执行流程 |
| `src/dst_manager/infrastructure/` | DST/AcSm、AutoCAD、SQLite、文件锁、发布事务适配器 |
| `src/dst_manager/interfaces/` | FastAPI 与 Typer 入口 |
| `web/` | Vue 3 + TypeScript + Vite 本地操作界面 |
| `plugins/src/DstManager.AutoCAD/` | AutoCAD 2016/2020 Worker 插件源码（.NET Framework 4.8） |
| `migrations/` | Alembic 数据库迁移 |
| `scripts/` | 启动、环境初始化、插件与分发包构建脚本 |
| `docs/` | 项目文档入口 |
| `sample/`、`legacy/` | 私有样本与旧工具，仅保留在本地，不进入公开仓库 |

## 安全边界（重要）

- 只读打开工作区不创建 `.dst-manager/`、不修改 DST/DWG、不更新文件时间戳。
- 不绕过发布器直接覆盖原文件；不用字符串替换方式修改 DST XML。
- Web 服务在 MVP 阶段只监听 `127.0.0.1`。
- `legacy/`、`sample/` 等本地私有目录禁止发布到公开仓库。

## 文档导航

- [使用指南（面向最终用户）](docs/dst-manager/guides/GUIDE-DM-006-user-guide.md)
- [完整文档入口](docs/README.md)
- [DST Builder 产品文档](docs/dst-builder/README.md)
- [DST Manager 产品文档](docs/dst-manager/README.md)
- [MVP 架构与验收基线（ARCH-DM-001）](docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)
- [公共 AutoCAD/DST 能力](docs/shared/README.md)
- [跨项目整合](docs/integration/README.md)

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。
