# PLAN-DM-048 G4 冻结资产与证据索引

> 状态：G4 冻结包。SPEC-DM-006 于 2026-10-01 转为 `accepted`；用户于 2026-09-30 接受六项原则，并于 2026-10-01 确认本索引关联的固定 HTML 可作为设计冻结基准。截图与 Demo 均为虚构数据，不作为生产页面 G8 证据。

## G4 冻结版本

- 原型：[PLAN-DM-048-hint-classification.html](../../../../../docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html)
- 采集日期：2026-09-30
- 原型 HTML SHA-256：b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d
- 文件大小：46101 bytes
- 原型状态：2026-10-01 经用户确认作为 G4 设计冻结基准；虚构数据，无真实项目路径、用户数据、API 调用或持久化写入
- 状态入口：27 种可复现情形；6 类业务流，另含提示职责页
- 结构预检：103 个唯一 id；11 个 aria-describedby 引用均有目标；27 个情形与页面/区块映射齐全；唯一内嵌脚本通过 node --check
- 用户裁决：接受方向 A、自明标题不加 Lead、Help/Error 顺序与关联、成功反馈和持续状态的分工、warning 与 blocker 并存、四种 Banner tone 与 notice 的 info 色义、900×768 韧性边界、长文本展示和正交截图采样。
- G4 状态：用户确认本固定 HTML 及本索引所列设计材料作为冻结基准。生产实现同态对照、完整键盘行为和 WebView2 验证属于 G8/G9，不表示现有生产实现已符合或验收通过。G5 全量技术映射仍待完成。

## 状态入口

在原型的“选择可复现情形”中选择并应用：

| 情形范围 | 页面/观察点 | 状态 |
| --- | --- | --- |
| 创建：初始、自明标题、Help/Error、同上级共享 Help、多字段错误 | 创建向导 | 候选 |
| 创建：不同上级或图纸组分离 Help | 创建向导 | 候选 |
| 属性：dirty/pending、保存中/成功/失败 | 图纸属性 | 候选 |
| 标准：自明标题、Lead、导入冲突、warning + blocker | 标准管理 | 候选 |
| 设置/目录：加载、待保存、基准冲突、导出失败 | 设置与目录 | 候选 |
| 工作区：恢复、全局错误、修复 warning/blocker | 工作区外壳 | 候选 |
| 提示职责：四种 Banner tone、notice 的 info 语义 | 提示职责 | 候选 |
| 任务：成功、失败、NEEDS_REVIEW、重复终态 | 任务反馈 | 候选 |
| 浅/深主题 | 全部页面 | 可切换候选 |

## G4 截图采样矩阵

共 28 张：7 个页面/展示组各 4 张。视口为 1440×900、1024×768、1120×768、900×768；主题按正交样本轮换 light/dark。900×768 仅作韧性检查，不作正式支持门槛。截图使用浏览器默认缩放（本轮未调整），以全页方式采集，采集前滚动位置为 0；表中同时记录设置的 CSS 视口和图像像素尺寸。JPEG 全页图像可能因纵向内容高度超过视口，且排除滚动条宽度而与 CSS 视口尺寸不同。

| 页面/工作流 | 情形 | CSS 视口 | 主题 | 缩放/滚动 | 图像像素 | 文件与 SHA-256 | 采集/裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 创建向导 | initial | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [create-01-initial-1440x900-light.jpg](screenshots/create-01-initial-1440x900-light.jpg) · 7843b98c8ef9343403e0037e296ab1fd335f2db44a8924b61a31555ee3e2b397 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 创建向导 | help-error | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [create-02-help-error-1024x768-light.jpg](screenshots/create-02-help-error-1024x768-light.jpg) · 3e7a3c59644f0c5bd2d95ea0c0dcb19b7bcac50e72f486b14e8552aa8f4d76c5 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 创建向导 | cascade-same | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [create-03-cascade-same-1120x768-dark.jpg](screenshots/create-03-cascade-same-1120x768-dark.jpg) · d9b3cc0550c32f0b4a2009f1120329b90f9dc72e5f570761ef7945ae8e90d0e2 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 创建向导 | multi-error | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 884×989 | [create-04-multi-error-900x768-light.jpg](screenshots/create-04-multi-error-900x768-light.jpg) · d081532ea5a91bbe728b140a590e64f1103824dea8340cebd2402bf6e0b02277 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 提示职责 / Banner | four-banner-tones | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1424×1150 | [feedback-01-four-banner-tones-1440x900-light.jpg](screenshots/feedback-01-four-banner-tones-1440x900-light.jpg) · fd8bd69e1aa981b1a77ed7d0953fe2db449f47362309f811b91d6f72e9d4bd64 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 提示职责 / Banner | four-banner-tones | 1024x768 | dark | 默认缩放未调整；滚动 0；全页 | 1008×1168 | [feedback-02-four-banner-tones-1024x768-dark.jpg](screenshots/feedback-02-four-banner-tones-1024x768-dark.jpg) · 95dbcaa7f98012f0e18623d333337dd466f27c186646c342e71e3781cbf82502 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 提示职责 / Banner | four-banner-tones | 1120x768 | light | 默认缩放未调整；滚动 0；全页 | 1104×1150 | [feedback-03-four-banner-tones-1120x768-light.jpg](screenshots/feedback-03-four-banner-tones-1120x768-light.jpg) · cdedc492d4eb3a71c05ab74088c815054be4990bb06a924bb4ca2ce5aec6a2c6 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 提示职责 / Banner | four-banner-tones | 900x768 | dark | 默认缩放未调整；滚动 0；全页 | 884×1628 | [feedback-04-four-banner-tones-900x768-dark.jpg](screenshots/feedback-04-four-banner-tones-900x768-dark.jpg) · 9521d51255fb445488accca3988f00617c481220ba5dfa47d12ec797873db2d4 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 任务反馈 | success | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [jobs-01-success-1440x900-light.jpg](screenshots/jobs-01-success-1440x900-light.jpg) · 166cbc404de1a539153490d13d4583295b12045cf9da7190f5e6fcee3014ec8b | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 任务反馈 | failed | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [jobs-02-failed-1024x768-light.jpg](screenshots/jobs-02-failed-1024x768-light.jpg) · 32ff0a56576bc7123b5a327ac8968957ff4250167985c09d8e0267162834c1d0 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 任务反馈 | review | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [jobs-03-review-1120x768-dark.jpg](screenshots/jobs-03-review-1120x768-dark.jpg) · 566a27fa362ce66f95659d1e163819f64cd61b3e05d67e73e0cb2436a215569d | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 任务反馈 | duplicate | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 900×768 | [jobs-04-duplicate-900x768-light.jpg](screenshots/jobs-04-duplicate-900x768-light.jpg) · e1a2e7fbac9af811820571318e53e4b1592a8eb56ba3883288db99deb0eb5b2b | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 图纸属性 | dirty-pending | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [properties-01-dirty-pending-1440x900-light.jpg](screenshots/properties-01-dirty-pending-1440x900-light.jpg) · afd23b49b1bd65c2b12bf7a900eb157604bc278deec27be16ed753fcc1b5c385 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 图纸属性 | saving | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [properties-02-saving-1024x768-light.jpg](screenshots/properties-02-saving-1024x768-light.jpg) · f4cf18339b66a4d9c45ba13ba6de63beef5418da571c2ad1181a09f96cf7fea4 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 图纸属性 | saved | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [properties-03-saved-1120x768-dark.jpg](screenshots/properties-03-saved-1120x768-dark.jpg) · 1e72cf45396b452ead2f686c08cb63937c60e412291462fae73133fa4dde204f | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 图纸属性 | save-failed | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 900×768 | [properties-04-save-failed-900x768-light.jpg](screenshots/properties-04-save-failed-900x768-light.jpg) · 19a90953b6580e5c0d868d9d3ec627b61984a56e53ff3ce0b665b0340e9ec6be | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 设置与目录 | loaded | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [settings-01-loaded-1440x900-light.jpg](screenshots/settings-01-loaded-1440x900-light.jpg) · 283a0f357baf7e8a435e28afb8da844bf21e7ce962c12e9b4de6b6628500ba88 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 设置与目录 | dirty | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [settings-02-dirty-1024x768-light.jpg](screenshots/settings-02-dirty-1024x768-light.jpg) · 8eab7e4fda294d2d2223ac68df61bccb62944427d56226338426f9f285453836 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 设置与目录 | conflict | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [settings-03-conflict-1120x768-dark.jpg](screenshots/settings-03-conflict-1120x768-dark.jpg) · 469c85fc902b1f7e09228f8f6530a85c7ac5e5add6d67e08f3dbdad7d54e78ff | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 设置与目录 | export-failed | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 900×768 | [settings-04-export-failed-900x768-light.jpg](screenshots/settings-04-export-failed-900x768-light.jpg) · fd7444dd58ce33afdfdde0346356f7fa2b3480a8c76069bfbd562bb29d880511 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 工作区外壳 | ready | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [shell-01-ready-1440x900-light.jpg](screenshots/shell-01-ready-1440x900-light.jpg) · 1416a85347656286d6c9f1a0176600e5acc085c43d40fda52574160e43d51a0d | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 工作区外壳 | global-error | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [shell-02-global-error-1024x768-light.jpg](screenshots/shell-02-global-error-1024x768-light.jpg) · 2e39f7bfdaadfe7187a01dfb3b4a01fcd5b703e9d702a2bff627caff748994d4 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 工作区外壳 | repair-warning | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [shell-03-repair-warning-1120x768-dark.jpg](screenshots/shell-03-repair-warning-1120x768-dark.jpg) · 182e89c357cff69ab9ca926e248604ff942b92b0aed9de194e54f131518528ea | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 工作区外壳 | repair-blocker | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 900×768 | [shell-04-repair-blocker-900x768-light.jpg](screenshots/shell-04-repair-blocker-900x768-light.jpg) · 4da2e0a0d45e81802253b4f811c7ccd8d25ebf59ee42072e1d0fff4dd0eb63ca | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 标准管理 | overview | 1440x900 | light | 默认缩放未调整；滚动 0；全页 | 1440×900 | [standards-01-overview-1440x900-light.jpg](screenshots/standards-01-overview-1440x900-light.jpg) · 9374de020d3c130776a63df685b921bc819506e068fd947d52afda9183a0ebef | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 标准管理 | lead | 1024x768 | light | 默认缩放未调整；滚动 0；全页 | 1024×768 | [standards-02-lead-1024x768-light.jpg](screenshots/standards-02-lead-1024x768-light.jpg) · 7c1c18a8b13603bbcfe813102ade844e809294e6c44fd47261e31b0f0c74f2f5 | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 标准管理 | conflict | 1120x768 | dark | 默认缩放未调整；滚动 0；全页 | 1120×768 | [standards-03-conflict-1120x768-dark.jpg](screenshots/standards-03-conflict-1120x768-dark.jpg) · 10313c32cb00ea03169c575169493ccdcecb7d865aa697ed41e90665373c504a | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |
| 标准管理 | warning-blocker | 900x768 | light | 默认缩放未调整；滚动 0；全页 | 900×768 | [standards-04-warning-blocker-900x768-light.jpg](screenshots/standards-04-warning-blocker-900x768-light.jpg) · 7100df14e41823316964688d902120010a5d5a6361c51f667550aee37d100a7b | 2026-09-30；截图已纳入 G4 冻结包（用户于 2026-10-01 确认） |

上述截图均为冻结原型证据，候选原则与 G4 冻结确认日期分别为 2026-09-30、2026-10-01；不代表生产页面 G8 验收通过。不要把 DOM/axe 数量当成播报次数证据。

## 本地预览与限制

预览只绑定 127.0.0.1，服务目录限定为 docs/dst-manager/mockups；采集完成后停止服务。仅对冻结候选页做了有限的 14 个 Tab 焦点、Enter/Space 激活和焦点轮廓抽样；未验证真实生产计算样式、API/持久化、屏幕阅读器播报、穷尽键盘行为或 Windows WebView2。相应结论留给 G5、G8 与 G9。
