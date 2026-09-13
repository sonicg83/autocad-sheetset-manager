# 不编号图纸关键字的 M 级门禁缺口（G8 截图与 G9 桌面验收）

日期：2026-09-13

状态：待办（未立项；来源 `PLAN-DM-027`「门禁分级与证据缺口」与 `PLAN-DM-028`「门禁分级与证据缺口」，用户于 2026-09-13 裁决「暂不补，登记为待办」）

关联：`SPEC-DM-011`、`SPEC-DM-014`、`PLAN-DM-027`、`PLAN-DM-028`、`GUIDE-DM-001`、`GUIDE-DM-003`

## 问题

「不编号图纸关键字」按 GUIDE-DM-003 A-6 引入新控件类型 `text`，属 GUIDE-DM-001 的 **M 级**事项，要求 G0～G9 全部执行。当前已闭合 G0/G1（后端全量 pytest、Ruff）、G5（`npm run build`）、G6/G7 相关项（e2e 全量 490 passed，真实后端），但以下证据仍缺失：

1. **G8（同态生产证据）**：设置 → 编号规则 → 「不编号图纸关键字」文本行在**浅色与深色**主题下的自动化截图与几何/可访问性断言，未归档到 `docs/dst-manager/specs/assets/SPEC-DM-011/production/`（既有冻结件未覆盖该新行）。
2. **G9（真实桌面验收）**：打包 EXE 内「保存关键字 → 新建子集命名为关键字 → 该子集及其图纸不编号、其他子集编号不变 → 重启后再验证一次」的端到端人工验收未执行。

`PLAN-DM-028` 修复（设置保存的运行期字段对预览即时生效）在打包版上的真实生效同样只能由 G9 覆盖——自动化 e2e 只证明源码装配正确，不证明 PyInstaller 产物内装配正确。

## 复现条件 / 执行前提

- 已按 `scripts/build_release.ps1` 重建打包产物（`dist/releases/dst-manager-v*-win64.zip`）；
- 本机存在可用的 AutoCAD 2016/2020 Core Console 与双版本插件（仅 G9 的 CAD 落盘环节需要；纯预览环节不需要）；
- G8 需要设置对话框可渲染的新控件行（已有）。

## 完成条件

1. G8：在既有设置生产证据 spec（`web/tests/e2e/settings-extensions-production-evidence.spec.ts` 或 `settings-demo-visual-evidence.spec.ts`）中按既有模式新增该行的浅/深主题截图用例与结构化断言（字段顺序、`role=textbox`、`aria-describedby`/`aria-invalid` 关系、超限即时错误），归档到 `docs/dst-manager/specs/assets/SPEC-DM-011/production/`，并在 `SPEC-DM-011` §7 登记文件名与对照冻结件；既有冻结件不得重取。
2. G9：按 1～6 步执行并留下可核验记录（被测包 SHA-256、被测 commit、Windows/WebView2 版本、图纸集副本路径）：
   1. 打开设置 → 编号规则 → 不编号图纸关键字，填 `封面，扉页`，保存；
   2. 新建子集「封面」，添加 1～2 张图纸 → 图号应为 `000`（单值，不是范围）；
   3. 检查既有子集编号未变（仍为 `001`、`002`…）；
   4. 新建子集「扉页」，确认同为 `000`；
   5. 关闭应用并重启，重复第 2 步 → 仍为 `000`（验证文件值在重启后生效）；
   6. 把关键字清空保存，再新建「封面」→ 恢复为正常连续编号（回归确认）。
3. 完成后回填 `SPEC-DM-011` §8 门禁表（G8/G9 行）、`PLAN-DM-027` 与 `PLAN-DM-028` 的门禁缺口段落，并把本文件归档。
