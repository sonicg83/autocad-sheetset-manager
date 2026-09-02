---
id: SPEC-DM-005
title: 受控子集整体删除与文件事务规范
status: accepted
owners:
  - dst-manager
created: 2026-09-01
updated: 2026-09-01
related:
  - ARCH-DM-001
  - ADR-DM-001
  - ADR-DM-004
  - PLAN-DM-002
---

# 受控子集整体删除与文件事务规范

## 背景

普通 `delete_sheet` 必须继续拒绝删除子集最后一张图纸。用户要删除整个分册时，需要一个明确承担全部图纸、AcSm 子树和主 DWG 影响的独立命令。

## 范围

本规范只定义直属 `AcSmSheetSet` 的非嵌套 `AcSmSubset` 整体删除；不支持子集自定义属性、嵌套子集、工程外部引用证明或任意 XML/GUID/Handle 编辑。

## 行为

1. `delete_subset` 必须同时携带 `confirm_delete_all_sheets=true` 与 `confirm_delete_main_dwg=true`。
2. 领域投影删除目标 `AcSmSubset`、其全部 `AcSmSheet`、布局引用、自定义属性值和其他完整拥有子树；不得保留空子集。
3. 其余子集和图纸按既有统一派生规则重算图号、标题、布局名、子集显示名和目标 DWG。
4. 预览逐项显示被删子集、全部图纸、主 DWG、其余结构变化、CAD 分流、目标基准和回滚边界，并提示系统不证明工程外部引用。
5. 纯子集删除没有剩余 CAD 工作单元时，Core Console 数量为 0；任务仍进入后台结构发布器，以便原子地替换 DST 并删除 DWG。

## 接口

```json
{
  "type": "delete_subset",
  "subset_id": "g...",
  "confirm_delete_all_sheets": true,
  "confirm_delete_main_dwg": true
}
```

命令属于 Pydantic 判别联合。未知字段、缺少任一确认或确认值不为 `true` 时返回 422。执行仍必须提供当前 `base_revision_id` 与匹配的 `preview_digest`。

## 数据

- `execution_intent.deleted_subsets` 保存 `subset_id` 与规范化主 DWG 路径。
- `path_graph.delete_targets` 只包含最终结构不再使用的旧主 DWG。
- `semantic_diff.structure.before/after` 保存完整人类可读结构；`semantic_diff.dwgs` 以 `action=delete` 列出文件和布局。
- `expected_file_hashes` 同时绑定 DST、所有旧/新目标和来源；删除目标不得缺少执行基准。

## 异常

- `SUBSET_NOT_FOUND`：目标子集不存在。
- `DELETE_SUBSET_SHEETS_CONFIRMATION_REQUIRED` / `DELETE_SUBSET_DWG_CONFIRMATION_REQUIRED`：领域层旁路调用缺少确认。
- `UNKNOWN_REFERENCE_BLOCKED`：待删除子树任一 ID 被子树外未知节点引用。
- `DWG_DELETE_STILL_REFERENCED`：最终存活图纸仍会引用确认删除的主 DWG。
- `PUBLISH_BASE_CHANGED` / `REPREVIEW_REQUIRED`：文件或预览摘要漂移。
- 发布故障按 ADR-DM-004 进入 `ROLLED_BACK` 或 `NEEDS_REVIEW`。

## 安全边界

- 只删除工作区根内、由目标子集当前布局确定且经过基准绑定的主 DWG。
- 不扫描、不声称证明其他 DST、脚本、外部软件或工程目录之外的引用；用户在确认界面承担该外部影响。
- 内部引用检查、派生 DOM 校验、永久 before、同步 journal、整批回滚和启动恢复不可关闭。

## 兼容性

`delete_sheet` 的 `EMPTY_SUBSET` 行为保持不变；旧 `delete_empty_subset` 字段不恢复。现有 `create`、`replace` 发布条目保持兼容，删除仅使用已有 `staged=null` 清单表达。

## 测试

- 完整子树与主 DWG 删除；最后一个子集删除；无 Core Console 的纯删除发布。
- 子树外未知 ID 引用阻断；存活图纸引用同一待删 DWG 阻断；工程外部引用不探测。
- 预览确认字段、摘要和文件基准漂移。
- 发布器新增、替换、删除混合事务的逐点故障回滚、COMMITTED 恢复和永久 before 复核。
