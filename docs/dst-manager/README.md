# DST Manager 文档入口

## 定位与当前状态

2026-09-16 设置中心现有 **13 个**应用配置项：新增 `cad_version`（AutoCAD 2016/2020）与 `ui_theme`（浅色/深色）持久偏好。Topbar 已移除 AutoCAD 版本选择；主题按钮保留为会话级临时切换，刷新/重启仍以配置中心保存值为准。本条取代下方 2026-09-08 历史交付段中的“现为 10 项”数量口径。

DST Manager 面向单人单机真实工程，提供既有 DST/DWG 的检查、受控编辑和安全发布能力。当前版本为 `v0.3.3`。既有 `v0.3` 基线已包含受控图纸集编辑、快速预览/确认阶段 CAD 分流、DST XML 契约校验与可修复加载，以及 `PLAN-DM-002` 的持久草稿、大项目导航、统一写入摘要门禁和子集整体删除；图号、范围、标题、后缀和文件/布局命名均由受控规则统一派生。

2026-09-14 交付 [发布事务按 attempt 嵌套命名空间并拆分 publisher 模块实施计划（PLAN-DM-031，completed）](../../.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md)：发布事务磁盘布局嵌套到 `jobs/<job_id>/attempt-NNN/` 与 `revisions/<job_id>/attempt-NNN/`（`publish()` 新增必填 `attempt` 参数，journal 新增 `"attempt"` 字段）；删除重试时的目录复用（reclaim）机制，重试永远写入新 attempt 目录且所有 attempt 的 journal/before/终态记录永久保留；同 job 跨 attempt 与旧布局 COMMITTED manifest 双层防重复提交守卫（`PUBLISH_OPERATION_CONFLICT`）；旧平铺布局只读兼容，不支持降级；1077 行 `publisher.py` 拆分为 `publish_errors`/`publish_primitives`/`publish_journal`/`publish_recovery` 四个同层模块（application 层 import 零改动）并同步拆分测试。详见 [ARCH-DM-001](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) §8。

2026-09-14 已依据接受的 [前端视觉基础与渐进整改架构（ARCH-DM-007）](architecture/ARCH-DM-007-frontend-ui-foundations.md) 编制 [前端视觉基础与一致性整改实施计划（PLAN-DM-029，proposed）](../../.planning/plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md)：计划以静态契约棘轮和三层令牌为起点，建立公共视觉原语后按属性、图纸目录、图纸/任务浮层、设置、旧页面顺序迁移，再处理图纸树、模态焦点与 `App.vue` 拆分；全量自动门禁和真实 Windows WebView2 100/125/150/200% 缩放复验共同构成关闭条件。
2026-09-14 已依据接受的 [前端视觉基础与渐进整改架构（ARCH-DM-007）](architecture/ARCH-DM-007-frontend-ui-foundations.md) 编制 [前端视觉基础与一致性整改实施计划（PLAN-DM-029，active）](../../.planning/plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md)：计划以静态契约棘轮和三层令牌为起点，建立公共视觉原语后按属性、图纸目录、图纸/任务浮层、设置、旧页面顺序迁移，再处理图纸树、模态焦点与 `App.vue` 拆分；全量自动门禁和真实 Windows WebView2 100/125/150/200% 缩放复验共同构成关闭条件。（2026-09-16 已按用户裁定**关闭**：状态 `completed`，见下段；2026-09-15 状态：**Task 1–11 已全部关闭**，Task 11（`App.vue` 拆分）评审 `Approve`／0 Critical／0 Important，`App.vue` **809 → 450 行**（新增 5 个同层模块共 1174 行）；例外表棘轮 **382 → 320 → 258 → 186 → 128 → 63 → 25 → 16 → 14**（裸违规 15）。Task 12（全量矩阵与收口）进行中：控制器亲跑全量门禁 `test:contracts` **86/86**、`test:unit` **13 文件 / 166 passed**、`build` 0、**全量 e2e 548 passed / 2 flaky（引导期超时，exit 0）**、`ruff` 0、`uv lock --check` 0、`pytest` **1488 项 / 0 failed / 0 errors / 74 skipped** 均通过；视觉证据 **29 张**已登记于 [PLAN-DM-029 资产登记](../../.planning/memos/dst-manager/assets/PLAN-DM-029/README.md)。**关闭尚差**：① 真实 Windows WebView2 100/125/150/200% 复验（Steps 5–6，需用户执行，**尚未完成**）；② 责任 K 的语义字号档位与例外清除（**2026-09-16 已全部实现，例外表 14 → 7**）。2026-09-16 审查修复轮（I1–I3）与用户验收修复轮（模态悬停/表单弹窗间距/属性值 2/4 列切换）落地后，**计划归属方（用户）裁定以当前状态关闭**（真实 Windows WebView2 复验未执行，证据缺口与裁定记录见计划 T12-5 与 Step 8 节）；**状态 `completed`**。）

2026-09-13 交付 [不编号图纸关键字（SPEC-DM-014）](specs/SPEC-DM-014-unnumbered-subset-keywords.md)（实施计划 [PLAN-DM-027](../../.planning/plans/dst-manager/PLAN-DM-027-unnumbered-subset-keywords.md)，completed）：设置 → 编号规则新增「不编号图纸关键字」文本框；子集可编辑标题（大小写不敏感）包含任一关键字时，该子集整体不编号（图号为 `000` 单值而非范围）且**不消耗序号**，对其他子集编号零影响；关键字为空时行为与既有版本完全一致。关键字列表半/全角逗号分隔、上限 50 项/100 字符（超限拒绝保存、绝不截断）。门禁：`ruff` 通过、`pytest -q` 1446 项（1374 passed / 72 skipped / 0 failed）、`npm run build` 通过、`settings-dialog.spec.ts` e2e 22 passed。同日修复其打包版缺陷（设置保存的文件值对预览不可见，根因与修复见 [PLAN-DM-028](../../.planning/plans/dst-manager/PLAN-DM-028-runtime-settings-live-consumption.md)，`completed`；全量回归 `pytest` 1451 项、e2e 全量 490 passed）；打包 EXE 重建与真实桌面验收待用户执行。

2026-09-10 交付 [内置扩展平台与图纸目录 XLSX（PLAN-DM-020，completed）](../../.planning/plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md)（依据 [ARCH-DM-006](architecture/ARCH-DM-006-builtin-extension-platform.md) 与 [SPEC-DM-012](specs/SPEC-DM-012-sheet-catalog-extension.md)）：内置扩展平台与图纸目录功能实现、自动验证和打包守护已完成。2026-09-11 最终评审确认 5 项未被既有测试覆盖的正确性缺陷（[MEMO-DM-031](../../.planning/memos/dst-manager/2026-09-11-plan-dm022-final-review-defects.md)），[PLAN-DM-024](../../.planning/plans/dst-manager/PLAN-DM-024-sheet-catalog-correctness-closure.md)（completed）已同日收口 F1～F5 并使 G7 恢复通过；同日用户真实 Windows 桌面复验推翻原 G8 视觉通过结论（[MEMO-DM-030](../../.planning/memos/dst-manager/2026-09-11-plan-dm020-g8-user-revalidation.md)），视觉整改由 [PLAN-DM-023](../../.planning/plans/dst-manager/PLAN-DM-023-sheet-catalog-visual-convergence.md)（completed，commit `441b85c`/`1cf0a8f`/`0d69e45`/`70b23c0`/`241c7b5`/`6acc6e3`）承接并实施完毕，生产证据已入 [SPEC-DM-012 production 目录](specs/assets/SPEC-DM-012/production/)；用户于 2026-09-11 逐对确认 V1～V8 全部关闭并通过 G8。2026-09-12 另完成 [图纸目录数字格式码实施计划（PLAN-DM-026，completed）](../../.planning/plans/dst-manager/PLAN-DM-026-sheet-catalog-number-format-code.md)：字段引用尾部新增 `:0{1,16}` 数字格式码（只做只读导出的输出格式化，不修改 DST/DWG、不写回属性值、不做重编号），预览与 XLSX 贯通，字段浏览器提供格式入口；格式入口的 G8 自动化证据（浅/深主题与 200% 缩放）已入 [SPEC-DM-012 production 目录](specs/assets/SPEC-DM-012/production/)，G9 清单 [MEMO-DM-028](../../.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md) 已追加补零图号为文本单元格的验收项。**仅剩 [G9 真实桌面/Excel 验收（MEMO-DM-028）](../../.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md) 待用户执行并填写结果**，期间 PLAN-DM-020 保持 `active`。（2026-09-13 更正：G9 已于当日由用户整体确认通过，PLAN-DM-020 同日关闭，见下段。）

2026-09-13（历史段末追加）：PLAN-DM-020 的 G9 已由用户在真实 Windows 桌面（pywebview/WebView2）与真实 Microsoft Excel 环境按 [MEMO-DM-028](../../.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md) `### 1.1～1.10` 执行后**整体确认通过**，无遗留缺陷（操作者/日期：用户 / 2026-09-13；逐项字段留空的口径见该 memo §0）。据此 PLAN-DM-020 与其配套的 [PLAN-DM-025（Builtin 扩展全局设置框架，completed）](../../.planning/plans/dst-manager/PLAN-DM-025-extension-global-settings.md) 同日关闭，SPEC-DM-011/012 的 G9 行与两份索引同步，MEMO-DM-028 `status` → `final`。

2026-09-08 交付 [设置中心（PLAN-DM-019，active；自动化验证 703 passed / 72 skipped、e2e 291 passed，G8 截图比对与 G9 真实桌面验收待进行）](../../.planning/plans/dst-manager/PLAN-DM-019-settings-center.md)（依据 [ARCH-DM-004](architecture/ARCH-DM-004-settings-center.md)）：顶部齿轮入口 + 模态对话框，未加载 DST 即可配置 9 个应用配置项（现为 10 项，2026-09-13 新增「不编号图纸关键字」，见 [ARCH-DM-004](architecture/ARCH-DM-004-settings-center.md) §2.1；`settings.json` 只存显式覆盖值、保存即时生效并跨 API/Worker 进程传播）并查看关于页（版本/MIT 协议/外链）。2026-09-13 由 [Builtin 扩展全局设置框架实施计划（PLAN-DM-025，active）](../../.planning/plans/dst-manager/PLAN-DM-025-extension-global-settings.md) 在同一对话框内交付**扩展全局设置框架**：扩展卡片在声明设置时出现「配置」入口，进入同一 `<dialog>` 的平级子视图；`generated` 由宿主按 `ExtensionSettingsProvider` 字段定义生成表单，`custom` 打开编译期白名单组件；设置作用域为当前 Windows 用户、跨工作区共享，乐观并发与预览设置快照门禁（Schema/revision/digest）与核心设置分离；首个真正的全局配置项为图纸目录「输出图纸过滤」（图名命中任一关键词即不写入目录，业务页显示「已过滤 N 张图纸」）。门禁：G4 第三次重开已于 2026-09-12 由用户确认，生产证据入 [SPEC-DM-011](specs/SPEC-DM-011-settings-center-ui.md) §7 与 [SPEC-DM-012 production 目录](specs/assets/SPEC-DM-012/production/)，**G9 真实桌面/Excel 验收仍待用户执行**。

2026-09-07 完成 [桌面壳单实例守卫（PLAN-DM-018，completed；自动化验证 638 passed / 72 skipped，真实桌面双开冒烟待用户复验）](../../.planning/plans/dst-manager/PLAN-DM-018-desktop-single-instance.md)：同一会话只允许一个壳进程，第二个实例弹置顶告警框并在用户确认后把既有窗口还原置前（命名互斥量 + Win32 前台唤起，仅限 `desktop` 入口，不涉及 API 契约与 Worker 链路）。

2026-09-05 完成 [图纸页单表工作区实施计划（PLAN-DM-015，状态 `active`）](../../.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 的功能实施（依据已接受的 [SPEC-DM-009](specs/SPEC-DM-009-sheets-workspace-ui.md)）：图纸页已具备左树右唯一主表、统一范围导航、显示列配置、分页缓冲编辑、参照插入、批量/删除/草稿联动及视口/可访问性回归。用户随后在真实桌面复验中确认并推动关闭 S-07 的系统性视觉差距，包括编辑与列表卡片层级、控件样式、表格分层和交互态、导航拖拽后的列重叠，以及任务浮层挤压主内容；SPEC-DM-006/SPEC-DM-009 已于同日修订，[视觉收敛整改计划（PLAN-DM-017，completed；用户真实桌面复验通过）](../../.planning/plans/dst-manager/PLAN-DM-017-sheets-visual-convergence.md) 已完成。PLAN-DM-015 仅因 S-09 真实 Explorer 验收尚未完成而继续保持 `active`；SPEC-DM-010 已接受（实施计划 PLAN-DM-016）。

2026-09-04 交付 `v0.3.3`（[PLAN-DM-013](../../.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md)，依据 [SPEC-DM-006](specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)）：**纯前端标签化外壳重建，后端零改动**。设计令牌与浅深双主题（§5.1）；发布/删除/恢复等 8 处原生 `confirm()` 改为应用内可访问确认模态（§6.2/§6.9）；`App.vue` 四业务状态域拆分到 composables（useJobMonitor/useCsvImport/useRepair/useRestore）；固定三标签外壳（① 图纸 / ② 属性 / ③ 修订历史，§4.1/§4.2）+ 右缘任务浮层（实施进度/修改预览/诊断）+ 全局 ActionDock 与草稿栈浮窗（§6.8/§6.9 §7.1）+ SSE 任务通知 toast（§6.6）+ 修订历史标签空状态卡与恢复预览接入浮层（§6.5）。全量验证：`uv run ruff check .` 通过、`uv run pytest -q` 547 passed / 72 skipped（619 项，0 失败）、`npm run build` 零类型错误、Playwright e2e 55/55 通过，记录见 [PLAN-DM-013](../../.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md)「实际验证」小节。

2026-09-03 交付 `v0.3.1`（[PLAN-DM-011](../../.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)，依据 [SPEC-DM-007](specs/SPEC-DM-007-v031-shell-and-usability.md)）：新增 pywebview（WebView2）桌面壳，`uv run dst-manager desktop` 为唯一交付入口；前端两态状态机（DST 文件选择/关闭确认/草稿恢复提示/保存状态可见性）、来源文件选择与布局下拉；后端新增 `POST /api/layout-names` 布局名读取端点与全局缓存（SHA-256 → 布局名，SQLite 迁移 0004），Worker 插件新增只读布局枚举命令 `DstGetLayoutNames`（不修改图纸、不 QSAVE）。全量验证与真实 AutoCAD 2016/2020 系统测试记录见 [PLAN-DM-011](../../.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)「实际验证」小节。

2026-08-26 已在私有 `sample/project1` 临时副本上完成 `PLAN-DM-008` 的 AutoCAD 2016/2020 验收：非性能系统矩阵 54/54、并发 1/4/10 性能矩阵 6/6、双版本插件构建成功；全量 Python 为 367 passed、64 skipped，Web E2E 为 18 passed。`rename_only` 不删除/导入布局且保持 Handle，`rebuild` 才回读 Handle；默认并发为 4、合法范围 1–10，任一单元失败均不发布。`PLAN-DM-009` 已完成非 CAD 交付验证（全量 Python 432 passed、66 skipped；Web E2E 19/19）；其真实 AutoCAD 2016/2020 与官方 Sheet Manager 显示验收尚未在该环境运行，保留为 v1.0 发布资格门禁。具体记录见 [PLAN-DM-008](../../.planning/plans/dst-manager/PLAN-DM-008-deferred-cad-validation-and-layout-rename.md) 与 [PLAN-DM-009](../../.planning/plans/dst-manager/PLAN-DM-009-dst-schema-validation-and-repair.md)。

## 当前规范与决策

- [产品愿景（VISION-DM-001）](product/vision.md)
- [已接受的架构基线（ARCH-DM-001）](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)
- [Windows 绿色分发包与一键 release 流程（ARCH-DM-002，已接受）](architecture/ARCH-DM-002-windows-release-packaging.md)
- [版本管理与发布流程（ARCH-DM-003，已接受）](architecture/ARCH-DM-003-versioning-and-release.md)
- [设置中心：应用内配置与关于页（ARCH-DM-004，草稿）](architecture/ARCH-DM-004-settings-center.md)
- [多语言支持架构（ARCH-DM-005，已接受）](architecture/ARCH-DM-005-multilingual-support.md)
- [内置扩展平台首期架构（ARCH-DM-006，评审中）](architecture/ARCH-DM-006-builtin-extension-platform.md)
- [前端视觉基础与渐进整改架构（ARCH-DM-007，已接受）](architecture/ARCH-DM-007-frontend-ui-foundations.md)
- [受控图纸集编辑替代自由调整模型（ADR-DM-001）](adr/ADR-DM-001-controlled-sheetset-editing.md)
- [CAD 单脚本布局重建（ADR-DM-002）](adr/ADR-DM-002-v021-cad-single-script-execution.md)
- [延后 CAD 校验与子集级 CAD 操作分流（ADR-DM-003，已实施）](adr/ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md)
- [正式工程文件删除纳入可恢复发布事务（ADR-DM-004，已接受）](adr/ADR-DM-004-recoverable-file-deletion.md)
- [CAD 工作范围按可证明差异收敛（ADR-DM-005，已实施；部分替代 ADR-DM-003 的「前沿之后必须进入 CAD 工作范围」）](adr/ADR-DM-005-provable-diff-cad-scope.md)
- [实施路线图（ROADMAP-DM-001）](../../.planning/roadmaps/dst-manager.md)
- [当前 Plan 索引](../../.planning/plans/dst-manager/README.md)

产品需求：

- [插件式扩展平台功能需求与要求书（PRD-DM-001，评审中）](product/prds/PRD-DM-001-extensible-capability-platform.md)

功能规范：

- [v0.21 图纸集编辑需求调整规范（SPEC-DM-001，已接受）](specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md)
- [v0.21 CAD 单脚本布局重建需求调整规范（SPEC-DM-002，已接受）](specs/SPEC-DM-002-v021-cad-single-script-execution.md)
- [延后 CAD 校验与子集级 CAD 操作分流规范（SPEC-DM-003，已验收；§3.1/§9 已按 ADR-DM-005 修订为「前沿只作展示、工作单元只由可证明差异决定」）](specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md)
- [DST XML Schema 校验与可修复加载契约（SPEC-DM-004，已接受）](specs/SPEC-DM-004-dst-schema-validation-and-repair.md)
- [受控子集整体删除与文件事务规范（SPEC-DM-005，已接受）](specs/SPEC-DM-005-controlled-subset-deletion.md)
- [单人桌面界面人性化与易用性设计规范（SPEC-DM-006，评审中）](specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)
- [v0.3.1 桌面壳与操作易用性迭代设计规范（SPEC-DM-007，草稿）](specs/SPEC-DM-007-v031-shell-and-usability.md)
- [v0.3.2 命名与模板流程需求变更规范（SPEC-DM-008，已接受）](specs/SPEC-DM-008-v032-naming-and-template-flows.md)
- [图纸页单表工作区设计规范（SPEC-DM-009，已接受；实施计划 PLAN-DM-015，视觉整改 PLAN-DM-017）](specs/SPEC-DM-009-sheets-workspace-ui.md)
- [属性页分区编辑设计规范（SPEC-DM-010，已接受；实施计划 PLAN-DM-016）](specs/SPEC-DM-010-properties-workspace-ui.md)
- [设置中心 UI 设计规范（SPEC-DM-011，已接受；G7 已通过，依据 ARCH-DM-004；2026-09-12 的第三次 G4 重开（SC-17 扩展全局设置入口）已由用户确认，生产实现由 PLAN-DM-025 任务 7/8 交付，G8 扩展配置入口/子视图生产证据已入 §7，G9 已于 2026-09-13 由用户真实桌面验收通过）](specs/SPEC-DM-011-settings-center-ui.md)
- [图纸目录 XLSX 内置扩展设计规范（SPEC-DM-012，已接受；含数字格式码与输出图纸过滤设计，G0～G8 既有基线已通过——格式入口的门禁证据已由 PLAN-DM-026 补足，输出图纸过滤由 PLAN-DM-025 交付且过滤证据（部分/全部）已入 production 目录，未重开 G3/G4，G9 已于 2026-09-13 由用户真实桌面/Excel 验收通过）](specs/SPEC-DM-012-sheet-catalog-extension.md)
- [多语言界面与本地化契约规范（SPEC-DM-013，已接受；G0～G7 自动验证部分已闭合，G8 待 D3 裁决、G9 待真实桌面验收，实施计划 PLAN-DM-021 为 `active`）](specs/SPEC-DM-013-multilingual-ui.md)
- [不编号图纸关键字规范（SPEC-DM-014，已接受；增量修订 SPEC-DM-001 的统一派生编号规则，设置项位于「编号规则」分组；实施计划 PLAN-DM-027 已完成，自动化门禁已闭合；因引入新控件类型 `text` 属 M 级，G3/G4/G8/G9 未重开，缺口与待补动作见该计划；2026-09-14「已知代价」（不编号子集之后被迫 `rename_only`）已由 ADR-DM-005 / PLAN-DM-030 关闭；同场景的编号种子缺陷（删除不编号子集使后续子集重编为 0 起）已由 PLAN-DM-032 修复，§行为 3/§行为 5 表述已按实现校正）](specs/SPEC-DM-014-unnumbered-subset-keywords.md)

## 研究与分析

- [图号前导零格式化与格式码惯例调研（RES-DM-001，已接受；方案选型证据，实施计划 PLAN-DM-026 已完成）](research/RES-DM-001-number-format-code-conventions.md)
- [图纸目录标准模板库分发方案调研与提案（RES-DM-002，草稿；提案性质，标准模板库的分发通道与 pack 格式设计，不改动现有实现）](research/RES-DM-002-standard-template-library-distribution.md)

## 指南

- [前端功能设计与实施门禁清单（GUIDE-DM-001，评审中）](guides/GUIDE-DM-001-frontend-design-implementation-gates.md)
- [前端功能设计与实施门禁通俗说明（GUIDE-DM-002，评审中）](guides/GUIDE-DM-002-frontend-gates-plain-language.md)
- [配置中心配置项增删改 SOP（GUIDE-DM-003，评审中）](guides/GUIDE-DM-003-settings-config-sop.md)
- [多语言与本地化配置 SOP（GUIDE-DM-004，评审中）](guides/GUIDE-DM-004-multilingual-config-sop.md)
- [Builtin 内置扩展开发指南（GUIDE-DM-005，评审中；以图纸目录为例）](guides/GUIDE-DM-005-builtin-extension-development.md)
- [DST Manager 用户使用指南（GUIDE-DM-006，draft；面向最终用户的安装、日常受控编辑、发布与故障处理）](guides/GUIDE-DM-006-user-guide.md)
- [图纸页单表工作区交互 Demo（模拟数据）](mockups/SPEC-DM-009-sheets-demo.html)
- [属性页分区编辑交互 Demo（模拟数据）](mockups/SPEC-DM-010-properties-demo.html)
- [设置中心交互 Demo（模拟数据，SPEC-DM-011 G4 已冻结：第三次重开于 2026-09-12 由用户确认）](mockups/SPEC-DM-011-settings-demo.html)
- [图纸目录交互 Demo（模拟数据，SPEC-DM-012 G4 已冻结）](mockups/SPEC-DM-012-sheet-catalog-demo.html)
- [多语言界面交互 Demo（模拟数据，SPEC-DM-013 G4 已冻结）](mockups/SPEC-DM-013-multilingual-demo.html)

- [启动、使用和开发说明](../../README.md#一键启动)
- [测试策略](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md#12-测试策略)

当前暂无独立部署指南；开发与测试入口以上述仓库说明、架构基线和前端门禁指南为准。
