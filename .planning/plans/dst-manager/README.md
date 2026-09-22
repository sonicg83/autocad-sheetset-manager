# DST Manager MVP 后续实施计划

状态：持续规划中；当前能力基线为 v0.2.1（含 PLAN-DM-005、PLAN-DM-006、PLAN-DM-008 与 PLAN-DM-009）。
目标：把当前技术验证型 MVP 完善为可长期、可靠地处理真实工程的单人单机图纸集编辑管理工具。

- [图纸标准属性与 DWG 命名整改实施计划（PLAN-DM-038，proposed）](PLAN-DM-038-standard-properties-and-dwg-naming-remediation.md)：依据 SPEC-DM-017，以普通/派生属性和唯一全局 DWG 命名模板直接替换尚未发布的旧 Schema v1，并重构标准编辑与发布门禁；完成后 PLAN-DM-036 才能基于新契约实施创建流程。
- [图纸标准校验与 HTML JSON 报告实施计划（PLAN-DM-037，proposed）](PLAN-DM-037-standard-validation-reports.md)：从统一验证结果模型生成同源 HTML/JSON 报告，不创建归档包。
- [标准驱动的新图纸集创建实施计划（PLAN-DM-036，proposed）](PLAN-DM-036-standard-driven-sheetset-creation.md)：从已发布标准生成 DST/DWG，经预览和原子发布后直接进入普通工作区。
- [图纸标准平台与标准编辑器实施计划（PLAN-DM-035，completed——Task 1–11 已完成，**仅剩 G9 真实桌面验收待用户执行**；建立官方/用户标准库、封闭规则、模板资产和普通用户标准编辑器；前端按已接受的 [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md) 实现打开优先欢迎页、主从分栏标准库、映射表和独立发布检查页。实际验证：check:api/check:i18n（1253 键）/check:ui/build 全过、test:unit 221、全量 e2e **612 passed / 0 failed**（4.8 分钟）、ruff、pytest **1561 passed / 72 skipped / 0 failed**、alembic 全新库升级到 head、uv lock 全过；双版本 CAD 标准资产检查实测通过（2016/2020 均只读枚举布局且 DWG sha256/mtime 未变），`-k layout` 的 CAD 套件 2 项失败为 PLAN-DM-031 attempt 命名空间后的过期断言（与标准平台无关）；G4/G8 证据各 12 张逐张像素一致，G9 清单见 [assets/SPEC-DM-016](../../../docs/dst-manager/specs/assets/SPEC-DM-016/README.md)；残余风险见计划 §实际验证摘要）](PLAN-DM-035-drawing-standard-platform.md)：建立官方/用户标准库、封闭规则、模板资产和普通用户标准编辑器；前端按已接受的 [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md) 实现打开优先欢迎页、主从分栏标准库、映射表和独立发布检查页。

## 阶段顺序

| 阶段 | 版本目标 | 核心成果 | 前置条件 |
| --- | --- | --- | --- |
| 1 | v0.2 稳定化 | 数据安全、修订恢复、任务自救、多 DWG 有界并行 | 当前 MVP |
| 2 | v0.3 受控日常编辑器 | 草稿、批量属性维护、人类可读预览、修复状态与全写入摘要门禁 | v0.2.1 基线稳定，SPEC-DM-004 门禁已明确 |
| 3 | v0.4 单人工作流与维护支持 | 最近项目、受检查模板、CSV 双契约、健康检查与脱敏诊断 | 阶段 2 完成 |
| 4 | v1.0 Windows 产品化与发布资格 | 安装升级、恢复、保留策略、双版本 CAD 与官方 Sheet Manager 资格 | 阶段 3 完成，发布门禁具备实际证据 |

详细计划：

- [前端文本编辑状态与提交动作对齐实施计划（PLAN-DM-034，proposed——实施与 G8 已完成，**仅剩 G9 真实 Windows 桌面检查待用户执行后关闭**；依据 SPEC-DM-015，统一图纸属性、属性值、图纸目录模板、常规设置与扩展配置的 dirty/revert/invalid 状态、可见提示和 clean 写操作守卫；普通表单字段级提示，目录模板采用模板级徽标，并以可聚焦 `aria-disabled` 保留保存焦点锚点。实际验证：Task 1–8 完成（`UiButton.ariaDisabled` + 五处页面对齐），check:i18n 955 键不变、check:ui、test:unit 178、build、全量 e2e **579 passed / 0 failed**（首跑 27 failed 均为旧用例编码已删除的「clean 空保存」例外与 95fe260 顶栏改版遗留过期断言，已按新契约修复）、ruff、pytest 2280 项 / 2202 passed / 78 skipped、uv lock 全过；两处已裁决偏差追记至 SPEC-DM-015 §9；G8 六张证据与 200% 浏览器缩放检查登记于 `.planning/memos/dst-manager/assets/PLAN-DM-034/`；实施记录见计划 §10）](PLAN-DM-034-frontend-text-edit-state-alignment.md)

- [publisher 生产代码剩余拆分实施计划（PLAN-DM-033，proposed；承接 PLAN-DM-031 偏差与 MEMO-DM-036 F3：「两个叶模块 + 编排门面」——新增 `publish_apply.py`（正向应用与结果校验）与 `publish_rollback.py`（回滚、身份保护与清理），`publisher.py` 只留事务编排与公共门面并暂留极薄私有委托维持恢复鸭子调用与故障注入语义；纯移动重构、application 层 import 零改动、只拆生产代码不拆测试文件；完成门禁为 `publisher.py` ≤ 400 行、两个新模块各 ≤ 300 行、全量 `pytest -q` 通过）](PLAN-DM-033-publisher-remaining-split.md)

- [删除不编号子集导致后续子集重编号修复计划（PLAN-DM-032，completed；PLAN-DM-030 验证中发现的第二个缺陷：删除已应用的不编号封面后，紧随其后的 `01 图纸目录` 被重编为 `00 图纸目录` 并按改名进入 CAD。根因：`_number_seed` 读的是**命令前**文档的既有图号，而「不编号子集」排除集合按**命令后**子集列表判定，被删除的封面不在集合里，其 `00`/`000` 就当了编号种子；关键字刚开启（封面仍为 `001`）时删除则使后续子集整体前移。修复：命令前快照判定与命令后判定取并集。TDD：新增 5 例、修复前 `[['00']] != [['01']]` 等 5 项失败。实际验证：`ruff` 通过、`pytest -q` **1481 项 / 1409 passed / 0 failed / 72 skipped**；规范表述见 SPEC-DM-014 §行为 3/§行为 5 与「2026-09-14 追记」）](PLAN-DM-032-delete-unnumbered-subset-number-seed.md)

- [发布事务按 attempt 嵌套命名空间并拆分 publisher 模块实施计划（PLAN-DM-031，completed；消除 job_id 与 attempt 混用导致的重试撞修订目录问题：`jobs/<job_id>/attempt-NNN/` 与 `revisions/<job_id>/attempt-NNN/` 嵌套布局 + `journal["attempt"]` 字段，整体删除 reclaim 证据回收机制（评审发现 #8），重试永远写新 attempt 目录且所有 attempt 证据永久保留、无自动清扫；同 job 跨 attempt/旧布局 COMMITTED manifest 双层防重复提交守卫；旧平铺布局只读兼容、不支持降级；随后将 1077 行 `publisher.py` 拆分为 `publish_errors`/`publish_primitives`/`publish_journal`/`publish_recovery` 四个同层模块并同步拆分测试文件（评审发现 #9），application 层 import 零改动。实际验证：`ruff` 通过、`pytest tests/unit -q` 1262 passed / 4 skipped、`test_api.py` 集成回归通过（Task 2 时全量 unit + test_api 为 1330 passed / 4 skipped）。偏差：`publisher.py` 最终 721 行、超出计划 500-600 预期——计划对 Task 8 迁移量的算术预期有误，残留回滚/提交原语的外移留作后续计划，依赖方向与接口契约已达成；偏差已由 PLAN-DM-033 正式承接）](PLAN-DM-031-publisher-attempt-namespace-and-split.md)

- [数量变化前沿不再强制 CAD 工作范围修复计划（PLAN-DM-030，completed；用户缺陷报告：插入不编号子集（图号 `000`、不消耗序号）时其他子集图号/布局名未变，却仍被生成 `rename_only` 工作单元，每个多启动一次 Core Console。根因：`planning.py` 把 `in_cardinality_scope` 传给 `_cad_operation`，使「数量变化前沿之后」成为操作分流输入；而 `_subset_changed` 的逐张可证明比较已完整覆盖「图号/布局名可能顺移」这一唯一理由。修复：`return "rename_only" if changed else "none"`，前沿字段保留为展示信息，HTTP 契约不变。TDD：先改/新增 4 例、修复前 5 failed / 1 passed。实际验证：`ruff` 通过、`pytest -q` **1476 项 / 1404 passed / 0 failed / 72 skipped**（修复前 1472 项，+4 用例）、稳态复现脚本证明不编号子集后续子集由 `rename_only` 变为 `none` 且 `in_cardinality_scope` 仍为 `true`；前端未改动、真实 CAD 系统测试未执行。决策变更见 ADR-DM-005，规范修订见 SPEC-DM-003 §3.1/§9 与 SPEC-DM-014「已知代价」）](PLAN-DM-030-provable-diff-cad-scope.md)

- [前端视觉基础与一致性整改实施计划（PLAN-DM-029，completed；2026-09-16 经用户裁定关闭，真实 Windows WebView2 复验未执行并如实登记；依据已接受的 ARCH-DM-007，按“基线与门禁 → 公共原语 → 属性/目录/图纸与浮层/设置/旧页面迁移 → 结构治理 → 真实桌面验收”实施；含 TDD、静态契约棘轮、24–30 张正交证据与 Windows 100/125/150/200% WebView2 关闭条件。**进度（2026-09-15）**：**Task 1–11 已全部关闭**；Task 11（`App.vue` 跨域拆分）评审 `Approve`／0 Critical／0 Important，`App.vue` **809 → 450 行**（新增 `WorkspaceShell.vue`、`useShellNavigation`、`useDraftGuards`、`useWorkspaceLifecycle`、`useWorkspaceCommands` 共 1174 行），模板跨轮字节不变、四个 e2e 证据 spec 未改；例外表棘轮 **382 → 320 → 258 → 186 → 128 → 63 → 25 → 16 → 14**（裸违规 15，`check:ui` EXIT 0）。**Task 12（全量矩阵与收口）进行中**：控制器亲跑 `test:contracts` 86/86、`test:unit` 13 文件 / 166 passed、`build` 0、全量 e2e **548 passed / 2 flaky**（引导期超时同一签名，exit 0）、`ruff` 0、`uv lock --check` 0、`pytest` **1488 项 / 0 failed / 0 errors / 74 skipped**（与隔离基线逐值一致）；24–30 张正交证据已登记共 **29 张**（`docs/…/assets/*/production/` 21 张 + `.planning/memos/…/PLAN-DM-029/` 8 张），登记表见 [PLAN-DM-029 资产登记](../../../memos/dst-manager/assets/PLAN-DM-029/README.md)。**关闭尚差**：真实 Windows WebView2 100/125/150/200% 复验（Step 5–6，**需用户执行，尚未完成**）；责任 K 的语义字号档位 + 例外清除**已于 2026-09-16 全部实现**（例外表 14 → 7）；2026-09-16 审查修复轮（I1–I3）与用户验收修复轮（模态悬停/表单弹窗间距/属性值 2/4 列切换）已完成，见计划 Task 12 追记；2026-09-16 审查修复轮（I1–I3）与用户验收修复轮落地后经用户裁定关闭，状态 `completed`（真实桌面复验缺口如实保留）](PLAN-DM-029-frontend-ui-foundations-remediation.md)
- [运行期配置即时生效修复计划（PLAN-DM-028，completed；用户缺陷报告：打包 EXE 内保存「不编号图纸关键字」后新建「封面」子集仍被编号。根因：`create_app` 未把 `RuntimeSettings` 注入 `DstManagerService`，API 进程内服务的运行期字段读取全为构造期快照（`Settings()` = 默认 + env，不含 settings.json 覆盖）；修复为新增统一读取口 `_live_settings()`（先 `refresh_if_changed()` 再取快照、旧 Schema 容忍）并把编号规则、CAD 路径/超时、`cad_max_parallel`、`worker_lease_seconds` 全部改走该口，`create_app` 完成接线。TDD：先写 2 个集成回归（RED：`['001','000'] == ['000','001']`）后修复转绿。实际验证：`ruff` 通过、`pytest -q` **1451 tests / 0 failed / 0 errors / 72 skipped**（+5 用例）、`npm run build` EXIT=0、e2e 全量 **490 passed / 0 failed**（3.1m）；真实 CAD 系统测试未执行；打包 EXE 重建与真实桌面验收（G9）待用户执行）](PLAN-DM-028-runtime-settings-live-consumption.md)
- [不编号图纸关键字实施计划（PLAN-DM-027，completed；依据 SPEC-DM-014，增量修订 SPEC-DM-001 的统一派生编号规则。6 个任务全部实施：`domain/keywords.py` 纯函数模块、领域编号派生（不编号子集图号 `000` 且不消耗序号）、设置层 `text` 控件与保存事务上限校验、应用层 `SuffixOptions` 接线、Web 设置中心文本控件与 e2e、文档与索引同步。实际验证：`ruff` 通过、`pytest -q` 1446 项（1374 passed / 72 skipped / 0 failed）、`npm run build` 通过、`settings-dialog.spec.ts` e2e 22 passed；真实 CAD 系统测试未执行（改动不涉及 SCR/插件/布局重建））](PLAN-DM-027-unnumbered-subset-keywords.md)
- [图纸目录数字格式码实施计划（PLAN-DM-026，completed；依据 SPEC-DM-012 §5.4 与 RES-DM-001，只做只读导出的输出格式化：表达式新增 `:0{1,16}` 格式码、预览与 XLSX 贯通、字段浏览器格式入口。4 个任务全部实施并逐任务评审通过；任务 4 补足格式入口的 G8 自动化证据（浅/深主题截图 + 200% 缩放）入 `docs/dst-manager/specs/assets/SPEC-DM-012/production/`，G9 清单（MEMO-DM-028）已追加 `### 1.9` 待用户执行；全量回归 ruff 通过、pytest 1180 passed / 74 skipped / 0 failed（collected 1254，含评审后补的 19 例；2026-09-12 复核重跑为 1182 passed / 72 skipped / 0 failed，collected 数一致，2 例因环境差异由 skip 转 pass）、unit 40 passed、build 通过（898 键 / 9 域）、E2E 437 passed / 0 failed / 2 flaky（均重跑通过）)](PLAN-DM-026-sheet-catalog-number-format-code.md)
- [Builtin 扩展全局设置框架实施计划（PLAN-DM-025，completed；已按 MEMO-DM-033 关闭 2 个阻断项，并纳入“输出图纸过滤”作为真实设置验证，共 9 项任务。任务 1～9 已全部实施并逐任务评审收口（基 `main` 79c61a3 的 28 个实施/收口提交 + 2 个评审修复轮提交 = 30）；G4 于 2026-09-12 经用户确认（MEMO-DM-034），G8 于 2026-09-13 补 5 张扩展设置与 2 张输出过滤自动化证据（既有冻结件未重取）；全量门禁实测 `ruff` 通过、pytest **1329 passed / 72 skipped / 0 failed**（含两轮评审修复新增用例；PLAN-DM-026 收口时为 1182 passed）、`check:i18n` 938 键 / 9 域、`build` 通过、E2E 首测 **486 passed / 0 failed / 2 flaky**（flaky 成员随机漂移；独立复跑 484 passed / 4 flaky，两次均 exit 0 且 0 failed）；`SettingsDialog.vue` 535 → 469 行。**G9 已于 2026-09-13 由用户真实桌面/Excel 验收整体确认通过**（与 PLAN-DM-020 共用同一次执行，记录见 MEMO-DM-028；逐项字段留空的口径见该 memo §0），与 PLAN-DM-020 同日关闭）](PLAN-DM-025-extension-global-settings.md)
- [扩展卡片基线与布尔开关统一下沉（PLAN-DM-022，completed，依据 SPEC-DM-011 SC-16；3 批次 4 任务全部实施并逐任务评审通过，G8 已覆盖 SC-15/SC-16，G9 真实桌面验收待用户）](PLAN-DM-022-extension-card-baseline.md)
- [多语言支持实施计划（PLAN-DM-021，active；批次一～三与 Task 11/12 已实施，G8 待 D3 裁决、G9 待真实桌面验收）](PLAN-DM-021-multilingual-support.md)
- [图纸目录扩展正确性缺陷收口计划（PLAN-DM-024，completed；MEMO-DM-031 F1～F5 已全部关闭，SPEC-DM-012 G7 已于 2026-09-11 恢复通过，PLAN-DM-023 实施前置已解除）](PLAN-DM-024-sheet-catalog-correctness-closure.md)
- [图纸目录页面视觉收敛整改计划（PLAN-DM-023，completed；任务 1～6 全部完成，14 条新用例先红后绿、全量回归 432 passed / 0 failed，生产证据已入 `docs/dst-manager/specs/assets/SPEC-DM-012/production/`；用户于 2026-09-11 逐对确认 V1～V8 全部关闭并通过 G8）](PLAN-DM-023-sheet-catalog-visual-convergence.md)
- [内置扩展平台与图纸目录 XLSX 实施计划（PLAN-DM-020，completed；12 个原实施任务已完成，G7 由 PLAN-DM-024 恢复通过，PLAN-DM-023 视觉整改已实施且 G8 已由用户于 2026-09-11 重新确认通过；G9 已于 2026-09-13 由用户真实桌面/Excel 验收整体确认通过，计划同日关闭）](PLAN-DM-020-sheet-catalog-builtin-extension.md)；G9 记录见 [MEMO-DM-028](../../memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md)（`final`）。
- [设置中心实施计划（PLAN-DM-019，proposed，依据 ARCH-DM-004 与 SPEC-DM-011；G0～G5 门禁已通过，G4 设计已冻结）](PLAN-DM-019-settings-center.md)
- [桌面壳单实例守卫（PLAN-DM-018，completed；自动化验证通过，真实桌面双开冒烟待用户复验）](PLAN-DM-018-desktop-single-instance.md)
- [图纸工作区与任务浮层视觉收敛整改计划（PLAN-DM-017，completed；用户真实桌面复验通过）](PLAN-DM-017-sheets-visual-convergence.md)
- [属性页分区编辑实施计划（PLAN-DM-016，active，依据已接受的 SPEC-DM-010；任务 1～7 已实施、自动回归全绿，视觉确认与人工矩阵待用户后收口）](PLAN-DM-016-properties-workspace-ui.md)
- [图纸页单表工作区实施计划（PLAN-DM-015，active，依据已接受的 SPEC-DM-009；S-07 已由 PLAN-DM-017 关闭，S-09 真实桌面验收待用户）](PLAN-DM-015-sheets-workspace-ui.md)
- [v0.3.2 命名与模板流程需求变更（PLAN-DM-012，completed，依据 SPEC-DM-008；含 service.py 拆分与 M6/M4）](PLAN-DM-012-v032-naming-and-template-flows.md)
- [v0.3.1 桌面壳与操作易用性迭代（PLAN-DM-011，completed，依据 SPEC-DM-007）](PLAN-DM-011-v031-shell-and-usability.md)
- v0.3.3 桌面界面人性化与易用性重构（PLAN-DM-010，待编制，依据 SPEC-DM-006）
- [延后 CAD 校验与布局批量改名（PLAN-DM-008，已完成）](PLAN-DM-008-deferred-cad-validation-and-layout-rename.md)
- [v0.21 CAD 单脚本布局重建（PLAN-DM-007，已取消：范围由 PLAN-DM-008 吸收）](PLAN-DM-007-v021-cad-single-script-execution.md)
- [v0.21 受控图纸集编辑（PLAN-DM-006，已完成）](PLAN-DM-006-v021-controlled-sheetset-editing.md)
- [v0.2.1 紧急修复：运行时、日志与 AcSm 兼容性（PLAN-DM-005，已完成）](PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md)
- [阶段 1：v0.2 稳定化与多 DWG 并行（PLAN-DM-001，已完成）](PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md)
- [阶段 2：v0.3 日常编辑器（PLAN-DM-002，已完成）](PLAN-DM-002-v0.3-daily-editor.md)
- [阶段 3：v0.4 单人工作流（PLAN-DM-003，计划中）](PLAN-DM-003-v0.4-solo-workflow.md)
- [阶段 4：v1.0 Windows 产品化（PLAN-DM-004，计划中）](PLAN-DM-004-v1.0-windows-productization.md)

## 全局实施原则

- 始终保留 `DST → XML DOM → DST` 受控链路，不开放任意 XML、SCR 或 Shell 输入。
- 正式写入继续采用永久 before 快照、暂存校验、整批发布和失败回滚。
- 多 DWG 并行只发生在任务暂存区；DST 更新和正式发布必须集中、串行、原子执行。
- 同一工作区同一时刻只允许一个写任务；阶段 1 不开放多个通用 Worker 并发领队列。
- 所有真实 CAD 测试只操作私有样本的临时副本。
- 每个阶段都要先通过非 CAD 自动化测试，再执行 AutoCAD 2016/2020 系统测试。
- 新增功能必须包含错误码、日志、恢复路径和用户可理解的提示。
- v0.2.1 紧急修复未验收前，暂停 v0.3 日常编辑器功能开发，先恢复单实例运行和可信日志基线。

## 暂不纳入 v1.0

- 多用户、权限、SSO 和远程任务调度。
- RustFS、DM8、对象存储和跨机器 Worker。
- 任意 AutoCAD 命令、SCR 或 AcSm XML 编辑器。
- Word/PDF 成果生成、图框内容智能生成和模型空间重绘。
- AutoCAD 2025 及以上版本迁移，除非真实项目形成明确需求。
