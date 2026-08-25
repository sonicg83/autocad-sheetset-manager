# PLAN-DM-008 任务 7 实施报告

日期：2026-08-26

## 结果

已在 Web 快速预览和确认任务进度中展示真实 CAD 操作。预览直接消费并展示后端的 `cad_validation_deferred`、`cardinality_frontier`、`subset_operations`、`groups[].cad_operation` 和 `source_baselines`；任务文件直接展示 `cad_operation`、`started_at`、`finished_at`、`duration_ms`。

固定标签为：

- `rename_only`：批量改名布局
- `rebuild`：清除并重建布局
- 其他或缺失操作：无需 CAD 操作

预览中的旧“布局来源验证”区域已替换为来源基准和确认后 CAD 校验提示。任务监听、latest-wins、跨工作区隔离和安全重试逻辑未改动。

## TDD 记录

### RED

先新增 `CAD 操作分流` E2E mock 和断言，执行：

```powershell
Set-Location web
rtk npm run test:e2e -- --grep "CAD 操作分流"
```

结果：失败，页面尚未展示“CAD 布局校验将在确认后执行”，符合预期的功能缺失失败。

### GREEN

实现 `App.vue` 后按要求执行了一次目标 GREEN 命令。第一次失败原因为测试定位严格模式同时命中了预览操作表格和 CAD 分组标题；修正断言为 `.first()` 后未重复执行该 GREEN 命令。修正后的同一用例由后续全量 E2E 验证通过。

## 验证

```text
npm run build：通过，vue-tsc -b 与 Vite 构建成功
npm run test:e2e：18 passed
```

未执行 `npm install`，未重复安装依赖。

## 修改文件

- `web/src/App.vue`
- `web/tests/e2e/main.spec.ts`
- 本报告：`.superpowers/sdd/PLAN-DM-008-deferred-cad-validation-and-layout-rename/task-7-report.md`

实现提交 SHA：`50f9757`

## 自审

- 前端仅做后端操作码到固定显示标签的映射，没有重新推导 CAD 资格或操作分类。
- 预览展示源路径、SHA-256、请求布局、数量前沿和子集操作；确认阶段提示明确说明 CAD 校验延后执行。
- 任务文件字段直接来自后端 mock/API 结构，包含操作、开始、结束和耗时字段。
- 保留既有异步代际、工作区隔离、latest-wins、任务监控和重试行为。
- `git diff --check` 通过，除两个所有权文件和本报告外没有修改其他文件；未修改 `changelog.md`，因为任务明确限制所有权范围。

## 审查修复回合 1

- `cadOperationLabel` 现在明确区分 `rename_only`、`rebuild`、`none`、缺失值和未知值；缺失值显示“未提供 CAD 操作”，未知值显示“未知 CAD 操作：<raw>”。任务表调用处直接传入后端字段，不再以 `?? 'none'` 伪装缺失值。
- 旧插入子集 E2E mock 的数量变化前沿、新子集和后续子集按当时的回归语义使用 `rebuild`；两种有效标签由专门 CAD 操作 E2E 覆盖。
- 专门 CAD E2E 增加两个目标 DWG 到 `affected_files` 并在受影响文件区域断言；按 `target_path` 定位两条任务行，分别断言操作、开始时间、结束时间和耗时。
- RED：新增缺失/未知标签断言后，旧实现没有“未提供 CAD 操作”文案而失败；修复后验证通过。
- build：`npm run build` 通过。
- 全量 E2E：18/18 通过。

修复提交 SHA：`4cf2089`

## 审查修复回合 2

- 仅修正 `insert_subset` E2E mock 语义：现有两个子集后以 `ordinal=2`、`placement=after` 插入的新子集位于 `index=2`，前沿显示为“第 3 个子集”。
- `subset_operations` 现在按 `subset-1`、`subset-2`、`subset-new` 展示：前两个为 `none` 且不在数量范围内，新子集为 `rebuild` 且在数量范围内。
- `groups` 只保留需要 CAD 的 `subset-new`，`affected_files` 只保留工作区 DST 与新子集 DWG；E2E 通过子集 CAD 操作表、前沿、受影响文件和执行分组断言这些语义。
- RED：新增断言先运行目标 E2E，因旧 mock 仍返回 `cardinality_frontier.index=0` 而失败。
- GREEN：修正 mock 后目标 E2E `维护属性并按位置创建子集后预览派生变化` 通过（1/1）。
- build：`npm run build` 通过（`vue-tsc -b` 与 Vite 构建成功）。
- 本回合只修改 `web/tests/e2e/main.spec.ts`；`App.vue` 未改动，未重复安装依赖或运行全量 E2E。
- 修复提交 SHA：`7c30bf4`。

## 追加说明

- 按修复回合 2 的要求，本次未重复运行测试或构建，沿用已记录的目标 E2E 1/1 通过、`npm run build` 通过和 `git diff --check` 通过结果。
- 本次仅补充报告并提交报告变更；代码提交 `7c30bf4` 保持不变。
