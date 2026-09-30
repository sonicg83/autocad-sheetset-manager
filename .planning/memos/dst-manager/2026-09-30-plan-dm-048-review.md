---
id: MEMO-DM-043
title: PLAN-DM-048 实施计划审查备忘
status: final
owners:
  - dst-manager
created: 2026-09-30
updated: 2026-09-30
related:
  - PLAN-DM-048
  - SPEC-DM-006
  - SPEC-DM-015
  - ARCH-DM-007
  - GUIDE-DM-001
document_kind: memo
---

# PLAN-DM-048 实施计划审查备忘（MEMO-DM-043）

## 日期

2026-09-30

## 审查范围

- 被审查对象：[PLAN-DM-048](../../plans/dst-manager/PLAN-DM-048-hint-classification-and-feedback.md)（`status: proposed`，当前仅获文档编写授权）。
- 权威依据：[SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.3/§6.5/§6.6/§6.7/§7/§9/§10.2/§10.4、[SPEC-DM-015](../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md)（尤其 §9）、[SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)、[SPEC-DM-021](../../../docs/dst-manager/specs/SPEC-DM-021-cascading-enum-properties.md)、[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §5/§7/§9、[GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md) 与仓库 `AGENTS.md`。
- 事实核对对象：`web/src/components/ui/`（`FormField.vue`、`ToastHost.vue`、`UiInput.vue`、`UiSelect.vue`、`instanceId.ts`、`domId.ts`）、`web/src/composables/`（`useToast.ts`、`useJobMonitor.ts`）、`web/src/features/creation/`（`useCreationJob.ts` 与目录结构）、`ProjectStep.vue`/`GroupsStep.vue`、`web/src/styles/`（`tokens.css`/`legacy.css`/`style.css`）、`web/package.json`、`web/tests/e2e/` 相关 spec 与 `fixtures/creation.ts`、`tests/unit/test_job_terminal_statuses.py`、计划索引与 `changelog.md`；共核对 67 个既有路径与 7 个拟新建路径。
- 审查性质：**只读静态审查**。未执行任何测试、构建、浏览器、读屏或真实桌面验收，未修改计划正文、产品代码或测试。
- 结论映射：下文 **F1–F5** 为进入生产修改（任务 2）前建议补齐项；**I1–I9** 为改进项；与评审对话中的问题编号一一对应。

## 已核对无误的关键事实

| 方案断言 | 核对结果 |
| --- | --- |
| `FormField.vue` hint/error 用 `--font-label`、describedBy 先 hint 后 error、无共享说明参数 | 属实 |
| `ProjectStep.vue` 逐字段通用级联说明（`role="note"`），关联不完整 | 属实（`ProjectStep.vue:124`） |
| `GroupsStep.vue` 按字段建立级联说明 ID | 属实（`GroupsStep.vue:102-105`）；清洗方式见 F4 |
| `legacy.css` `.notice` 使用 `--color-danger-bg` | 属实（`legacy.css:32`），共 9 处消费 |
| `ToastHost.vue` 外层 `aria-live` 与子项 `status`/`alert` 嵌套 | 属实 |
| `useToast` 成功 5000ms、失败常驻、上限 4 条移除最旧 | 属实（`slice(-3)`） |
| `useJobMonitor` 有浮层可见抑制与代次保护 | 属实（`shouldSuppress`、`monitorMatches`） |
| `useCreationJob` 创建无普通工作区、需专用监视器 | 属实 |
| 7 个拟新建文件、2 个拟新建测试均不存在 | 属实 |
| 不新增依赖 | 属实（`@vue/test-utils`、`happy-dom` 已在 `devDependencies`） |
| npm 脚本、`rtk npm`/`rtk proxy`、`tests/unit/test_job_terminal_statuses.py` | 属实，命令写法可用 |
| 令牌 13px/12px 与 `tokens→reset→primitives→legacy` 层序 | 属实（`tokens.css:78,80`；`style.css`） |
| SPEC-DM-006 §6.7.1–6.7.5、§10.4（恰为 10 组场景）、§10.2（4 视口×2 主题）存在且口径一致 | 属实 |
| SPEC-DM-015 §9 Provider 409 裁决 | 属实（`SPEC-DM-015:192`） |
| GUIDE-DM-001 十门禁、L 级定义、G9 未闭合保持 `active` | 属实 |
| 计划索引、产品导航、changelog 已同步 PLAN-DM-048 | 属实 |
| 上游计划：PLAN-DM-029、PLAN-DM-047 已完成 | 属实；PLAN-DM-034 正文显示实施与 G8 已完成、仅 G9 待用户执行 |

安全与治理边界成立：不触碰发布链路与 HTTP/SSE/错误码/后端/DB/CAD；候选预览限 `127.0.0.1`；保留必要后果与恢复边界；与 ARCH-DM-001、SPEC-DM-006 §9、`AGENTS.md` 无冲突。

## F：建议在 G6 前补齐（重要）

### F1：G6 没有归属，与"G0～G9 全部登记"矛盾

- 事实：任务 1 标注 `(G0～G5)`，任务 8 标注 `(G7～G9)`，G6 无检查点，而任务 2 即进入生产修改；任务 1 的目标描述为"形成迁移清单与候选基准"。
- 风险：GUIDE-DM-001 §2"上一门未通过，不进入下一阶段"、§6 G6 是 G7 的强制前置门禁，按现文执行会在未登记 G6 结论的情况下改产品代码。
- 建议：任务 1 末尾增加 G6 检查点（或新增"任务 1.5"），把"技术负责人核对追踪矩阵＋业务负责人审阅 Spec/冻结设计"写成任务 2 的启动条件。

### F2：§7 覆盖表不是 GUIDE §6 强制的追踪矩阵

- 事实：GUIDE-DM-001 §6 要求 `ID / Spec 要求 / 设计证据 / 实施任务 / 自动测试 / 设计 QA / 真实验收 / 状态` 列，并双向核对（每条要求有任务、每个任务指回 Spec）；计划 §7 只有"规范要求 → 任务 → 证据"三列，且为章节级而非条目级。
- 建议：按模板重构 §7，或明确任务 1 产出全量矩阵文件并在 G6 检查点登记。

### F3：任务 1 的 G3/G4 交付物不完整，"沿用视觉方向"的成立性存疑

- 事实：任务 1 只有一条"按 GUIDE-DM-001 记录沿用视觉方向、受影响的 G2/G4 重开范围和候选裁决"；G4 必交项（可操作 Demo 的关键状态入口、冻结截图索引、控件尺寸/间距/截断规格、键盘与焦点定义、Demo 与业务契约差异表、用户逐项确认及日期）未落成子步骤或产出路径。§6.7 为 SPEC-DM-006 新增内容（该 Spec 仍 `review`），既有演示是"旧口径讨论材料"，五类提示与四种横幅属于新的视觉状态。
- 建议：明确 G3/G4 是"重开并重新冻结受影响状态"；把 G4 清单项落成任务 1 的具体子步骤与资产路径，并与 I3 的候选 HTML 归位一并处理。

### F4：级联帮助 ID 的编码未落到既有工具，存在碰撞风险

- 事实：`instanceId.ts` 实际位于 `web/src/components/ui/instanceId.ts`，`nextInstanceId(prefix)` 只产生 `prefix-N`；计划 §3.3 未写路径，也未写"表单实例 ID 如何组合进组 ID"。"使用安全编码"应显式复用 `web/src/components/ui/domId.ts` 的 `domIdToken`（`encodeURIComponent`，`PropertiesView.vue:64` 已在用）；否则执行者很可能照抄 `GroupsStep.vue:103` 的 `safe()`——`[^a-zA-Z0-9_-] → "-"` 会让 `a:b` 与 `a-b` 生成同一 ID，与 `shared_help_ids_do_not_collide` 的意图冲突。
- 建议：§3.3 写死组合格式（如 `${domIdToken(instanceId)}-${domIdToken(objectId)}-${domIdToken(sourcePropertyId)}`），并补含 `:`、空格、中文、重复分隔符的碰撞用例。

### F5：任务 4–6 在任务 1 产出前不可独立执行

- 事实：这些任务的步骤只有"运行对应失败用例，按清单迁移"，没有具体测试名、断言或文案行；与 GUIDE G6"每个任务写明准确文件、接口、测试、预期结果"及写作规范"每个步骤只含一件确定的事"有差距。任务 2/3/7 的详细度明显更高。
- 建议：在 §4 加硬性前置——"批次开始前先把任务 1 清单中该批的行冻结为测试名、i18n key 与断言（RED 记录）"；或至少给任务 4/5/6 各补 1–2 条与任务 2/3 同级的示例 RED 用例。

## I：改进建议

1. **任务 8 采集矩阵与截图预算**：`1024/1120/1440/900 × light/dark` 若逐页截图会突破 ARCH-DM-007 §9.3"单页 4–6 张、整轮 24–30 张"预算。建议改为：矩阵用于布局/溢出/计算样式自动断言，截图按 §9.3 正交抽样；200% 自动韧性只覆盖属性/目录/图纸三个密集页面，Windows 缩放仍由真实 WebView2 覆盖（方案后半句已正确）。
2. **补对比度比例断言**：SPEC-DM-006 §10.1 要求按实际渲染前景/背景计算 ≥4.5:1（正文）/3:1（非文本），任务 8 只写"前景/背景匹配"。仓库已有先例（`web/tests/e2e/sheets-layout.spec.ts` 的 contrast 计算），建议复用并对 Banner/五类提示做数值断言。
3. **候选 HTML 归位**：GUIDE-DM-001 §9 建议可操作 Demo 放 `docs/dst-manager/mockups/`，`assets/<PLAN-ID>/` 放去敏持久截图；现有 assets 目录无 HTML 先例。建议候选 HTML 放 mockups，或在任务 1 登记偏差理由。
4. **`UiBanner` tone 命名与 `UiHint` 约束**：`info/success/warning/error` 与 SPEC §6.7.5 的 `notice/warning/error/success` 不完全一致，建议对齐或注明映射；`UiHintProps.tone` 未按 kind 收窄，"Lead/Help 不接受状态色覆盖"缺测试，建议判别联合类型或补 `lead_help_ignore_semantic_tone` 用例。
5. **自建表格关联规则写全**：任务 5"须满足相同关联规则"建议写明包含 `aria-invalid="true"`（`SheetPropertyEditor.vue:104` 已有先例），不只是 describedby。
6. **live region 挂载策略**：`role="status"` 元素若随内容条件挂载，首帧播报可能丢失。建议 §3.2 注明"live region 常驻、只更新文本"，并在任务 8 人工读屏清单补一条内联 Status 播报（现只覆盖错误摘要/字段关联/禁用说明/SSE 终态）。
7. **预登记漏网消费方**：`.notice` 共 9 处消费，`DraftActionsPanel.vue:14-15`（corrupted/stale）未出现在任何任务文件列表；虽然任务 1 盘点会兜底，建议直接预登记，降低疏漏风险。
8. **与 PLAN-DM-034 的证据关系**：034 为 `proposed`（实施与 G8 已完成、仅 G9 待用户执行），048 修改同一批编辑页面。建议明确 048 的 G8 是否延用 034 冻结基准、两者 G9 的先后关系，避免同一页面出现两套冻结基准。
9. **每任务显式提交步骤**：PLAN-DM-047 每个任务都有"只暂存本任务文件并提交"的 Step；048 只有 §1 一句通用约定。建议恢复该步骤（纯只读任务可注明豁免），并与 changelog/证据登记对齐。

其他（可选）：`mergeDescriptionIds` 的 `sharedIds` 建议注明"按空白切分、去重后保持 error→hint→shared 次序"；§6 中 `check:api`/`check:i18n`/`check:ui` 已被 `npm run build` 覆盖，重复列出无害，可注明避免执行者困惑。

## 未验证事项

RED/GREEN 实际行为、真实计算样式、对比度数值、读屏播报、浏览器 200% 与 Windows WebView2 真实缩放均未验证。本次审查不能代替 G4/G6/G8/G9 任何门禁，与计划 §9 的"未执行"声明一致。

## 后续处置建议

1. 若接受 F1–F5，建议修订 PLAN-DM-048 正文（同步 `updated` 与 changelog）后重新进入 G6；I1–I9 可在同轮修订或任务 1 产出时吸收。
2. 本备忘只归档审查结论，不代表计划状态变化；PLAN-DM-048 保持 `proposed`，仍不得据此启动生产修改。
3. 可选：在 PLAN-DM-048 的 `related` 回填 `MEMO-DM-043`，便于后续追踪本轮修订。
