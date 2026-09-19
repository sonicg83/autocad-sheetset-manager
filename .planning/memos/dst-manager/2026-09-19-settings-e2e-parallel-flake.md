---
id: MEMO-DM-038
title: 设置中心 e2e 并行 flake 排查（task8-03 输入禁用超时）
status: final
owners:
  - dst-manager
created: 2026-09-19
updated: 2026-09-19
related:
  - PLAN-DM-029
  - PLAN-DM-019
  - PLAN-DM-025
  - PLAN-DM-034
  - ARCH-DM-007
document_kind: memo
---

# 设置中心 e2e 并行 flake 排查（MEMO-DM-038）

## 1. 结论

`web/tests/e2e/settings-extensions-production-evidence.spec.ts` 的 task8-03 在**全量并行**运行下会偶发失败，原因**不是产品缺陷，而是 e2e 测试隔离缺陷**：一份**共享且被刻意改成异常状态的设置文件**，加上 Playwright 的**跨文件并行**。

具体链路：`settings-dialog.spec.ts` 为测试「Schema 过新只读降级」会把共享设置文件写成 `schema_version: 99`；在该窗口内，任何**其它文件**中恰好打开设置对话框的用例都会看到整个对话框只读、所有输入 `disabled`；Playwright 的 `fill` 会等待元素可用，于是等到 30 秒测试超时。**隔离运行该 spec 是确定的**（见 §2 证据）。

现有代码与既有测试断言都没错：schema 过新转为只读是**正确行为**，而且它本身就有专门的用例覆盖。缺陷只在测试夹具的隔离方式。

**本次只做排查，未修改任何源码、测试或配置。** 修法见 §7。

## 2. 症状与证据

失败现场（全量并行运行时）：

```
✘  settings-extensions-production-evidence.spec.ts:358:3
   › Task 8 控件视觉基础正交证据（PLAN-DM-029）
   › task8-03 校验错误：行内错误进入 aria-describedby 且保存禁用        (30.0s)

Error: locator.fill: Test timeout of 30000ms exceeded.
  locator resolved to <input min="30" disabled max="3600" value="120" type="number"
      data-key="worker_lease_seconds" id="settings-input-worker_lease_seconds"
      aria-describedby="settings-hint-worker_lease_seconds" aria-invalid="false" />

✓ 同一条用例 retry #1                                                   (1.3s)
```

两个关键观察：该行**只有 hint、没有 error**，说明行本身渲染正常，只是整体处于只读降级；且 retry 立即通过，说明状态是**时间窗口性**的。

隔离运行则完全确定——`--retries=0` 连跑 5 轮，每轮 15 个用例全绿、0 失败：

```powershell
cd web
npx playwright test settings-extensions-production-evidence --retries=0 --reporter=line   # ×5 轮
```

**这组对比就是「不是产品缺陷」的判据**：产品若会飘，隔离运行同样应该飘。

## 3. 机制

| 步骤 | 事实 | 出处 |
| --- | --- | --- |
| 1 | 唯一一个真实后端（端口 9001）；设置文件固定在 `os.tmpdir()/dst-manager-e2e-settings/settings.json`，经 `DST_MANAGER_SETTINGS_PATH` 交给后端；`workers: 4`、`retries: 1` | `web/tests/global-setup.ts:13-14`、`:42`；`web/playwright.config.ts` |
| 2 | `settings-dialog.spec.ts` 声明 `test.describe.configure({mode: "serial"})`，但 **`serial` 只约束该文件内部**，挡不住别的文件并行；该文件全文调用 `writeSettingsFile(...)` 约 30 次 | `web/tests/e2e/settings-dialog.spec.ts:8`；`web/tests/e2e/fixtures/settings.ts:39-49` |
| 3 | 其中一例把共享文件写成 **`schema_version: 99`**（测试「Schema 过新」只读横幅），断言结束后还原为 1 | `settings-dialog.spec.ts:212`（写入）、`:223`（还原） |
| 4 | 程序侧 `SCHEMA_VERSION = 1`。文件为 99 时 `SettingsResolver.load_snapshot()` 抛 `SettingsSchemaNewer` 并置 `schema_blocked = True` | `src/dst_manager/settings/store.py:27`；`src/dst_manager/settings/resolver.py:76` |
| 5 | `schema_blocked` 直接驱动对话框的禁用：`schemaBlocked = snapshot?.schemaBlocked ?? false`，并以 `:disabled="schemaBlocked"` 传给每个 `SettingsFormRow`；该组件 prop 注释即「schema 过新只读降级：全部输入禁用」 | `web/src/components/settings/SettingsDialog.vue:161`、`:416`；`SettingsFormRow.vue:20` |
| 6 | 并行的另一个文件在窗口内打开设置对话框，`worker_lease_seconds` 处于 `disabled` → `fill` 等 30 秒超时 → 报 flaky | `settings-extensions-production-evidence.spec.ts:358` |

**另一条同样会让对话框只读的路径**（本次未被触发，但排查时需一并知道）：设置文件 schema **过旧**时，端点走 `_schema_older_snapshot()`，同样返回 `schema_blocked=True`（`src/dst_manager/interfaces/api.py:187`）。

## 4. 污染源定位：只有一处是元凶

`settings-dialog.spec.ts` 里有两类「异常场景」写入，但只有一类会导致禁用：

| 写入 | 结果 |
| --- | --- |
| `writeSettingsFile("{ 这不是合法 JSON", 3)`（`:189`） | 走 `SETTINGS_FILE_CORRUPT` 降级，`schema_blocked=False` → **不禁用** |
| `writeSettingsFile({}, 5, 99)`（`:212`） | `schema_version=99 > 1` → `schema_blocked=True` → **整个对话框禁用** |

所以并行时被撞到的只会是 `:212` 这个窗口。这也解释了为什么只有这一个用例偶发、且只在并行时发生。

## 5. 为什么这不是产品缺陷

- Schema 过新的只读降级是**设计行为**，并且有专门用例覆盖（`settings-dialog.spec.ts` 的 SC-12）。
- 隔离运行 5/5 全绿，说明产品在该状态下行为稳定。
- 冲突根因在测试夹具：**共享可变文件 + 跨文件并行**。`web/tests/global-setup.ts:25` 会在 setup 开始时清场重建设置目录，所以**轮次之间不泄漏**——只有同一轮内的并发会撞。

## 6. 与「Builder 构建状态接口撕裂读」的区别（勿混淆）

同一轮交付记录里还有另一个待办缺陷（`.planning/todos/integration/2026-09-18-builder-status-torn-read.md`）。两者性质完全不同：

| | 撕裂读（PLAN-INT-002 暴露） | 本备忘的 flake |
| --- | --- | --- |
| 性质 | **真实产品缺陷**（API 可返回从未存在的状态组合） | **测试隔离缺陷** |
| 用户可见 | 是（构建成功却不显示成果路径） | 否 |
| 隔离下可复现 | 是，约 1/8 | 否，5/5 全绿 |
| 修在哪 | `src/`（事务/隔离语义） | `web/playwright.config.ts` 或测试夹具 |

排查时不要用同一个假设套两者。

## 7. 修法选项

| 方案 | 评价 |
| --- | --- |
| **A. 把会改共享设置文件的 spec 与其它 spec 分开跑**（该组 `--workers=1`，其余照常并行） | **推荐**。全仓只有 `settings-dialog.spec.ts` 使用 `writeSettingsFile`（已核实），因此只需两条命令或两个 project，改动最小且不碰产品代码。 |
| B. 在 `fixtures/settings.ts` 加跨 worker 文件锁：改文件的用例持锁，其它依赖设置状态的用例在打开对话框前取锁 | 也可靠，但要给所有断言设置状态的用例加锁，改动面更大。 |
| C. 把 `:189`/`:212` 两个异常场景改用 page 级 mock | 与 `web/tests/global-setup.ts:1` 的既有红线冲突——「设置中心 e2e 必须真实打后端，禁止 mock `/api/settings`」。不建议破例。 |
| D. 每 worker 一份设置文件 + 各自后端 | 隔离最彻底，但每个 worker 都要起后端，成本最高。 |

方案 A 的具体形态建议：新增一个只跑设置类 spec 的入口（例如 `npm run test:e2e:settings`，`--workers=1`），并从默认并行入口排除该文件；`package.json` 的 `test:e2e` 改为先跑串行组再跑并行组。

## 8. 修复后的验证方法

1. 修复前先固化证据：`npx playwright test settings-extensions-production-evidence --retries=0` 连跑 5 轮应全绿（本备忘已跑过，见 §2）。
2. 实施修改后，全量 `npm run test:e2e` 应**零 flaky**；建议连跑 3 轮全量（每轮约 4 分钟）确认。
3. 若仍偶发，用 `--retries=0` 单跑设置类 spec 与全量各 3 轮对照，确认是否为同一签名。

## 9. 关于与 `f82cb6e`（PLAN-DM-034）的关系

诚实表述：**相关但未证明**。

- 该提交**没有触碰** `settings-dialog.spec.ts` 与 `fixtures/settings.ts`，共享文件与跨文件并行属于既有结构问题。
- 但它给 `extensions-settings.spec.ts` 等增加了用例，总时长与负载上升；`playwright.config.ts` 自己的注释就在描述「单一 vite dev server 过载」的压力。窗口重叠概率随负载上升。
- 观测对比：该提交合并前的验收为「579 passed、零 flaky」，合并后为「581 passed + 1 flaky」。方向一致，但 n=1 vs n=1，不足以定为因果。

## 10. 本次未做的事

- 未修改任何源码、测试、`playwright.config.ts` 或 `package.json`。
- 未修复该 flake（按上述方案 A/B 修复后才应关闭本备忘）。
- 未量化全量运行下的真实 flake 率（单次观测到的是一次，样本过小；若需要，按 §8 连跑 3 轮全量统计）。
