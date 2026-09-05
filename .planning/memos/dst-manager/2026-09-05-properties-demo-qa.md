# 属性页交互 Demo 验证记录

日期：2026-09-05。范围：[SPEC-DM-010](../../../docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md) 的[独立 HTML Demo](../../../docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html)。这是交互评审材料，不是生产验收或实施计划。

## 已验证

- 初始 36 个字段定义、33 项图纸集属性；字段定义默认折叠，值默认展开，名称与工程名称分离。
- 搜索隐藏的输入仍整体加入草稿；修改标记按输入/草稿/基准比较，未加入草稿与待写入可同时显示；对照及单项撤回正确。
- 编辑后不匹配的字段暂留，并不计入隐藏修改数；折叠及跨标签返回保留输入。
- 模拟校验错误保留输入；模拟保存失败保留内存草稿，重试后动作仍为一项。
- 字段定义每页六条；新增、搜索、删除、撤销恢复；图纸/图纸集同名字段身份分离由模型测试覆盖。
- 显式预览后发布强确认，复选确认前不可提交；模拟完成更新演示基准。
- CSV 内置示例的新建/跳过预览与强确认；默认值冲突阻断导入；不静默覆盖默认值。
- 1440×900 桌面浅色和 900×768 窄窗深色截图检查；窄窗 document.scrollWidth 与 innerWidth 均为 900，无整页横向溢出；浏览器本次日志查询无 error/warn。

截图保存在本机演示输出目录，不提交到仓库：`properties-demo-desktop.png`、`properties-demo-narrow.png`。

## 自动验证

- `node --test tests/demo/properties-demo.test.cjs`：9/9 通过。先验证失败，再实现；搜索暂留计数另加回归用例。
- `uv run ruff check .`：通过。
- `uv run pytest tests/unit/test_acsm_custom_properties.py -q`：20/20 通过。

## 边界

- 不连接 API、桌面壳或 AutoCAD，不读取真实 DST/DWG；草稿仅在内存，刷新重置。
- CSV 使用内置案例，不提供真实上传/解析；下载仅包含虚构数据。
- 校验、保存失败及基准冲突为人工场景；没有真实持久化、文件事务或恢复流程。
- 图纸/修订历史标签仅演示切换及内存历史，不替代对应产品页；未完成全面无障碍审计。
- 本任务不修改 `web/`、后端或 PLAN-DM-015。其他 agent 正在生产实现，因此不运行生产 Web 构建/E2E，也不把独立 Demo 检查宣称为生产验证。
- SPEC-DM-010 保持 `review`，等待用户确认。
