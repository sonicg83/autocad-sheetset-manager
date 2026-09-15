// Task 11 第 11e 轮（Step 5）：页面事件 → 命令/API 编排。
//
// 本模块只**编排**既有能力，**不复制任何规则**：
//  · 命令构造一律经 `createCommand`（`../api/contracts`），本模块不自行拼命令载荷；
//  · 草稿入栈/撤销/保存队列/保存失败与 `DRAFT_CONFLICT` 语义全在 `useDraftGuards`（以 `draft` 注入）；
//  · 工作区的打开/关闭/刷新在 `useWorkspaceLifecycle`（以**懒取值函数**注入，见下）；
//  · 图纸页/属性页的会话缓冲与表单上下文（`editor`/`properties`）只被调用，不被重新实现；
//  · 后端最终校验仍由服务端负责：本模块只按既有错误码与字段原样上抛（`SubmitResult`），
//    不在这里重做「是否允许空值」「是否可执行」之类的判定（`S-11` 等仍由服务端裁决）。
//
// ★ 求值顺序：本模块被根在 `useSheetEditor` **之前**调用（`submitCommands` 是它的**直接实参**，
// setup 期即求值），而 `editor`/`properties`/`sheets` 在根里更晚创建 ⇒ 这些一律以
// **懒取值函数**传入，只在动作真正被调用时才解引用（与 11c/11d 同法，避免 setup 期循环依赖）。
import {computed, ref, type Ref} from "vue";
import {ApiError, request} from "../api/client";
import {createCommand} from "../api/contracts";
import type {ChangeCommand, Job, Preview, PropertyDefinition, SemanticDiff, Sheet, Subset, Workspace} from "../api/contracts";
import {getShellBridge} from "../api/shell";
import type {DraftActionLabel, InsertSheetEditContext, InsertSubsetEditContext, SubmitResult} from "../features/sheets/types";
import {useHotkeys} from "./useHotkeys";
import type {useConfirm} from "./useConfirm";
import type {useCsvImport} from "./useCsvImport";
import type {useDraftGuards} from "./useDraftGuards";
import type {useJobMonitor} from "./useJobMonitor";
import type {usePropertiesWorkspace} from "./usePropertiesWorkspace";
import type {useRepair} from "./useRepair";
import type {useSheetEditor} from "./useSheetEditor";
import type {useShellNavigation} from "./useShellNavigation";
import type {useSheetsWorkspace} from "./useSheetsWorkspace";
import type {useToast} from "./useToast";
import type {useWorkspaceLifecycle} from "./useWorkspaceLifecycle";

// 预览上下文：一次预览所对应的基准（工作区 + 修订 + CAD 版本 + 命令快照 + 结果）。
// 正式写入必须逐项匹配该上下文，否则视为上下文失效（不写入）。
export type PreviewContext = {workspaceId: string; baseRevisionId: string; cadVersion: string; commands: ChangeCommand[]; result: Preview};

export type WorkspaceCommandsOptions = {
  // 根持有的共享状态（跨域：生命周期/草稿门禁也会失效预览，故预览态留在根，由本方读写）
  workspace: Ref<Workspace | null>;
  error: Ref<string>;
  preview: Ref<Preview | null>;
  previewContext: Ref<PreviewContext | null>;
  isPreviewing: Ref<boolean>;
  isWorkspaceLoading: Ref<boolean>;
  isRestoreExecuting: Ref<boolean>;
  cadVersion: Ref<string>;
  t: (key: string, params?: Record<string, unknown>) => string;
  confirmAction: ReturnType<typeof useConfirm>["confirmAction"];
  pushToast: ReturnType<typeof useToast>["pushToast"];
  cloneJson: <T>(value: T) => T;
  invalidatePreview: () => void;
  // 代次计数留在根（`previewGeneration`/`layoutReadGeneration` 是被重新赋值的 `let`，不能解构回同名）
  nextPreviewGeneration: () => number;
  currentPreviewGeneration: () => number;
  nextLayoutReadGeneration: () => number;
  currentLayoutReadGeneration: () => number;
  // 既有模块（`draft` 直接注入对象；其余以懒取值函数断开 setup 期求值顺序）
  draft: ReturnType<typeof useDraftGuards>;
  nav: Pick<ReturnType<typeof useShellNavigation>, "openOverlay">;
  getLifecycle: () => ReturnType<typeof useWorkspaceLifecycle>;
  getEditor: () => ReturnType<typeof useSheetEditor>;
  getProperties: () => ReturnType<typeof usePropertiesWorkspace>;
  getSheets: () => ReturnType<typeof useSheetsWorkspace>;
  getJobMonitor: () => Pick<ReturnType<typeof useJobMonitor>, "job" | "terminal" | "watchJob" | "invalidateJobMonitor" | "isCurrentJobGeneration">;
  getRepair: () => Pick<ReturnType<typeof useRepair>, "dstValidation" | "repairWritesDisabled">;
  getCsvImport: () => Pick<ReturnType<typeof useCsvImport>, "importCsv" | "invalidateCsvPreview" | "csvText" | "csvPreview">;
  setJob: (job: Job) => void;
  hasShell: Ref<boolean>;
  selectAndOpenDst: () => void | Promise<void>;
  refreshSheetProjection: () => Promise<SubmitResult>;
};

export function useWorkspaceCommands(deps: WorkspaceCommandsOptions) {
  const {
    workspace, error, preview, previewContext, isPreviewing, isWorkspaceLoading, isRestoreExecuting, cadVersion,
    t, confirmAction, pushToast, cloneJson, invalidatePreview,
    nextPreviewGeneration, currentPreviewGeneration, nextLayoutReadGeneration, currentLayoutReadGeneration,
    draft, nav, getLifecycle, getEditor, getProperties, getSheets, getJobMonitor, getRepair, getCsvImport,
    setJob, hasShell, selectAndOpenDst, refreshSheetProjection,
  } = deps;

  const bulkPropertyName = ref("");
  const bulkPropertyValue = ref("");
  const bulkMode = ref<"set" | "clear">("set"); // 批量模式：设置值 / 清空值（SPEC-DM-009 §6.1 显式区分）

  const saveStatusText = computed(() => draft.draftSaveFailed.value ? t("shell.dock.saveStatusFailed") : draft.draftSaving.value ? t("shell.dock.saveStatusSaving") : draft.draftStale.value ? t("shell.dock.saveStatusStale") : t("shell.dock.saveStatusSaved"));

  // 预览派生视图（只读展示投影，供根装配 TaskOverlay props；判定权在服务端与 `dock` 门禁）
  const previewGroups = computed(() => preview.value?.execution_intent?.groups ?? []);
  const derivedSubsets = computed(() => preview.value?.execution_intent?.derived_document?.subsets ?? []);
  const sourceBaselines = computed(() => preview.value?.execution_intent?.source_baselines ?? []);
  const subsetOperations = computed(() => preview.value?.execution_intent?.subset_operations ?? []);
  const cardinalityFrontier = computed(() => preview.value?.execution_intent?.cardinality_frontier ?? null);
  const cadValidationDeferred = computed(() => preview.value?.execution_intent?.cad_validation_deferred === true);
  const semanticDiff = computed<SemanticDiff>(() => preview.value?.semantic_diff ?? {sheet_set: [], structure: {before: [], after: []}, properties: [], dwgs: []});
  const executionEstimate = computed(() => preview.value?.execution_intent?.estimate ?? null);

  // —— 提交命令（SubmitCommands）：加入草稿动作并等待持久化与投影成功，不以入队即宣称保存 ——
  // label 为 DraftActionLabel（稳定 label_key + 命名 params，PLAN-DM-021 Task 8/I18N-12）：语言不写入草稿
  async function submitCommands(commands: ChangeCommand[], label: DraftActionLabel, category: "metadata" | "structural" | "property"): Promise<SubmitResult> {
    if (draft.draftStale.value) return {ok: false, message: t("shell.errors.draftStaleAction")};
    // 结构变更与属性定义变更必须分批；属性值编辑（metadata）可与结构并存（混合批次显示由命令簿叠加合成）
    if (category === "structural" && draft.hasPropertyDefinitionCommands.value) return {ok: false, message: t("shell.errors.mixedBatches")};
    if (category === "property" && draft.hasStructuralCommands.value) return {ok: false, message: t("shell.errors.mixedBatches")};
    // 草稿保存失败重试：仅当撤销/重做光标位于栈顶且与最后一条草稿动作等价时，
    // 视为保存失败重试而不重复加入同一命令批次；撤销后重提交相同命令必须重新入栈（I-1 修复）
    const last = draft.draftActions.value[draft.draftActions.value.length - 1];
    const sameBatch = last?.kind === "command_batch" && draft.draftCursor.value === draft.draftActions.value.length && JSON.stringify(last.commands) === JSON.stringify(commands);
    if (!sameBatch) {
      if (!draft.addCommandBatch(commands, label, category)) return {ok: false, message: error.value || t("shell.errors.addDraftFailed")};
    }
    // 保存失败重试去重：不重复入栈，但用户确实执行了一次加入草稿动作，旧预览同样失效
    else {draft.scheduleDraftSave(); invalidatePreview()}
    await draft.pendingDraftSave();
    if (draft.draftSaveFailed.value) return {ok: false, message: draft.lastDraftError.value?.message ?? t("shell.errors.draftSaveFailed"), fields: draft.lastDraftError.value?.fields};
    const projection = await refreshSheetProjection();
    if (!projection.ok) return projection;
    return {ok: true};
  }

  // —— 删除与批量编辑（页面事件 → 草稿命令）——
  async function queueDelete(sheet: Sheet) {
    // 编辑未提交时先处理缓冲（三选一），再按删除确认流程；删除命令不得夹带未确认的属性变更
    await getEditor().guard(async () => {await doQueueDelete(sheet)});
  }
  async function doQueueDelete(sheet: Sheet) {
    // 单张图纸删除为低风险动作：danger:false、无需勾选；确认文案明确「加入删除草稿」，不是立即删除文件（SPEC-DM-009 §6.3）
    const ok = await confirmAction({title: t("shell.flows.deleteSheet.title"), message: t("shell.flows.deleteSheet.message", {number: sheet.number}), confirmText: t("shell.flows.deleteSheet.confirm"), danger: false});
    if (!ok) return;
    if (draft.addCommand(createCommand.deleteSheet(sheet.id), "structural")) {
      // 删除成功进入草稿：目标已从投影移除，结束对应编辑上下文，避免预览/写入被「未提交输入」误报
      getEditor().discardIfTargeting(sheet.id);
      pushToast({type: "ok", title: t("shell.flows.deleteSheet.toastTitle"), body: t("shell.flows.deleteSheet.toastBody", {number: sheet.number})});
    }
  }
  // 删除整个子集：目标取编辑子集表单的编辑对象；编辑未提交时先三选一决策（保存后再删除），
  // 再走整子集删除确认流程。目标 ID 在 guard 前捕获——保存标题会关闭表单，删除仍作用于原目标。
  async function queueDeleteSubset() {
    const ctx = getEditor().context.value;
    const subsetId = ctx?.kind === "rename" ? ctx.objectId : "";
    await getEditor().guard(async () => {await doQueueDeleteSubset(subsetId)});
  }
  async function doQueueDeleteSubset(subsetId: string) {
    const subset = workspace.value?.sheet_set.subsets.find(item => item.id === subsetId);
    if (!subset) return;
    const drawing = subset.sheets[0]?.layout.resolved_path ?? subset.sheets[0]?.layout.file_name ?? t("shell.flows.deleteSubset.unknownDrawing");
    // 删除整个子集属不可逆破坏类操作：需要显式勾选后才可确认
    const ok = await confirmAction({title: t("shell.flows.deleteSubset.title"), message: t("shell.flows.deleteSubset.message", {name: subset.display_name, count: subset.sheets.length, drawing}), confirmText: t("shell.flows.deleteSubset.confirm"), danger: true, requireCheckbox: true, reversibility: "irreversible"});
    if (!ok) return;
    if (draft.addCommand(createCommand.deleteSubset(subset.id), "structural")) {
      // 删除成功进入草稿：目标已从投影移除，结束对应「编辑子集」上下文，
      // 否则残留的失效上下文会在下一次预览/写入时被「未提交输入」误报（2026-09-10 用户反馈 bug1）
      getEditor().discardIfTargeting(subset.id);
      pushToast({type: "ok", title: t("shell.flows.deleteSubset.toastTitle"), body: t("shell.flows.deleteSubset.toastBody", {name: subset.display_name, count: subset.sheets.length})});
    }
  }
  // 批量加入草稿：与单行编辑共用一个活动编辑上下文，有未提交输入先三选一
  function queueBulkSheetProperty() {
    void getEditor().guard(() => doQueueBulkSheetProperty());
  }
  // 批量编辑（SPEC-DM-009 §4.2/§6.1）：遍历完整勾选集合（含未加载行，不隐式缩为当前可见行）；
  // 逐张复制 custom_properties 后仅改指定名称，已删除对象按 ID 匹配不到自然不进入批量。
  // 设置值模式空输入不生成修改只提示；清空值须显式选择并确认受影响数量（是否允许空值仍由服务端校验 S-11）。
  async function doQueueBulkSheetProperty() {
    const name = bulkPropertyName.value;
    const selectedIds = getSheets().selectedIds;
    const allRows = getSheets().allRows;
    if (!name || !selectedIds.value.length) {error.value = t("shell.errors.selectSheetAndProperty"); return}
    const selected = new Set(selectedIds.value);
    const targets = allRows.value.filter(({sheet}) => selected.has(sheet.id));
    if (!targets.length) {error.value = t("shell.errors.bulkTargetsUnavailable"); return}
    if (bulkMode.value === "set") {
      if (!bulkPropertyValue.value.trim()) {error.value = t("shell.errors.bulkEmptyValue"); return}
      applyBulkBatch(targets, name, bulkPropertyValue.value, "set");
      return;
    }
    const affected = targets.filter(({sheet}) => (sheet.custom_properties[name] ?? "").trim() !== "");
    if (!affected.length) {error.value = t("shell.errors.bulkAllEmpty", {name}); return}
    const ok = await confirmAction({
      title: t("shell.flows.clearValues.title"),
      message: t("shell.flows.clearValues.message", {count: affected.length, name}),
      confirmText: t("shell.flows.clearValues.confirm"), danger: false,
    });
    if (!ok) return;
    applyBulkBatch(affected, name, "", "clear"); // 只改实际受影响图纸，与确认数量一致
  }
  function applyBulkBatch(targets: {sheet: Sheet; subset: Subset}[], name: string, value: string, mode: "set" | "clear") {
    const batch = targets.map(({sheet}) => createCommand.updateSheetProperties(sheet.id, {...sheet.custom_properties, [name]: value}));
    const subsetCount = new Set(targets.map(({subset}) => subset.id)).size;
    const labelKey = mode === "set" ? "shell.flows.bulk.setLabel" : "shell.flows.bulk.clearLabel";
    const toastKey = mode === "set" ? "shell.flows.bulk.setToast" : "shell.flows.bulk.clearToast";
    // 草稿动作持久化 label_key + 命名参数（属性名与数量是用户数据，I18N-12）；显示文本由动作栈渲染期翻译
    if (draft.addCommandBatch(batch, {key: labelKey, params: {name, count: batch.length}}, "metadata")) {
      // 连续批量编辑保留勾选集合与展开状态，只初始化本次属性输入。
      bulkMode.value = "set"; bulkPropertyName.value = ""; bulkPropertyValue.value = "";
      pushToast({type: "ok", title: t("shell.flows.bulk.toastTitle"), body: t(toastKey, {name, count: batch.length, subsets: subsetCount})});
    }
  }
  // 删除属性定义（PLAN-DM-016 任务 4 / SPEC-DM-010 §4.2）：沿用既有草稿与确认语义；
  // 目标 sheetset 值仍 dirty 时先运行属性输入 guard（三选一）再弹删除确认；空文本值不视为删除定义。
  // 确认文案只说明作用域与草稿语义，不虚构级联影响数量；受影响范围以预览时服务端结果为准。
  function queueDeleteProperty(definition: PropertyDefinition) {
    void getProperties().guard(() => doQueueDeleteProperty(definition));
  }
  async function doQueueDeleteProperty(definition: PropertyDefinition) {
    const scopeLabel = t(definition.type === "sheetset" ? "shell.flows.deleteProperty.scopeSheetset" : "shell.flows.deleteProperty.scopeSheet");
    const ok = await confirmAction({title: t("shell.flows.deleteProperty.title"), message: t("shell.flows.deleteProperty.message", {scope: scopeLabel, name: definition.name}), confirmText: t("shell.flows.deleteProperty.confirm"), danger: false});
    if (!ok) return;
    if (draft.addCommand(createCommand.deleteCustomProperty(definition.type, definition.name), "property")) {
      pushToast({type: "ok", title: t("shell.flows.deleteProperty.toastTitle"), body: t("shell.flows.deleteProperty.toastBody", {scope: scopeLabel, name: definition.name})});
    }
  }

  // —— CSV 导入（正式写入 ⇒ 同属命令编排）：先过全局未提交输入闸门，不静默混批 ——
  async function guardedImportCsv() {
    await draft.guardAllInputs(async () => {await getCsvImport().importCsv()});
  }
  async function closeCsvImport() {
    // 关闭导入区（2026-09-06 用户裁决）：有未导入数据（已选文件/预览）先确认，确认后清空文件与预览缓存；
    // 在途任务不取消（job 监控独立于导入区 UI）
    if (Boolean(getCsvImport().csvText.value) || Boolean(getCsvImport().csvPreview.value)) {
      const ok = await confirmAction({title: t("shell.flows.closeCsv.title"), message: t("shell.flows.closeCsv.message"), confirmText: t("shell.flows.closeCsv.confirm"), danger: false});
      if (!ok) return;
    }
    getCsvImport().invalidateCsvPreview(true);
    getProperties().csvOpen.value = false;
  }

  // —— 全局预览 / 确认写入（SPEC-DM-006 §9.1 统一门禁）——
  // 有未提交输入先三选一（图纸页与属性页依次过闸）；加入草稿使旧预览失效，不能静默忽略输入
  async function showPreview() {
    await draft.guardAllInputs(async () => {await doShowPreview()});
  }
  async function doShowPreview() {
    if (isWorkspaceLoading.value || draft.draftStale.value || !workspace.value || !draft.commands.value.length) return;
    const workspaceId = workspace.value.id;
    const baseRevisionId = workspace.value.revision_id;
    const cadVersionSnapshot = cadVersion.value;
    const commandSnapshot = cloneJson(draft.commands.value);
    const generation = nextPreviewGeneration();
    preview.value = null; previewContext.value = null; isPreviewing.value = true;
    try {
      const result: Preview = await request(`/api/workspaces/${workspaceId}/changes/preview`, {method: "POST", body: JSON.stringify({base_revision_id: baseRevisionId, commands: commandSnapshot, cad_version: cadVersionSnapshot})});
      if (generation !== currentPreviewGeneration() || workspace.value?.id !== workspaceId || workspace.value.revision_id !== baseRevisionId) return;
      preview.value = result; previewContext.value = {workspaceId, baseRevisionId, cadVersion: cadVersionSnapshot, commands: commandSnapshot, result}; error.value = ""; nav.openOverlay("prev");
    }
    catch (e) {if (generation === currentPreviewGeneration()) error.value = String(e)}
    finally {if (generation === currentPreviewGeneration()) isPreviewing.value = false}
  }
  // 执行正式写入（Task 5：模态上移到 write()，execute 不再自行开模态）
  async function execute() {
    const context = previewContext.value;
    if (!context || !context.result.executable) return;
    const current = workspace.value;
    if (isWorkspaceLoading.value || !current || current.id !== context.workspaceId || current.revision_id !== context.baseRevisionId) {invalidatePreview(); error.value = t("shell.errors.previewContextStale"); return}
    const monitor = getJobMonitor();
    const generation = monitor.invalidateJobMonitor(false);
    try {
      const result: Job = await request(`/api/workspaces/${context.workspaceId}/changes/execute`, {method: "POST", body: JSON.stringify({base_revision_id: context.baseRevisionId, commands: cloneJson(context.commands), cad_version: context.cadVersion, preview_digest: context.result.preview_digest})});
      if (!monitor.isCurrentJobGeneration(generation) || isWorkspaceLoading.value || workspace.value?.id !== context.workspaceId) return;
      setJob(result);
      if (result.status === "QUEUED" && result.id) monitor.watchJob(result.id, context.workspaceId);
      else if (result.status === "SUCCEEDED") {await draft.discardDraft(); await getLifecycle().refreshWorkspace(context.workspaceId)}
    }
    catch (e) {if (monitor.isCurrentJobGeneration(generation) && workspace.value?.id === context.workspaceId && !isWorkspaceLoading.value) error.value = String(e)}
  }
  // write 不能捕获旧 context 后在保存继续时执行：guard 保存后 previewContext 已失效，必须重新预览
  async function write() {
    await draft.guardAllInputs(async () => {await doWrite()});
  }
  async function doWrite() {
    const context = previewContext.value;
    if (!context || context.result.executable === false) return;
    if (await confirmAction({title: t("shell.flows.publish.title"), message: t("shell.flows.publish.message"), impactLines: context.result.affected_files, confirmText: t("shell.flows.publish.confirm"), danger: true, requireCheckbox: true, reversibility: "irreversible"})) await execute();
  }

  // —— ActionDock 门禁矩阵（SPEC-DM-006 §6.9 唯一出口）——
  const dock = computed(() => {
    const monitor = getJobMonitor();
    const job = monitor.job;
    const repair = getRepair();
    const taskRunning = isWorkspaceLoading.value || isRestoreExecuting.value || Boolean(job.value && !monitor.terminal(job.value.status));
    const base = {commandCount: draft.commands.value.length, actions: draft.draftActions.value, cursor: draft.draftCursor.value, stale: draft.draftStale.value, staleReasons: draft.draftStaleReasons.value, corrupted: draft.draftCorrupted.value, saveStatusText: saveStatusText.value, saveFailed: draft.draftSaveFailed.value, previewing: isPreviewing.value, writesDisabled: taskRunning || repair.repairWritesDisabled.value};
    if (taskRunning) return {...base, canPreview: false, canWrite: false, writeDisabledReason: t("shell.dock.reasonTaskRunning"), writeNeedsModal: false};
    if (job.value?.status === "NEEDS_REVIEW") return {...base, canPreview: false, canWrite: false, writeDisabledReason: t("shell.dock.reasonNeedsReview"), writeNeedsModal: false}; // 终态但需人工检查：dst_validation 是加载快照仅 SUCCEEDED 刷新，须独立锁定（§6.9 行）
    const status = repair.dstValidation.value?.status ?? "VALID";
    if (status !== "VALID") return {...base, canPreview: false, canWrite: false, writeDisabledReason: status === "REPAIRED" ? t("shell.dock.reasonRepaired") : status === "INVALID_UNRECOVERABLE" ? t("shell.dock.reasonUnrecoverable") : t("shell.dock.reasonNeedsRepair"), writeNeedsModal: false};
    if (!draft.commands.value.length) return {...base, canPreview: false, canWrite: false, writeDisabledReason: t("shell.dock.reasonNoChanges"), writeNeedsModal: false};
    const context = previewContext.value;
    if (!context) return {...base, canPreview: true, canWrite: false, writeDisabledReason: t("shell.dock.reasonPreviewFirst"), writeNeedsModal: false};
    if (context.workspaceId !== workspace.value?.id || context.baseRevisionId !== workspace.value?.revision_id) return {...base, canPreview: true, canWrite: false, writeDisabledReason: t("shell.dock.reasonPreviewStale"), writeNeedsModal: false};
    if (context.result.executable === false) return {...base, canPreview: true, canWrite: false, writeDisabledReason: t("shell.dock.reasonNotExecutable"), writeNeedsModal: false};
    return {...base, canPreview: true, canWrite: true, writeDisabledReason: "", writeNeedsModal: true};
  });

  // —— 布局模板读取（页面事件 → API 编排）：代次 + 对象身份双重校验，旧响应不回填 ——
  // PLAN-DM-021 Task 4：文件选择经桥的 file_kind + 本地化描述（描述取自语言包，仅作对话框显示）
  const DWG_DWT_EXT = /\.(dwg|dwt)$/i;
  function activeLayoutContext(kind: "insert-sheet"): InsertSheetEditContext | null;
  function activeLayoutContext(kind: "insert-subset"): InsertSubsetEditContext | null;
  function activeLayoutContext(kind: "insert-sheet" | "insert-subset"): InsertSheetEditContext | InsertSubsetEditContext | null {
    const ctx = getEditor().context.value;
    return ctx && ctx.kind === kind ? (ctx as InsertSheetEditContext | InsertSubsetEditContext) : null;
  }
  // 布局读取写入当前活动表单上下文：经代次 + 对象身份校验，取消/切表单/切版本后的旧响应不回填
  async function loadLayoutOptions(path: string, ctx: InsertSheetEditContext | InsertSubsetEditContext) {
    const gen = nextLayoutReadGeneration();
    ctx.layoutLoading = true; ctx.layoutOptions = [];
    // M4：cad_version 使用当前工作区的响应式版本，去除硬编码 "2020"
    try {
      const r = await request<{layouts: string[]; cached: boolean; file_hash: string}>(`/api/layout-names`, {method: "POST", body: JSON.stringify({file_path: path, cad_version: cadVersion.value})});
      if (gen !== currentLayoutReadGeneration() || getEditor().context.value !== ctx) return;
      ctx.layoutOptions = r.layouts;
    } catch (e) {
      if (gen !== currentLayoutReadGeneration() || getEditor().context.value !== ctx) return;
      ctx.layoutError = e instanceof ApiError ? e.message : t("shell.errors.layoutReadFailed"); ctx.layoutManual = true;
    } finally {
      if (gen === currentLayoutReadGeneration() && getEditor().context.value === ctx) ctx.layoutLoading = false;
    }
  }
  async function selectTemplateFile() {
    const bridge = getShellBridge();
    if (!bridge) {error.value = t("shell.errors.shellNotReadyShort"); return}
    const path = await bridge.select_file("template", t("common.shell.fileKinds.template"));
    if (!path) return;
    if (!DWG_DWT_EXT.test(path)) {error.value = t("shell.errors.templateOnly"); return}
    const ctx = activeLayoutContext("insert-sheet");
    if (!ctx) return;
    ctx.sourceFile = path; ctx.layoutError = ""; ctx.layoutManual = false; ctx.dirty = true;
    await loadLayoutOptions(path, ctx);
  }
  async function selectSubsetTemplateFile() {
    const bridge = getShellBridge();
    if (!bridge) {error.value = t("shell.errors.shellNotReadyShort"); return}
    const path = await bridge.select_file("template", t("common.shell.fileKinds.template"));
    if (!path) return;
    if (!DWG_DWT_EXT.test(path)) {error.value = t("shell.errors.templateOnly"); return}
    // 与新增图纸对齐：选文件后读取布局列表（缓存优先），下拉选择布局名称
    const ctx = activeLayoutContext("insert-subset");
    if (!ctx) return;
    ctx.templateFile = path; ctx.layoutError = ""; ctx.layoutManual = false; ctx.dirty = true;
    await loadLayoutOptions(path, ctx);
  }
  async function selectBaseTemplateFile() {
    const bridge = getShellBridge();
    if (!bridge) {error.value = t("shell.errors.shellNotReadyShort"); return}
    const path = await bridge.select_file("template", t("common.shell.fileKinds.template"));
    if (!path) return;
    if (!DWG_DWT_EXT.test(path)) {error.value = t("shell.errors.templateOnly"); return}
    const ctx = activeLayoutContext("insert-subset");
    if (!ctx) return;
    ctx.baseTemplateFile = path; ctx.dirty = true;
  }

  // 全局快捷键（SPEC-DM-006 §7.1）：Ctrl+S 只在 writeNeedsModal 时开模态，否则给非阻断提示（Task 7 toast 前用既有 error）
  useHotkeys({
    open: () => {if (workspace.value) {error.value = t("shell.errors.closeFirst"); return} if (hasShell.value) void selectAndOpenDst(); else (document.querySelector<HTMLInputElement>(".no-shell input"))?.focus()},
    preview: () => {if (dock.value.canPreview) void showPreview(); else error.value = dock.value.writeDisabledReason || t("shell.dock.reasonPreviewUnavailable")},
    write: () => {if (dock.value.writeNeedsModal) void write(); else error.value = dock.value.writeDisabledReason || t("shell.dock.reasonWriteUnavailable")},
    undo: () => draft.undoDraft(),
    redo: () => draft.redoDraft(),
  });

  return {
    bulkPropertyName, bulkPropertyValue, bulkMode,
    submitCommands,
    queueDelete, queueDeleteSubset, queueBulkSheetProperty, queueDeleteProperty,
    guardedImportCsv, closeCsvImport,
    showPreview, execute, write, dock,
    selectTemplateFile, selectSubsetTemplateFile, selectBaseTemplateFile,
    previewGroups, derivedSubsets, sourceBaselines, subsetOperations, cardinalityFrontier,
    cadValidationDeferred, semanticDiff, executionEstimate,
  };
}
