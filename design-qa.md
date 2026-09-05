# PLAN-DM-017 图纸工作区视觉验收

final result: passed

本记录取代此前 PLAN-DM-015 的视觉通过结论。历史检查范围不足，已被用户真实桌面复验推翻；历史过程见[实施评审](.planning/memos/dst-manager/PLAN-DM-015-sheets-workspace-ui-review.md)。当前以 [PLAN-DM-017](.planning/plans/dst-manager/PLAN-DM-017-sheets-visual-convergence.md) 的实际验证为准。

## 对照范围与限制

- 现有参考为 [1440×900 浅色默认态](.planning/memos/dst-manager/assets/PLAN-DM-015-qa-reference-1440x900.png)，来自 SPEC-DM-009 Demo 的历史渲染。
- 实现截图仅使用虚构夹具，不保存真实客户路径、DST 或 DWG 内容。
- Browser URL 安全策略拒绝打开本地 Demo，并明确禁止改用其他入口绕过，因此本次不重新生成 Demo 参考。
- 深色主题、三类表单、hover、选中和任务抽屉缺少匹配参考图。实现截图及自动化通过不能替代同状态视觉比较，不能宣称 P0/P1/P2 已全面清零。

## 实施与行为验证

已收敛局部控件令牌、独立编辑/列表卡片、38px 表单、确定列宽与内部滚动、树和表格交互背景；任务面板采用 48px 常驻入口栏及覆盖抽屉。计算样式、单元格边界、四宽双主题抽屉几何和滚动保持均有自动化覆盖。完整命令和计数统一记录在计划的“实际验证”，不复制历史通过数。

## 验收结论

- 2026-09-05，用户基于真实桌面连续复验、逐项反馈及修正后的界面，明确确认 PLAN-DM-017 可以完成；本轮视觉验收通过，并关闭 PLAN-DM-015 的 S-07。
- Browser 无法重新渲染本地 Demo、部分状态缺少匹配参考图的限制作为验收过程记录保留；最终结论以用户对真实桌面最终实现的确认及本轮自动化证据为准。
- 在真实 Windows 桌面壳完成 Explorer 选中 DST 的 S-09 验收；浏览器夹具和壳桥 mock 不替代此项。
- S-09 不属于 PLAN-DM-017，PLAN-DM-015 因该项继续保持 `active`。

## 本次截图与比较结果

1440×900 浅色默认参考与最终实现已在同一次比较输入中核对：画布间隔、独立树/列表卡片、表头及行分隔线可见；实现保留既有 320px 可调树宽、搜索/选择操作和固定列宽，因此相较 Demo 列表起点更靠右，操作列在内部横向滚动后可达。这些差异有行为证据，不能直接推导其他状态视觉通过。19 张实现图均已检查：三类表单与列表独立，长表单主体内部滚动且页脚保留；浅深主题的 hover/选中背景可见，抽屉覆盖主区且底部动作仍可见。

| 状态 | 浅色实现 | 深色实现 |
|---|---|---|
| 1440×900 default | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/default-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/default-1440x900-dark.png) |
| 1440×900 edit-subset | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/edit-subset-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/edit-subset-1440x900-dark.png) |
| 1440×900 insert-sheet | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-sheet-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-sheet-1440x900-dark.png) |
| 1440×900 insert-subset | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-subset-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-subset-1440x900-dark.png) |
| 1440×900 hover | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/hover-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/hover-1440x900-dark.png) |
| 1440×900 selected | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/selected-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/selected-1440x900-dark.png) |
| 1440×900 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1440x900-dark.png) |
| 1024×768 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1024x768-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1024x768-dark.png) |
| 1120×768 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1120x768-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1120x768-dark.png) |
| 900×768 overlay | 本计划未要求 | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-900x768-dark.png) |
