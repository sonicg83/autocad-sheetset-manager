# DM v0.3.1 最终评审遗留发现（供 v0.3.2 编制 PLAN-DM-010 时吸收）

来源：PLAN-DM-011 最终整分支评审（2026-09-03，opus，范围 4e7202c..9526839）与逐任务审查 deferred 项 triage。I1（关闭工作区不清理任务/修订状态）已在 commit 9526839 修复并通过突变验证复审，不在本清单。

## 用户已决策的 v0.3.2 事项（2026-09-03 收尾补丁后）

- **`application/service.py` 拆分（1984 行）**：先拆 ~600 行纯辅助簇（`_build_semantic_diff`/`_summarize_*`/`_operation_digest` 等 → 无状态模块，行为零变化），再按功能域拆服务类（drafts/editing/revisions/xml_io/repair），共享小核心（workspace 门禁、修订检查、事务辅助）。已写入 AGENTS.md「代码组织契约」防复发。
- **正常关窗路径的 Worker 回收交互确认**：壳托管 Worker 已落地（`_spawn_worker`/`_shutdown_worker`，单测 6 项 + 整树冒烟），正常关闭窗口时的 terminate 回收逻辑由单测覆盖，活跃桌面的交互确认并入遗留人工验收项。

## 最终评审 Minor（M1-M7，均留 v0.3.2）

| # | 位置 | 问题 | 备注 |
| --- | --- | --- | --- |
| M1 | web/src/App.vue `draftRecovered` | 计数取 `commands.value.length`，草稿 actions 非空但 cursor=0（全部撤销后关闭重开）时横幅不显示，SPEC §5.2 要求"非空即展示" | 边界缺口 |
| M2 | App.vue `closeWorkspace`+`discardDraft` | discardDraft 遇 DRAFT_CONFLICT 时静默关闭；数据不丢（重开恢复横幅重现），仅提示丢失 | |
| M3 | App.vue 保存失败"重试"按钮 | DRAFT_CONFLICT 时 draftStale 使 scheduleDraftSave 直接 return，按钮可见但无动作（正确路径是冲突重载） | 轻微误导 |
| M4 | App.vue `loadLayoutOptions` | cad_version 硬编码 "2020"，与工作区 cadVersion 选择器不一致（2020 裁定已接受，交互一致性缺口） | 改用 cadVersion.value |
| M5 | App.vue 头部 / pyproject.toml | 版本声明 v0.3 / 0.3.0 vs 文档 v0.3.1 | 发布时统一 |
| M6 | App.vue `closeWorkspace` | 不重置 insertSheetForm.sourceFile/sourceLayout 与 layoutOptions（T7-1），重开后直接提交用旧模板路径；预览+确认门禁兜底 | v0.3.2 最高优先级 |
| M7 | tests/system_autocad | .dwt 复制为 source.dwg 仅单测覆盖，真实 CAD 只测了 .dwg | v0.3.2 补双版本 .dwt 实机 |

## Deferred triage 结论（25 条：CLOSE 10 / KEEP 15）

KEEP（随 v0.3.2 处理）：T2-1 SCR 无 _.QUIT 加固、T2-2 sidecar utf-8-sig、T4-2 server.started 无超时、T6-1 保存状态 span 无 role="status"（无障碍）、T6-3 draftSaving 队列瞬时复位、T6-4/T6-5 测试覆盖增强、T6-6 横幅 N 快照、T7-1（=M6）、T7-2 selectTemplateFile 防抖、T7-3 0 布局三态不渲染、T7-4 新建子集表单手输（范围外裁定）、T8-1 注册失败静默、T3-2 LAYOUT_READ_FAILED 400/502 双状态统一。

CLOSE：T1-1/T1-2/T1-3、T2-3、T3-1/T3-3/T3-4、T4-1、T6-2、T9-1、T9-2（明细见 SDD ledger，工作区删除后以本清单为准）。

## 遗留人工验收项（需活跃桌面，见 PLAN-DM-011「实际验证」小节）

1. 选择 .dst 打开、选择模板 .dwg 读布局（首读真实读、二次命中缓存）
2. 关闭确认对话框、退出清理
3. 拖拽冒烟 4 项：拖 .dst 直接打开；非 .dst 提示；打开态拖入拒绝且不破坏现状；中文/空格文件名（basename 匹配）
4. 其余交互走查（恢复横幅、保存状态、布局下拉失败回退）
