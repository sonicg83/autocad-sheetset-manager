---
id: MEMO-DB-001
title: PLAN-DB-001 发布证据备忘（Task 12 收口记录）
scope: dst-builder
type: memo
status: active
created: 2026-09-18
updated: 2026-09-18
related:
  - PLAN-DB-001
  - SPEC-DB-001
---

# PLAN-DB-001 发布证据备忘（Task 12 收口记录）

本备忘如实记录 2026-09-18 Task 12 实际执行的验证、环境受限项与待办人工项。结论先行：**开发闭环完成，正式双版本资格未满足**。SPEC-DB-001 保持 `review`，PLAN-DB-001 保持 `active`，唯一剩余门禁见文末。

## 1. 实际执行的验证（命令与结果）

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| Ruff | `uv run ruff check .` | 通过，0 违规 |
| pytest 全量 | `uv run pytest -q` | **2186 passed / 75 skipped / 0 failed**（skip 均为真实 CAD 显式启用门禁与私有样本门禁） |
| uv.lock | `uv lock --check` | 通过（Resolved 70 packages） |
| Builder 迁移全新升级 | `DST_BUILDER_DATABASE_URL=sqlite:///<临时目录>/builder-fresh.dstb uv run alembic -c builder_alembic.ini upgrade head` | 通过（→ `0001_db001_initial`） |
| Manager 迁移全新升级 | `DST_MANAGER_DATABASE_URL=sqlite:///<临时目录>/manager-fresh.db uv run alembic upgrade head` | 通过（→ `0007_db001_builder_handoff`） |
| Manager Web | `cd web && npm ci && npm run build && npm run test:e2e` | build 通过（含 `check:api`/`check:i18n`/`check:ui`）；e2e **555 passed**（契约漂移修复后独立重跑） |
| Builder Web | `cd builder-web && npm ci && npm run build && npm run test:e2e` | build 通过；**e2e 20 passed**（含真实后端全流程：创建项目→资产→计划确认→构建→交接 mock） |
| 双版本 Builder 插件 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_plugins.ps1` | 通过，0 警告 0 错误（2016/2020 各产出 `DstBuilder.AutoCAD.dll`） |
| Builder EXE | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_release.ps1` | 通过，产出 `dist/releases/dst-builder-v0.3.5-win64.zip`（28.8 MB，2026-09-18 重建，详见附录 A） |

### 1.1 真实 CAD 系统测试（显式启用，本机环境探测可用）

探测结论：本机存在 `C:\Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe` 与 `AutoCAD 2020\accoreconsole.exe`；`plugins/builder/autocad{2016,2020}/DstBuilder.AutoCAD.dll` 已构建；私有样本 `sample/project1/GP-0000 封面.dwg`（85 KB，唯一纸空间布局 `0000 封面`）可用。据此以 `DST_BUILDER_RUN_AUTOCAD=1` + `DST_BUILDER_AUTOCAD_<版本>_CONSOLE/_PLUGIN/_SAMPLE_DWG/_SAMPLE_LAYOUT` 显式启用执行。

| 版本 | 命令 | 结果 |
| --- | --- | --- |
| AutoCAD 2020 | `DST_BUILDER_AUTOCAD_VERSION=2020 uv run pytest tests/builder/system_autocad -q` | **通过**（真实布局导入、布局改名/清理、DWG 保存、Handle 与 SHA-256 校验） |
| AutoCAD 2016 | `DST_BUILDER_AUTOCAD_VERSION=2016 uv run pytest tests/builder/system_autocad -q` | **通过**（同上） |

两版本均使用各自匹配的 Core Console 与插件 DLL，未以一个版本结果推断另一个版本。

**执行中发现并修复的真实缺陷（Task 7 插件潜伏缺陷，此前真实测试从未具备环境执行）：**

1. **布局导入策略缺陷**：直接 `WblockCloneObjects` 克隆 Layout 对象到目标库布局字典时，源/目标 DWG 的匿名纸空间块（`*Paper_Space0`）同名，`DuplicateRecordCloning.Ignore` 跳过克隆导致两布局共享同一块表记录，AutoCAD 自动补出默认布局（如“布局1”），最终布局集合校验失败（`DSTBUILDER_FINAL_LAYOUT_SET_INVALID`）。修复（`plugins/src/DstBuilder.AutoCAD/Commands.cs`）：改为在目标库 `CreateLayout` 创建全新布局后**实体级克隆**纸空间内容，再 `CopyFrom` 复制打印设置。
2. **Core Console 保存限制**：`Database.SaveAs` 覆盖当前文档自身已打开路径抛 `eInvalidInput`（同路径各参数形态均复现；另存新路径成功且文档句柄不释放）。修复：插件保存到 attempt 目录内固定派生名 `working.saved.dwg`，进程退出、句柄释放后由 `CoreConsoleDrawingBuilder.build` 收敛回 `working.dwg`（`src/dst_builder/infrastructure/autocad/drawing.py`），并新增回归测试 `test_build_converges_core_console_saved_file_back_to_working_dwg`。
3. 插件保留 `DSTBUILDER_IMPORT=`/`DSTBUILDER_FINAL=` 诊断输出行（与既有 `DSTBUILDER_OK`/`DSTBUILDER_FAILED` 同风格），便于后续真实 CAD 排障。

修复后重跑：fake-CAD 专项 27 passed；真实 CAD 2020 与 2016 系统测试先后通过（2020 先于插件重建通过；2016 首跑失败原因是插件 DLL 未含修复，经 `build_builder_plugins.ps1` 重建双版本后通过）。

### 1.2 Task 12 发现并修复的契约漂移

Task 10 新增 Manager `POST /api/handoffs/open` 后，`web/src/api/openapi.json`/`schema.d.ts` 未重新生成，`npm run build` 的 `check:api` 门禁失败（`OpenAPI 契约已漂移`）。已执行 `cd web && npm run generate:api` 重新生成并提交。同时按收口要求重新生成了 `builder-web/src/api/openapi.json` 与 `schema.d.ts`（含 `GET /api/cadabilities` 与 Task 9/10 端点）。

## 2. 环境受限项与未执行项（不得视为通过）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 官方 Sheet Set Manager 打开生成的 DST | **未执行** | 需要完整 AutoCAD GUI 人工打开验证，无法经 accoreconsole 自动化替代 |
| 真实端到端“成果发布 → Manager 接管 → 初始修订恢复” | **未执行（真实 CAD 链路）** | 自动化覆盖止于 fake CAD 全流程与真实单 DWG 生成；真实包发布+真实交接+真实恢复的人工链路待执行 |
| 真实 WebView2 七步 UI 验收 | **未执行（人工）** | builder-web e2e 已覆盖键盘、错误聚焦、浅深主题、最小视口与 200% 缩放的自动化断言，但不构成真实 WebView2 人工验收 |
| 双 GUI 人工双开冒烟 | **未执行（人工）** | Task 11 已做并行启动冒烟，正式资格仍需人工复验 |
| 200% 缩放真实桌面复验 | **未执行（人工）** | 同上，e2e 断言不能替代 |
| Manager 全量真实 CAD 系统测试（`tests/system_autocad`）复跑 | **本轮未执行** | Manager 全量真实 CAD 回归属 Manager 计划自身的资格门禁，本轮仅执行 Builder 侧真实测试；共享原语提取（Task 6）后的 Manager 全量真实回归建议在下一人工验证轮执行 |
| 提交树敏感性核验 | `git ls-files` 扫描 | `sample/project1` 等真实样本与 `plugins/**/bin|obj`、`web/dist`、`.dst-manager-data` 均不在提交树；`sample/golden-template/` 下 11 个**零字节占位文件**系 2026-08-18 `d34417a` 有意追踪的目录结构模板（先于本分支存在），无真实客户数据 |

## 3. 独立代码审查

独立代码审查（0 Critical / 0 Important，Minor 逐项裁决）**待 controller 在本提交后做全分支终审**，结论将回填本备忘。当前不写“已通过”。

## 4. 结论与剩余门禁

- **开发闭环完成，正式双版本资格未满足。**
- SPEC-DB-001 保持 `status: review`；PLAN-DB-001 保持 `status: active`。
- **唯一剩余门禁**：真实双版本发布资格——AutoCAD 2016 与 2020 各自完成官方 Sheet Set Manager 打开生成 DST、真实端到端“成果发布 → Manager 显式接管 → 初始修订恢复”，以及真实 WebView2 七步 UI 人工验收；执行后按 SPEC-DB-001 §12 规则评审流转 SPEC/PLAN 状态。

## 附录 A：Builder EXE 构建结果

- 命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_release.ps1`（退出码 0）。
- 产物：`dist/releases/dst-builder-v0.3.5-win64.zip`（28.8 MB，2026-09-18 04:12 本轮重建）；该脚本依次完成 builder-web `npm ci && npm run build`、双版本插件重建与 PyInstaller 打包，产物全部落在 `dst-builder` 命名空间，与 Manager 分发包并列互不影响。
