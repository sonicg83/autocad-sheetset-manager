// PLAN-DM-029 Task 11：根组件跨域职责的冻结清单与契约测试。
//
// ============================================================================
// Step 1（责任清单）：App.vue 迁移前的五类接线及其迁移目标
// ============================================================================
//
// ① 打开 / 关闭 / 恢复（工作区生命周期）
//    - 现状：`openByPath`/`doOpenByPath`、`closeWorkspace`/`doCloseWorkspace`、
//      `refreshWorkspace`/`doRefreshWorkspace`、`beginWorkspaceLoad`、`loadDraft`、
//      `resetEditingState`/`resetDraftState`/`invalidatePreview`、代次 `workspaceLoadGeneration`，
//      以及桥接层（`hasShell`/`openFolder`/`acceptDstPath`/`selectAndOpenDst`/`registerDropBridge`）。
//    - 迁移目标：`useWorkspaceLifecycle.ts`，只返回根装配需要的 state/actions。
//    - 必须保留的顺序：`draftSaveQueue` 等待 → 代次递增 → `invalidateJobMonitor` →
//      `resetEditingState` → 快照 `baseWorkspace` → `loadDraft`；错误码处理与桥接降级语义不变。
//
// ② 未提交输入与草稿门禁
//    - 现状：草稿栈（`draftActions`/`draftCursor`/`draftVersion`/`draftStale`/`draftCorrupted`/
//      `draftSaveFailed`/`draftSaving`/`draftRecovered`/`lastDraftError`）、`rebuildDraftProjection`、
//      `scheduleDraftSave`（含 DRAFT_CONFLICT 分支）、`undoDraft`/`redoDraft`/`removeDraftAction`/
//      `clearCommands`/`clearDraftRestart`/`discardDraft`/`reloadAfterDraftConflict`、
//      `addCommand`/`addCommandBatch`、以及 `guardAllInputs`/`resolveSharedGuard`/`sharedGuardState`
//      与 `runScopeChange`/`guarded*`。
//    - 迁移目标：`useDraftGuards.ts`（组合既有 `useConfirm`/`useHotkeys`，不复制其职责）。
//    - 必须保留的顺序：两个输入域「先当前主标签、再另一域」的开合顺序；任一步「留在此处」终止 next；
//      同一 `UnsavedInputDialog` 实例不叠加模态。
//
// ③ 页签 / 浮层 / 焦点导航
//    - 现状：`tabDescriptors`/`tabIds`/`selectTab`/`doSelectTab`/`onTabKeydown`、
//      `overlayOpen`/`overlayTab`/`openOverlay`/`jumpOverlay`、`settingsOpen`/`openSettings`、
//      扩展页贡献 `extensionPages` 与 `extensionsPanel`、`guardExtensionListReplace`。
//    - 迁移目标：`useShellNavigation.ts`（组合既有 `useShellTabs`，不复制其职责）。
//    - 必须保留的顺序：切换页签先过图纸目录页草稿闸门；重复点击当前页签不重开闸门但修订历史仍重载列表。
//
// ④ 页面事件 → 命令 / API 的编排
//    - 现状：`submitCommands`、`queueDelete`/`queueDeleteSubset`/`queueDeleteProperty`/
//      `queueBulkSheetProperty`/`applyBulkBatch`、`showPreview`/`execute`、`write`、`dock` 门禁与
//      `useHotkeys` 的四个动作，以及布局读取与模板选择的桥接（`loadLayoutOptions`/`select*TemplateFile`）。
//    - 迁移目标：`useWorkspaceCommands.ts`，只编排既有 `createCommand`、draft/project helpers 与页面 emit，
//      不复制后端最终校验。
//
// ⑤ 纯壳层渲染
//    - 现状：`<template>` 中的 TopBar / TabBar / TaskOverlay / ActionDock / ConfirmModal /
//      SettingsDialog / UnsavedInputDialog / ToastHost 装配与三层可见区块。
//    - 迁移目标：`WorkspaceShell.vue`（纯展示，**不得**导入 API client、draft helpers 或业务 composable）。
// ============================================================================

import {describe, expect, test} from "vitest";
// RED（Step 2）：下列模块在实现前不存在 → 导入失败即为 RED 证据。
import {useWorkspaceLifecycle} from "./useWorkspaceLifecycle";
import {useDraftGuards} from "./useDraftGuards";
import {useShellNavigation} from "./useShellNavigation";
import {useWorkspaceCommands} from "./useWorkspaceCommands";

describe("根组件跨域职责的模块边界", () => {
  test("四个组合式函数都已导出且可调用", () => {
    for (const factory of [useWorkspaceLifecycle, useDraftGuards, useShellNavigation, useWorkspaceCommands]) {
      expect(typeof factory).toBe("function");
    }
  });
});

// 说明：本文件只固定「模块边界与导出形状」这类**装配期契约**；行为契约由既有 e2e 与
// 各自模块的单测承担（`sheetCatalogNavigationNeeded` 等业务规则仍归其原所属模块）。
// 之所以不在此挂载整个应用：根组件的正确性主要由四条 e2e 与「重构前后 API 请求序列 +
// 可见文本指纹」的前后比对证明（见 task-11-report.md 的 T11-1(C) 一节）。
