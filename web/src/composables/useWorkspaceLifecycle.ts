import {computed, ref, watch, type ComputedRef, type Ref} from "vue";
import type {useI18n} from "vue-i18n";
import {ApiError, localizedError, request} from "../api/client";
import {clearWorkspaceContext, getShellBridge, openWorkspaceFolder as bridgeOpenWorkspaceFolder, shellReady} from "../api/shell";
import type {DraftEnvelope, Workspace} from "../api/contracts";
import type {useDraftGuards} from "./useDraftGuards";
import type {ConfirmOptions} from "./useConfirm";

/**
 * 工作区生命周期域（Task 11 第 11d 轮，Step 3）：打开 / 关闭 / 恢复（刷新）/ 清空编辑态，
 * 以及壳桥接（选择 DST、拖拽接收、打开所在文件夹）这一组**跨域编排**。
 *
 * 只返回根装配需要的 state/actions；`doOpenByPath`/`doCloseWorkspace`/`beginWorkspaceLoad`/
 * `resetEditingState`/`loadDraft` 等内部步骤不外露（`doRefreshWorkspace` 例外，见下）。
 * **保留顺序**：`pendingDraftSave()` 等待 → 保存失败则中止 → `invalidateJobMonitor(true)` →
 * 代次递增（`beginWorkspaceLoad`）→ 重置编辑态/草稿态 → 快照 `baseWorkspace` → `loadDraft`。
 * 这个顺序是语义的一部分（草稿未落盘不得开新工作区；代次是「迟到响应不得复活旧工作区」的唯一闸门）。
 *
 * **依赖求值时机**：本模块在 setup 期创建于 `useDraftGuards` **之后**（组合其返回值）、
 * 但必须**早于** `useJobMonitor`/`useCsvImport`/`useRepair`/`useRestore`（它们把
 * `refreshWorkspace`/`workspaceLoadGeneration` 当**直接实参**，setup 期即求值）。
 * 因此下述 `resetSheetsWorkspace`/`reloadExtensions`/`invalidateJobMonitor`/`editor` 等
 * 在 setup 期尚不存在的目标，一律以**回调**传入，只在动作被调用时才解引用（与 11b/11c 同法）。
 */
export interface WorkspaceLifecycleOptions {
  // —— 根装配持有的单一事实来源：ref 经引用注入，写 `.value` 即写同一份状态 ——
  workspace: Ref<Workspace|null>;
  baseWorkspace: Ref<Workspace|null>;
  error: Ref<string>;
  isWorkspaceLoading: Ref<boolean>;
  isRestoreExecuting: Ref<boolean>;
  // —— 11c 的草稿域：本域**组合**它（清空草稿态、等待保存队列、过未提交输入闸门、丢弃草稿），不复制草稿语义 ——
  draft: ReturnType<typeof useDraftGuards>;
  // —— 根助手（函数声明可提升，直接引用即可）——
  cloneJson: <T>(value: T) => T;
  invalidatePreview: () => void;
  t: ReturnType<typeof useI18n>["t"];
  confirmAction: (options: ConfirmOptions) => Promise<boolean>;
  // —— 单点解引用：以下目标在 setup 期晚于本模块创建，故以回调传入 ——
  invalidateLayoutReads: () => void;
  resetSheetsWorkspace: () => void;
  reloadExtensions: () => void;
  clearExtensions: () => void;
  loadRevisions: () => void;
  invalidateRevisionState: () => void;
  invalidateJobMonitor: (force: boolean) => void;
  resetOverlay: () => void;
  resetEditor: () => void;
  invalidateCsvPreview: (clearFile: boolean) => void;
  isSettingsOpen: () => boolean;
  getActive: () => string;
}

export interface WorkspaceLifecycle {
  /** 跨域共享的加载代次：打开/关闭/刷新推进它，修复/恢复/任务域据此丢弃迟到响应。 */
  workspaceLoadGeneration: Ref<number>;
  /** 壳桥是否就绪（晚于首帧注入，故须可重算，否则永远显示无壳降级界面）。 */
  hasShell: ComputedRef<boolean>;
  openByPath: (path: string) => Promise<void>;
  /** 未过闸门的刷新（供草稿域 `reloadWorkspace` 在冲突后重载）：调用方负责先过闸 —— 见 `refreshWorkspace`。 */
  doRefreshWorkspace: (expectedWorkspaceId?: string) => Promise<void>;
  /** 按工作区 ID 打开（创建成功后的工作区接管）；已打开其它工作区时不静默切换。 */
  openWorkspaceById: (workspaceId: string) => Promise<void>;
  closeWorkspace: () => Promise<void>;
  refreshWorkspace: (expectedWorkspaceId?: string) => Promise<void>;
  openFolder: () => Promise<void>;
  /** 欢迎页「选择 DST 文件」入口：无工作区时经壳对话框选文件并打开（无壳时由根走降级路径）。 */
  selectAndOpenDst: () => Promise<void>;
}

export function useWorkspaceLifecycle(deps: WorkspaceLifecycleOptions): WorkspaceLifecycle {
  const {workspace, baseWorkspace, error, isWorkspaceLoading, isRestoreExecuting, draft, t, confirmAction} = deps;

  // 工作区加载代次为跨域共享的单一 ref：本域（打开/关闭/刷新）与修复/恢复域组合式函数共用
  const workspaceLoadGeneration = ref(0);

  function resetEditingState() {
    draft.commands.value = [];
    deps.invalidatePreview();
    deps.invalidateCsvPreview(true);
    error.value = "";
  }

  function beginWorkspaceLoad() {
    workspaceLoadGeneration.value += 1;
    isWorkspaceLoading.value = true;
    resetEditingState();
    draft.resetDraftState();
    deps.invalidateRevisionState();
    deps.resetOverlay();
    return workspaceLoadGeneration.value;
  }

  async function openByPath(path: string) {
    // 重新打开/切换工作区前先过全局输入保护（无未提交输入时直接通过）
    await draft.guardAllInputs(() => doOpenByPath(path));
  }

  /**
   * 按工作区 ID 打开（PLAN-DM-036 Task 9 创建成功路径）。
   *
   * 创建任务成功后只知道新工作区的 ID（没有可用的 DST 打开上下文），而 `doRefreshWorkspace`
   * 要求已经打开同一工作区、`doOpenByPath` 要的是路径，两者都不适用；因此本入口与 `doOpenByPath`
   * 同源，但允许从「尚无工作区」开始，且**不静默替换**已打开的其它工作区。
   */
  async function openWorkspaceById(workspaceId: string) {
    if (workspaceId === "" || isWorkspaceLoading.value) return;
    const current = workspace.value;
    if (current !== null) {
      // 已打开同一工作区：按普通刷新语义重建；已打开其它工作区：交给用户先关闭，不隐式切换
      if (current.id === workspaceId) await doRefreshWorkspace(workspaceId);
      return;
    }
    await draft.guardAllInputs(() => doOpenWorkspaceById(workspaceId));
  }

  async function doOpenWorkspaceById(workspaceId: string) {
    if (workspace.value !== null || isWorkspaceLoading.value) return;
    isWorkspaceLoading.value = true;
    await draft.pendingDraftSave();
    if (draft.draftSaveFailed.value) {
      isWorkspaceLoading.value = false;
      return;
    }
    deps.invalidateJobMonitor(true);
    const generation = beginWorkspaceLoad();
    try {
      const loaded: Workspace = await request(`/api/workspaces/${encodeURIComponent(workspaceId)}`);
      if (generation !== workspaceLoadGeneration.value) return;
      resetEditingState();
      baseWorkspace.value = deps.cloneJson(loaded);
      workspace.value = deps.cloneJson(loaded);
      deps.resetSheetsWorkspace();
      await loadDraft(loaded);
      isWorkspaceLoading.value = false;
      void deps.reloadExtensions();
    } catch (e) {
      if (generation === workspaceLoadGeneration.value) {
        isWorkspaceLoading.value = false;
        error.value = String(e);
      }
    }
  }

  async function doOpenByPath(path: string) {
    if (isRestoreExecuting.value) {
      error.value = t("shell.errors.restoreRunning");
      return;
    }
    isWorkspaceLoading.value = true;
    await draft.pendingDraftSave();
    if (draft.draftSaveFailed.value) {
      isWorkspaceLoading.value = false;
      return;
    }
    deps.invalidateJobMonitor(true);
    const generation = beginWorkspaceLoad();
    try {
      const loaded: Workspace = await request("/api/workspaces/open", {method: "POST", body: JSON.stringify({dst_path: path})});
      if (generation !== workspaceLoadGeneration.value) return;
      resetEditingState();
      baseWorkspace.value = deps.cloneJson(loaded);
      workspace.value = deps.cloneJson(loaded);
      deps.resetSheetsWorkspace();
      await loadDraft(loaded);
      isWorkspaceLoading.value = false;
      void deps.reloadExtensions();
      // 打开成功后若停留在修订历史标签，重载修订列表（beginWorkspaceLoad 已 invalidateRevisionState 清空，避免虚假空态）
      if (deps.getActive() === "revisions") void deps.loadRevisions();
    } catch (e) {
      if (generation === workspaceLoadGeneration.value) {
        isWorkspaceLoading.value = false;
        error.value = String(e);
      }
    }
  }

  // 桥晚于首帧注入（pywebviewready）：依赖 shellReady 才能在就绪时重算，否则永远显示无壳降级界面
  const hasShell = computed(() => shellReady.value && getShellBridge() !== null);

  // 打开图纸集所在文件夹（PLAN-DM-015 任务 2）：目标路径由服务端可信上下文解析，前端只传
  // workspace_id；异步返回后再比较一次，旧工作区结果不进入新工作区
  async function openFolder() {
    const current = workspace.value;
    if (!current || !hasShell.value) return;
    const result = await bridgeOpenWorkspaceFolder(current.id);
    if (workspace.value?.id !== current.id) return;
    if (!result) {
      error.value = t("shell.errors.shellFolderUnsupported");
      return;
    }
    if (!result.ok) error.value = result.code === "SHELL_WORKSPACE_UNAVAILABLE" ? t("shell.errors.workspaceSwitched") : localizedError(result.message_key, result.params, result.message);
  }

  const DST_EXT = /\.dst$/i;
  const DROP_CALLBACK_ID = "__dstManagerAcceptDst";

  async function acceptDstPath(path: string) {
    // 设置对话框打开时丢弃壳侧 document 级 drop 回调（SC-14 双保险：对话框已 stop 冒泡）
    if (deps.isSettingsOpen()) return;
    if (workspace.value) {
      error.value = t("shell.errors.closeFirst");
      return;
    }
    if (!DST_EXT.test(path)) {
      error.value = t("shell.errors.dstOnly");
      return;
    }
    await openByPath(path);
  }

  async function selectAndOpenDst() {
    const bridge = getShellBridge();
    if (!bridge) {
      error.value = t("shell.errors.shellNotReady");
      return;
    }
    const path = await bridge.select_file("dst", t("common.shell.fileKinds.dst"));
    if (!path) return;
    await acceptDstPath(path);
  }

  function registerDropBridge() {
    const bridge = getShellBridge();
    // 老/部分桥面可能只暴露 select_file：on_files_dropped 缺失时静默跳过拖拽接桥
    if (!bridge || typeof bridge.on_files_dropped !== "function") return;
    // 拖拽热区接桥：壳侧 document drop 监听（pywebview 原生 pywebviewFullPath）→ 本全局回调
    (window as unknown as Record<string, unknown>)[DROP_CALLBACK_ID] = (path: unknown) => {
      void acceptDstPath(String(path));
    };
    void bridge.on_files_dropped(DROP_CALLBACK_ID).catch(() => {});
  }

  // 桥就绪时机不定（早于/晚于首帧注入都可能）：immediate 覆盖已就绪，watch 覆盖 pywebviewready 晚到
  watch(shellReady, (ready) => {
    if (ready) registerDropBridge();
  }, {immediate: true});

  // 关闭工作区：先接全局输入保护（三选一），再纳入现有关闭确认，不静默丢弃
  async function closeWorkspace() {
    await draft.guardAllInputs(async () => {
      await doCloseWorkspace();
    });
  }

  async function doCloseWorkspace() {
    const pending = draft.draftActions.value.length > 0 || draft.draftSaveFailed.value || draft.draftStale.value;
    if (pending) {
      // 关闭工作区属于不可逆破坏类操作：需要显式勾选后才可确认
      const ok = await confirmAction({title: t("shell.workspace.closeConfirmTitle"), message: t("shell.workspace.closeConfirmMessage"), confirmText: t("shell.workspace.closeConfirmConfirm"), danger: true, requireCheckbox: true, reversibility: "irreversible"});
      if (!ok) return;
      await draft.discardDraft();
    }
    const closedId = workspace.value?.id;
    // 推进加载代次：关闭后迟到的打开/刷新/修订响应全部按代次失效，防止复活工作区
    workspaceLoadGeneration.value += 1;
    isWorkspaceLoading.value = false;
    draft.resetDraftState();
    resetEditingState();
    deps.resetEditor();
    baseWorkspace.value = null;
    workspace.value = null;
    deps.invalidateJobMonitor(true);
    deps.invalidateRevisionState();
    deps.resetOverlay();
    deps.clearExtensions();
    // 关闭成功清空服务端可信上下文（best-effort：旧 ID 的迟到清除请求由服务端按上下文匹配拒绝，不影响新工作区）
    if (closedId) void clearWorkspaceContext(closedId);
    // 重置图纸页工作区状态；操作表单/编辑缓冲状态已由 editor.reset() 清空，旧模板路径不残留
    deps.resetSheetsWorkspace();
    deps.invalidateLayoutReads();
  }

  // 刷新工作区同样先过全局输入保护（基准即将重建，未提交输入须先三选一）
  async function refreshWorkspace(expectedWorkspaceId?: string) {
    await draft.guardAllInputs(() => doRefreshWorkspace(expectedWorkspaceId));
  }

  async function doRefreshWorkspace(expectedWorkspaceId?: string) {
    const current = workspace.value;
    if (!current || isWorkspaceLoading.value) return;
    const workspaceId = expectedWorkspaceId ?? current.id;
    if (current.id !== workspaceId) return;
    isWorkspaceLoading.value = true;
    await draft.pendingDraftSave();
    if (draft.draftSaveFailed.value) {
      isWorkspaceLoading.value = false;
      return;
    }
    if (workspace.value?.id !== workspaceId) return;
    const generation = beginWorkspaceLoad();
    try {
      const loaded: Workspace = await request(`/api/workspaces/${workspaceId}`);
      if (generation !== workspaceLoadGeneration.value) return;
      resetEditingState();
      baseWorkspace.value = deps.cloneJson(loaded);
      workspace.value = deps.cloneJson(loaded);
      await loadDraft(loaded);
      isWorkspaceLoading.value = false;
      void deps.reloadExtensions();
      // 刷新成功后若停留在修订历史标签，重载修订列表（发布/关闭等路径已 invalidateRevisionState 清空，避免虚假空态）
      if (deps.getActive() === "revisions") void deps.loadRevisions();
    } catch (e) {
      if (generation === workspaceLoadGeneration.value) {
        isWorkspaceLoading.value = false;
        error.value = String(e);
      }
    }
  }

  async function loadDraft(loaded: Workspace) {
    const result: DraftEnvelope = await request(`/api/workspaces/${loaded.id}/draft`);
    if (workspace.value?.id !== loaded.id) return;
    draft.draftCorrupted.value = result.corrupted;
    draft.draftStale.value = result.stale;
    draft.draftStaleReasons.value = result.stale_reasons;
    const loadedDraft = result.draft;
    if (!loadedDraft) {
      draft.resetDraftState();
      draft.draftCorrupted.value = result.corrupted;
      return;
    }
    draft.draftActions.value = loadedDraft.actions;
    draft.draftCursor.value = loadedDraft.cursor;
    draft.draftVersion.value = loadedDraft.version;
    draft.rebuildDraftProjection();
    draft.draftRecovered.value = loadedDraft.actions.length > 0 ? draft.commands.value.length : null;
    if (result.corrupted) error.value = t("shell.errors.draftCorrupted");
    else if (result.stale) error.value = t("shell.errors.draftStale");
  }

  return {
    workspaceLoadGeneration,
    hasShell,
    openByPath,
    openWorkspaceById,
    doRefreshWorkspace,
    closeWorkspace,
    refreshWorkspace,
    openFolder,
    selectAndOpenDst,
  };
}
