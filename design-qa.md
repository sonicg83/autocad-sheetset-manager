# PLAN-DM-015 图纸工作区整改设计 QA

## 对照基线

- source visual truth path：`.planning/memos/dst-manager/assets/PLAN-DM-015-qa-reference-1440x900.png`，来源为 `docs/dst-manager/mockups/SPEC-DM-009-sheets-demo.html` 的本地浏览器渲染。
- implementation screenshot path：`.planning/memos/dst-manager/assets/PLAN-DM-015-qa-implementation-1440x900.png`。
- responsive evidence：`.planning/memos/dst-manager/assets/PLAN-DM-015-qa-implementation-900x768-dark.png`。
- focused comparison：`.planning/memos/dst-manager/assets/PLAN-DM-015-qa-reference-focus.png` 与 `.planning/memos/dst-manager/assets/PLAN-DM-015-qa-implementation-focus.png`。
- viewport：桌面 1440×900 CSS px；响应式复验 900×768 CSS px。
- pixels / density：桌面源图与实现图均为 1440×900 px，CSS 视口均为 1440×900，浏览器报告 `devicePixelRatio=1.5`，截图接口输出按 CSS 像素归一化；聚焦图均为 1396×680 px。响应式证据为 900×768 px。
- state：图纸页、全部图纸范围、无草稿、任务栏收起；桌面对照使用浅色主题，响应式补充使用深色主题。源 Demo 与实现证据均使用虚构数据，因此只比较信息层级、密度、换行、入口和布局，不比较动态业务文案逐字一致性；本地浏览器另以真实服务完成打开工作区、主表可见及 console 0 error 检查，但未把私有样本内容保存为文档资产。

## Findings

没有遗留的 P0、P1 或 P2 视觉问题。

- 字体与排版：两者均使用系统无衬线字体与相近的 12–15px 层级。实现中的图纸集名称、导航名称、标题列和文件名均恢复可读；导航最多双行，表格标题列最小 180px、子集列最小 200px，未再出现逐字换行或仅能依赖悬停读取的情况。
- 间距与布局：实现保留 Demo 的顶栏、标签、左树、主表、右侧任务入口和底部操作栏层级。实现让主表填满 ActionDock 上方空间，这是针对生产长列表的有意增强；树与表格各自滚动，900px 下左树进入抽屉，底部按钮未被右侧任务栏遮挡。
- 颜色与视觉 token：浅色对照的表面、边框、强调色、危险色和禁用态与 Demo 语义一致；深色响应式截图无突兀的浅色残留。正文与强调色对比度由现有自动化分别按 4.5:1 和 3:1 门槛验证。
- 图片与资产：该界面没有照片、插画或产品图像资产；本次移除了失真的临时文件夹 SVG，以明确文字按钮替代，不存在低清图片、占位图或伪造图形。
- 文案与内容：顶栏以图纸集名称标识当前对象，完整 DST 路径仅作为辅助 title；主表“文件名”只显示 basename；“打开所在文件夹”入口在名称旁直接可见。生产态额外的匹配数、加载数、搜索范围和发布门禁文案属于已接受功能，不是设计漂移。
- 图标与交互：标签编号、展开箭头和主题切换沿用项目既有样式；文件夹操作不再依赖难辨识图标。树支持鼠标拖动和键盘 Home/End/方向键调宽，长名称、焦点和展开状态均有可访问语义。

## Full-view comparison evidence

1440×900 源图与实现图已在同一次比较输入中检查。整体栅格、顶栏操作顺序、左树/主表比例和底部动作层级保持一致；实现相对 Demo 的主要可见差异是主表纵向填满、默认收起全部子集，以及真实产品的任务栏和字段配置，这些均来自已接受的生产需求。未发现控件裁切、区域重叠、错误圆角/边框或破坏层级的密度漂移。

## Focused region comparison evidence

对顶栏、左树、工具栏和主表密集区域另以 1396×680 聚焦图同屏检查。文件夹入口具备明确文字和 32px 高度；长子集名在 320px 树栏内双行呈现；标题、子集和文件名列保持可读宽度；文件名不含目录。900×768 深色证据进一步确认抽屉触发器、主表与底部“预览变更/确认写入”完整可见。

## Comparison history

1. 整改前审查发现 P1：文件夹入口被全局 padding 压成小点、导航长名称单行裁切、文件名显示完整路径；P2：顶栏显示路径而非图纸集名称、全部子集默认展开、工作区未填满。修复涉及 `TopBar.vue`、`SheetTree.vue`、`SheetTable.vue`、`SheetsView.vue` 与 `App.vue`；首次实现截图显示这些问题已关闭。
2. 首次同视口实现检查发现 P2：树栏加宽后，主表标题列被压到约 46–93px；900px 截图还显示底部确认动作与右侧任务栏边界过近。修复为标题/子集/文件名设置 180/200/240px 最小列宽，并在窄屏为 ActionDock 预留 44px 任务栏空间、收紧间距。
3. 修复后重新构建、复拍并再次同屏比较。1440×900 实现中标题列实测 180px、子集列大于 200px；900×768 深色截图中确认按钮完整位于任务栏左侧。没有新的 P0/P1/P2 发现。

## Open Questions

- 真正的 Windows 桌面壳中点击“打开所在文件夹”并由 Explorer 选中 DST，仍需 S-09 人工系统验收；浏览器态按设计禁用该按钮，自动化已覆盖壳桥参数与降级提示，但不能替代真实 Explorer 证据。

## Implementation Checklist

- [x] 顶栏显示图纸集名称并提供明确文件夹入口。
- [x] 导航支持双行名称、260–420px 调宽与默认渐进展开。
- [x] 文件名列只显示 basename，标题/子集/文件名列保持可读宽度。
- [x] 工作区填满剩余高度，树和表格内部滚动。
- [x] 900px 下左树抽屉化，底部持续操作不被遮挡。
- [x] 同视口源图/实现图与聚焦区域完成二次比较。
- [x] 生产构建、153 项 E2E、Ruff 与 51 项相关 Python 测试通过。
- [ ] 在真实桌面壳完成 Explorer 选中 DST 的 S-09 人工验收。

## Follow-up Polish

- P3：后续可把树宽偏好持久化为应用级 UI 设置；本轮保持会话内调节，避免把界面偏好写入 DST 或项目目录。

final result: passed
