// Task 11 第 11c 轮（Step 4 下半）：未提交输入保护与草稿门禁。
//
// 搬迁纪律（与 11a/11b 一致）：本模块**只搬运**，不改变任何可观测行为——HTTP 路径与载荷、
// 错误码、文案键、模态开合顺序一律保持原样；下方各函数体是 `App.vue` 原文的逐字搬迁。
// 既有职责一律**组合**而不重新实现：确认队列仍来自 `useConfirm`（本模块只调用注入的
// `confirmAction`）、投影仍来自既有 `./drafts`（`projectCommands`/`projectWorkspace`）、
// 草稿读写仍走既有 API client。
//
// ★ 前向引用的断开方式（setup 期存在真实循环）：草稿投影/保存要在运行期用
// `invalidatePreview`/`refreshSheetProjection`，guard 要用 `editor`/`properties`/`sheets`/`active`，
// 而它们由根组件在本模块**之后**创建；反过来 `editor`/`properties` 又消费本模块的
// `addCommand`/`submitCommands`。故这些依赖一律以**懒取值函数**注入，模块只在动作被调用时读取，
// 不在 setup 期解引用（`editor`/`properties` 的取值函数在本模块调用时尚未初始化，调用时才有效）。
import {computed, ref, type Ref} from "vue";
import {ApiError, request} from "../api/client";
import type {ChangeCommand, DraftAction, DraftEnvelope, Workspace} from "../api/contracts";
import {projectCommands, projectWorkspace} from "../drafts";
import {guardSheetCatalogPage} from "./useSheetCatalog";
import type {DraftActionLabel, GuardChoice} from "../features/sheets/types";
import type {ConfirmOptions} from "./useConfirm";
import type {usePropertiesWorkspace} from "./usePropertiesWorkspace";
import type {useSheetEditor} from "./useSheetEditor";
import type {useSheetsWorkspace} from "./useSheetsWorkspace";

/** 图纸页编辑缓冲：范围/筛选改变时可能隐藏当前编辑对象，故需要 context 与脏标记。 */
export type EditorApi = Pick<ReturnType<typeof useSheetEditor>, "context" | "hasUnsavedChanges" | "guard" | "resolveGuard" | "guardState">;
/** 属性页会话缓冲：只参与过闸顺序与共享三选一模态的取值，不承担其内部语义。 */
export type PropertiesApi = Pick<ReturnType<typeof usePropertiesWorkspace>, "guard" | "resolveGuard" | "guardState">;
/** 图纸页筛选快照：范围改变隐藏编辑对象时先还原快照，保持「先还原、再三选一」的既有次序。 */
export type SheetsFilterApi = Pick<ReturnType<typeof useSheetsWorkspace>, "filteredRows" | "snapshotState" | "restoreState">;

export interface DraftGuardsDeps {
  /** 当前工作区（只读引用；投影与保存都要按 id 校验归属）。 */
  workspace: Ref<Workspace | null>;
  /** 工作区只读基准副本：草稿投影的输入，不因草稿变化。 */
  baseWorkspace: Ref<Workspace | null>;
  error: Ref<string>;
  t: (key: string) => string;
  /** 根组件持有的 JSON 深拷贝（草稿保存前快照 actions，避免后续变更影响在途请求体）。 */
  cloneJson: <T>(value: T) => T;
  invalidatePreview: () => void;
  refreshSheetProjection: () => unknown;
  getActive: () => string;
  getEditor: () => EditorApi;
  getProperties: () => PropertiesApi;
  getSheets: () => SheetsFilterApi;
  /** 冲突后重新载入较新草稿：复用根组件已有的刷新路径，不重复实现刷新。 */
  reloadWorkspace: (workspaceId: string) => Promise<void>;
  confirmAction: (options: ConfirmOptions) => Promise<boolean>;
}

export function useDraftGuards(deps: DraftGuardsDeps) {
  const {workspace, baseWorkspace, error, t, cloneJson, invalidatePreview} = deps;

  // —— 草稿栈状态（Step 1 清单第 2 类「草稿栈全部 ref」）——
  /** 当前草稿投影出的命令列表（撤销/重做/移除后重算，不是入栈即真）。 */
  const commands = ref<ChangeCommand[]>([]);
  const draftActions = ref<DraftAction[]>([]);
  const draftCursor = ref(0);
  const draftVersion = ref(0);
  const draftStale = ref(false);
  const draftStaleReasons = ref<string[]>([]);
  const draftCorrupted = ref(false);
  const draftSaveFailed = ref(false);
  /** 最近一次草稿保存错误（字段级错误供编辑器定位）。 */
  const lastDraftError = ref<ApiError | null>(null);
  const draftSaving = ref(false);
  const draftRecovered = ref<number | null>(null);
  /** 保存串行队列：所有写草稿都排在同一条链上，靠它保证版本序。 */
  let draftSaveQueue: Promise<void> = Promise.resolve();

  const hasPropertyDefinitionCommands = computed(() => commands.value.some(item => item.type === "add_custom_property" || item.type === "delete_custom_property"));
  const hasStructuralCommands = computed(() => commands.value.some(item => ["update_subset_title", "delete_sheet", "delete_subset", "insert_sheet", "insert_subset"].includes(String(item.type))));

  // 命令类型 → 语义键（I18N-07/I18N-12）：稳定命令类型不进用户文案；草稿动作只持久化
  // label_key，显示文本由 DraftActionsPanel 在渲染期经语言包翻译（语言不写入草稿）
  const COMMAND_LABEL_KEYS: Record<ChangeCommand["type"], string> = {update_sheet_set: "shell.commands.updateSheetSet", update_subset_title: "shell.commands.updateSubsetTitle", update_sheet_properties: "shell.commands.updateSheetProperties", delete_sheet: "shell.commands.deleteSheet", insert_sheet: "shell.commands.insertSheet", insert_subset: "shell.commands.insertSubset", add_custom_property: "shell.commands.addCustomProperty", delete_custom_property: "shell.commands.deleteCustomProperty", delete_subset: "shell.commands.deleteSubset"};

  function resetDraftState() {
    draftActions.value = [];
    draftCursor.value = 0;
    draftVersion.value = 0;
    draftStale.value = false;
    draftStaleReasons.value = [];
    draftCorrupted.value = false;
    draftSaveFailed.value = false;
    draftSaving.value = false;
    draftRecovered.value = null;
  }

  function rebuildDraftProjection() {
    commands.value = draftStale.value ? [] : projectCommands(draftActions.value, draftCursor.value);
    if (baseWorkspace.value) {
      // 元数据/属性定义沿用本地只读副本投影；结构动作由内部投影请求以服务端权威派生结果显示
      workspace.value = projectWorkspace(baseWorkspace.value, draftStale.value ? [] : draftActions.value, draftStale.value ? 0 : draftCursor.value);
      void deps.refreshSheetProjection();
    }
    invalidatePreview();
  }

  function scheduleDraftSave() {
    const workspaceId = workspace.value?.id;
    if (!workspaceId || draftStale.value) return;
    draftSaving.value = true;
    draftSaveQueue = draftSaveQueue.then(async () => {
      const current = workspace.value;
      if (!current || current.id !== workspaceId || draftStale.value) return;
      try {
        const saved: DraftEnvelope = await request(`/api/workspaces/${workspaceId}/draft`, {method: "PUT", body: JSON.stringify({schema_version: 1, base_revision_id: current.revision_id, repair_status: current.dst_validation?.status ?? "VALID", expected_version: draftVersion.value, cursor: draftCursor.value, actions: cloneJson(draftActions.value)})});
        if (workspace.value?.id === workspaceId && saved.draft) {
          draftVersion.value = saved.draft.version;
          draftSaveFailed.value = false;
          lastDraftError.value = null;
        }
      } catch (e) {
        if (workspace.value?.id === workspaceId && e instanceof ApiError && e.code === "DRAFT_CONFLICT") {
          draftSaveFailed.value = true;
          lastDraftError.value = e;
          draftStale.value = true;
          draftStaleReasons.value = ["DRAFT_VERSION_CONFLICT"];
          commands.value = [];
          invalidatePreview();
          error.value = t("shell.errors.draftConflictOverwrite");
        } else throw e;
      }
    }).catch(e => {
      if (workspace.value?.id === workspaceId) {
        draftSaveFailed.value = true;
        lastDraftError.value = e instanceof ApiError ? e : null;
      }
    }).finally(() => {
      draftSaving.value = false;
    });
  }

  function clearCommands() {
    draftActions.value = [];
    draftCursor.value = 0;
    rebuildDraftProjection();
    scheduleDraftSave();
    error.value = "";
  }

  function clearDraftRestart() {
    draftRecovered.value = null;
    clearCommands();
    void discardDraft();
  }

  function undoDraft() {
    if (draftStale.value || draftCursor.value === 0) return;
    draftCursor.value -= 1;
    rebuildDraftProjection();
    scheduleDraftSave();
  }

  function redoDraft() {
    if (draftStale.value || draftCursor.value >= draftActions.value.length) return;
    draftCursor.value += 1;
    rebuildDraftProjection();
    scheduleDraftSave();
  }

  function removeDraftAction(index: number) {
    if (draftStale.value) return;
    const removedActive = index < draftCursor.value;
    draftActions.value.splice(index, 1);
    if (removedActive) draftCursor.value -= 1;
    draftCursor.value = Math.min(draftCursor.value, draftActions.value.length);
    rebuildDraftProjection();
    scheduleDraftSave();
  }

  async function discardDraft() {
    const current = workspace.value;
    if (!current) return;
    await draftSaveQueue;
    if (workspace.value?.id !== current.id) return;
    try {
      await request(`/api/workspaces/${current.id}/draft`, {method: "DELETE", body: JSON.stringify({expected_version: draftVersion.value})});
    } catch (e) {
      if (e instanceof ApiError && e.code === "DRAFT_CONFLICT") {
        draftStale.value = true;
        draftStaleReasons.value = ["DRAFT_VERSION_CONFLICT"];
        error.value = t("shell.errors.draftConflictDelete");
        return;
      }
      throw e;
    }
    resetDraftState();
    rebuildDraftProjection();
  }

  async function reloadAfterDraftConflict() {
    const current = workspace.value;
    if (!current || !draftStaleReasons.value.includes("DRAFT_VERSION_CONFLICT")) return;
    // 丢弃本地冲突动作并重新读取较新草稿：不改变服务器数据，属低风险动作（danger:false、无需勾选）
    const ok = await deps.confirmAction({title: t("shell.workspace.reloadConflictTitle"), message: t("shell.workspace.reloadConflictMessage"), confirmText: t("shell.workspace.reloadConflictConfirm"), danger: false});
    if (!ok) return;
    draftSaveFailed.value = false;
    // 此路径已带明确「放弃并重新加载」确认：直接刷新，不再叠加三选一（保存对过期草稿也必然失败）
    await deps.reloadWorkspace(current.id);
  }

  function addCommand(command: ChangeCommand, category: "property" | "structural" | "metadata") {
    if (draftStale.value) {
      error.value = t("shell.errors.draftStaleAction");
      return false;
    }
    if (category === "property" && hasStructuralCommands.value) {
      error.value = t("shell.errors.mixedBatches");
      return false;
    }
    if (category === "structural" && hasPropertyDefinitionCommands.value) {
      error.value = t("shell.errors.mixedBatches");
      return false;
    }
    draftActions.value = draftActions.value.slice(0, draftCursor.value);
    draftActions.value.push({id: crypto.randomUUID(), kind: "command_batch", label_key: COMMAND_LABEL_KEYS[command.type], commands: [command]});
    draftCursor.value = draftActions.value.length;
    rebuildDraftProjection();
    scheduleDraftSave();
    error.value = "";
    return true;
  }

  function addCommandBatch(batch: ChangeCommand[], label: DraftActionLabel, category: "property" | "structural" | "metadata") {
    if (!batch.length) return false;
    if (draftStale.value) {
      error.value = t("shell.errors.draftStaleAction");
      return false;
    }
    if (category === "property" && hasStructuralCommands.value) {
      error.value = t("shell.errors.mixedBatches");
      return false;
    }
    if (category === "structural" && hasPropertyDefinitionCommands.value) {
      error.value = t("shell.errors.mixedBatches");
      return false;
    }
    draftActions.value = draftActions.value.slice(0, draftCursor.value);
    draftActions.value.push({id: crypto.randomUUID(), kind: "command_batch", label_key: label.key, ...(label.params ? {params: label.params} : {}), commands: batch});
    draftCursor.value = draftActions.value.length;
    rebuildDraftProjection();
    scheduleDraftSave();
    error.value = "";
    return true;
  }

  // —— 未提交输入保护（SPEC-DM-009 §6.2）：范围/筛选改变若隐藏当前编辑对象，
  // 先还原快照再三选一（加入草稿后继续/放弃输入/留在此处），保存/放弃后再应用 ——
  function runScopeChange(apply: () => void) {
    const ctx = deps.getEditor().context.value;
    if (!ctx || ctx.kind !== "sheet" || !deps.getEditor().hasUnsavedChanges.value) {
      apply();
      return;
    }
    const sheets = deps.getSheets();
    const snapshot = sheets.snapshotState();
    apply();
    const hidden = !sheets.filteredRows.value.some(row => row.sheet.id === ctx.objectId);
    if (!hidden) return;
    sheets.restoreState(snapshot);
    void deps.getEditor().guard(apply);
  }

  function guardedFilter<T>(apply: (value: T) => void) {
    return (value: T) => runScopeChange(() => apply(value));
  }

  // —— 全局输入保护：图纸页与属性页两个活动输入域依次过闸 ——
  // 固定先处理当前主标签的活动编辑器，再处理另一域；任一步「留在此处」即终止 next。
  // 页面只挂载一个共享 UnsavedInputDialog（见模板），两个 guard 顺序开合同一实例，不叠加模态。
  // 核心输入域过闸后再征询图纸目录页未保存模板草稿的三选一守卫（目录页未挂载时为空操作）；
  // 「留在此处」同样终止 next。目录页守卫是既有纯函数，直接组合调用。
  async function guardAllInputs(next: () => void | Promise<void>) {
    const core = async () => {
      if (deps.getActive() === "properties") await deps.getProperties().guard(() => deps.getEditor().guard(next));
      else await deps.getEditor().guard(() => deps.getProperties().guard(next));
    };
    await guardSheetCatalogPage(core);
  }

  function resolveSharedGuard(choice: GuardChoice) {
    deps.getEditor().resolveGuard(choice);
    deps.getProperties().resolveGuard(choice);
  }

  const sharedGuardState = computed(() => (deps.getProperties().guardState.value.open ? deps.getProperties().guardState.value : deps.getEditor().guardState.value));

  /** 读当前保存队列：`draftSaveQueue` 每次入队都会重赋，故必须取值而非解构（解构是快照）。 */
  const pendingDraftSave = () => draftSaveQueue;

  return {
    commands, draftActions, draftCursor, draftVersion, draftStale, draftStaleReasons, draftCorrupted,
    draftSaveFailed, lastDraftError, draftSaving, draftRecovered,
    hasPropertyDefinitionCommands, hasStructuralCommands,
    resetDraftState, rebuildDraftProjection, scheduleDraftSave, clearCommands, clearDraftRestart,
    undoDraft, redoDraft, removeDraftAction, discardDraft, reloadAfterDraftConflict,
    addCommand, addCommandBatch,
    runScopeChange, guardedFilter, guardAllInputs, resolveSharedGuard, sharedGuardState, pendingDraftSave,
  };
}
