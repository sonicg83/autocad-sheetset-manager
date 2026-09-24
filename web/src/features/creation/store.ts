// 创建域状态控制器（PLAN-DM-036 Task 8，Task 9 接入权威预览会话）。
//
// 职责：持有四阶段向导的输入状态（固定标准身份、项目路径、图纸集属性、按组输入、当前
// 阶段与选中组），把输入变更映射为草稿保存请求，并在输入变化时使旧预览失效。属性求值、
// 编号、DWG 命名、目标目录状态等最终判定一律不在前端重复——预览与执行以后端响应为准
// （预览会话的状态迁移在 `previewSession.ts`）。
//
// 结构：状态是 `reactive` 对象上的普通值（组件直接读 `store.step` / `store.groups`）；
// 派生值（`targetPath`/`groupIssues`/`selectedGroups`）与动作是显式类型的函数，经
// `Object.assign` 组装到同一对象上。派生值用函数而不是 `computed` 字段，是为了让
// reactive 对象不在自身的初始化表达式里引用自己（否则 TS 无法推断其类型）；函数内部
// 读取的仍是同一份 reactive 状态，模板里调用时依赖照常被追踪。
//
// 「可恢复创建草稿」：草稿身份由后端给出，本模块只持有 `draftId`；把草稿 ID 记在哪里
// （桌面壳 localStorage 等）由调用方决定，store 不直接读写浏览器存储。
import {reactive} from "vue";
import type {Job} from "../../api/contracts";
import {createCreationPreviewSession} from "./previewSession";
import type {
  CreationApi,
  CreationBatchChange,
  CreationDraftState,
  CreationGroupIssueCode,
  CreationGroupPatch,
  CreationGroupState,
  CreationIdentity,
  CreationImportDiagnostic,
  CreationStandardCandidate,
  CreationStandardInputs,
  CreationState,
  CreationStep,
  CreationStoreOptions,
} from "./types";
import {
  creationBatchPatch,
  creationCopiedGroup,
  creationDefaultGroup,
  creationGroupIssues,
  creationHasInput,
  creationLatestGroup,
  creationNextGroupId,
  creationNextOrder,
  creationPathParts,
  creationStandardInputs,
  creationTargetPath,
  creationWithPropertyDefaults,
} from "./inputModel";

export interface CreationStore extends CreationState {
  /** 完整最终项目路径（上一级目录 + 目录名）。 */
  targetPath(): string;
  /** 某个图纸组的即时提示（图名/张数/模板/图幅）。 */
  groupIssues(groupId: string): CreationGroupIssueCode[];
  selectedGroups(): CreationGroupState[];
  loadCandidates(): Promise<void>;
  /** 建立或复用固定标准的草稿；`replace` 为真时先放弃现有草稿（切换标准）。 */
  chooseStandard(
    candidate: CreationStandardCandidate,
    options?: {replace?: boolean},
  ): Promise<boolean>;
  /** 恢复已存在的草稿（重新进入向导）；失败时返回 false 并保留稳定错误消息。 */
  resumeDraft(draftId: string): Promise<boolean>;
  /** 放弃当前草稿并回到第一阶段。 */
  restart(): Promise<boolean>;
  goToStep(step: CreationStep): Promise<void>;
  /** 保存草稿；内容与上次成功保存一致时跳过请求（返回 true）。 */
  save(force?: boolean): Promise<boolean>;
  setSheetsetValue(propertyId: string, value: string): void;
  setParentPath(value: string): void;
  setFolderName(value: string): void;
  /** 新建图纸组：复制创建序最大的组；无组时取标准默认值。 */
  addGroup(): CreationGroupState;
  updateGroup(groupId: string, patch: CreationGroupPatch): void;
  setGroupSheetValue(groupId: string, propertyId: string, value: string): void;
  removeGroup(groupId: string): void;
  moveGroup(from: number, to: number): void;
  toggleGroup(groupId: string, selected?: boolean): void;
  selectAllGroups(): void;
  clearGroupSelection(): void;
  batchUpdate(groupIds: string[], fieldId: string, change: CreationBatchChange): void;
  invalidatePreview(): void;
  /** 编号设置等向导外变化使旧摘要失效（与 `invalidatePreview` 同一实现，按原因区分入口）。 */
  invalidateForSettingsChange(): void;
  /** 保存草稿（按需）后请求权威预览，写入摘要与可执行标志。 */
  preview(): Promise<boolean>;
  /** 按当前有效摘要执行创建；无有效预览时不发请求并返回 null。 */
  execute(): Promise<Job | null>;
  group(groupId: string): CreationGroupState;
  templateUrl(): string;
  importWorkbook(file: File): Promise<boolean>;
  clearImportState(): void;
  /** 导入前的全量覆盖提醒依据（草稿是否已有用户输入）。 */
  hasInput(): boolean;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

function cloneGroup(group: CreationGroupState): CreationGroupState {
  return {...group, sheet_values: {...group.sheet_values}};
}

export function createCreationStore(
  api: CreationApi,
  options: CreationStoreOptions = {},
): CreationStore {
  const seed = api.seed ?? null;
  const defaultFolderName = options.defaultFolderName ?? "";
  // 上次成功保存的内容签名：内容未变时不重复发写请求（也避免无谓地递增草稿修订）
  let savedSignature = "";

  const state = reactive<CreationState>({
    step: seed === null ? "standard" : seed.draft.step,
    candidates: [],
    candidatesPending: false,
    candidatesError: "",
    standard: seed === null ? null : seed.standard,
    standardPending: false,
    draftId: seed === null ? "" : seed.draft.id,
    revision: seed === null ? 0 : seed.draft.revision,
    parentPath: seed === null ? "" : creationPathParts(seed.draft.target_path).parentPath,
    folderName: seed === null
      ? defaultFolderName
      : creationPathParts(seed.draft.target_path).folderName || defaultFolderName,
    sheetsetValues: seed === null ? {} : {...seed.draft.sheetset_values},
    groups: seed === null ? [] : seed.draft.groups.map(cloneGroup),
    selectedGroupIds: [],
    previewState: null,
    previewDigest: null,
    canExecute: false,
    previewPending: false,
    executePending: false,
    pending: false,
    importPending: false,
    importDiagnostics: [],
    importMessage: "",
    error: "",
  });

  /** 保存内容签名：包含阶段、最终路径、图纸集属性与按序图纸组。 */
  function saveSignature(): string {
    return JSON.stringify({
      step: state.step,
      targetPath: targetPath(),
      sheetsetValues: state.sheetsetValues,
      groups: state.groups,
    });
  }

  function targetPath(): string {
    return creationTargetPath(state.parentPath, state.folderName);
  }

  function sameIdentity(left: CreationIdentity | null, right: CreationIdentity): boolean {
    return left !== null && left.standardId === right.standardId && left.version === right.version;
  }

  // 权威预览会话：状态迁移在 `previewSession.ts`，本模块只组合并在输入变化时失效
  const previewSession = createCreationPreviewSession({
    api,
    state,
    draftId: () => state.draftId,
    save,
    onError: message => { state.error = message; },
  });

  /** 使旧预览失效：唯一实现在预览会话里（本模块保留同一拼写供各输入动作调用）。 */
  const invalidatePreview = previewSession.invalidate;

  /**
   * 采用草稿输入：路径拆成两段、属性按标准补齐（显式空串保留、缺键才用默认值）、
   * 组按数组顺序复制。`inputs` 给出时同时更新固定标准输入模型（切换/恢复标准），
   * 省略时沿用当前标准（导入只替换输入，不改变标准身份）。
   */
  function adoptDraft(draft: CreationDraftState, inputs?: CreationStandardInputs): void {
    if (inputs !== undefined) state.standard = inputs;
    const standard = state.standard;
    const parts = creationPathParts(draft.target_path);
    state.draftId = draft.id;
    state.revision = draft.revision;
    state.step = draft.step;
    state.parentPath = parts.parentPath;
    state.folderName = parts.folderName === "" ? defaultFolderName : parts.folderName;
    state.sheetsetValues = creationWithPropertyDefaults(draft.sheetset_values, standard, "sheetset");
    state.groups = draft.groups.map(group => ({
      ...cloneGroup(group),
      sheet_values: creationWithPropertyDefaults(group.sheet_values, standard, "sheet"),
    }));
    state.selectedGroupIds = [];
    invalidatePreview();
    savedSignature = saveSignature();
  }

  /** 回到「尚未选择标准」的干净输入（重新开始）；草稿身份与预览一并清空。 */
  function resetInputs(): void {
    state.step = "standard";
    state.draftId = "";
    state.revision = 0;
    state.standard = null;
    state.parentPath = "";
    state.folderName = defaultFolderName;
    state.sheetsetValues = {};
    state.groups = [];
    state.selectedGroupIds = [];
    state.error = "";
    clearImportState();
    invalidatePreview();
    savedSignature = "";
  }

  async function discardDraft(): Promise<boolean> {
    if (state.draftId === "") return true;
    state.pending = true;
    state.error = "";
    try {
      await api.deleteDraft(state.draftId);
      return true;
    } catch (error) {
      state.error = errorMessage(error);
      return false;
    } finally {
      state.pending = false;
    }
  }

  /** 读取固定标准的可输入字段模型；失败时保留稳定错误消息并返回 null。 */
  async function loadStandardInputs(
    identity: CreationIdentity,
    name: string,
    assetOptions: CreationStandardInputs["asset_options"],
  ): Promise<CreationStandardInputs | null> {
    state.standardPending = true;
    try {
      const document = await api.fetchStandardDocument(identity);
      return creationStandardInputs(identity, name, document, assetOptions);
    } catch (error) {
      state.error = errorMessage(error);
      return null;
    } finally {
      state.standardPending = false;
    }
  }

  function clearImportState(): void {
    state.importDiagnostics = [];
    state.importMessage = "";
  }

  async function loadCandidates(): Promise<void> {
    state.candidatesPending = true;
    state.candidatesError = "";
    try {
      state.candidates = await api.listStandards();
    } catch (error) {
      state.candidatesError = errorMessage(error);
    } finally {
      state.candidatesPending = false;
    }
  }

  async function chooseStandard(
    candidate: CreationStandardCandidate,
    chooseOptions: {replace?: boolean} = {},
  ): Promise<boolean> {
    const identity: CreationIdentity = {
      standardId: candidate.standard_id,
      version: candidate.version,
    };
    if (state.draftId !== "" && chooseOptions.replace !== true) {
      // 同一固定标准：复用现有草稿，不重建输入（切换标准必须显式要求 replace）
      if (sameIdentity(state.standard?.identity ?? null, identity)) {
        if (state.step === "standard") state.step = "project";
        return true;
      }
      return false;
    }
    if (chooseOptions.replace === true && state.draftId !== "") {
      // 切换标准：先放弃旧草稿，旧标准的字段、模板选择与预览随之清除（不静默迁移）
      if (!(await discardDraft())) return false;
    }
    state.pending = true;
    state.error = "";
    try {
      const inputs = await loadStandardInputs(identity, candidate.name, candidate.asset_options);
      if (inputs === null) return false;
      const draft = await api.createDraft(identity);
      adoptDraft(draft, inputs);
      // 初建草稿的后端阶段就是「项目信息」；标准入口因此直接落到第二阶段
      state.step = draft.step;
      return true;
    } catch (error) {
      state.error = errorMessage(error);
      return false;
    } finally {
      state.pending = false;
    }
  }

  async function resumeDraft(draftId: string): Promise<boolean> {
    state.pending = true;
    state.error = "";
    try {
      const draft = await api.fetchDraft(draftId);
      const candidate = state.candidates.find(
        item => item.standard_id === draft.standard_id && item.version === draft.standard_version,
      );
      const inputs = await loadStandardInputs(
        {standardId: draft.standard_id, version: draft.standard_version},
        candidate?.name ?? "",
        candidate?.asset_options ?? [],
      );
      if (inputs === null) return false;
      adoptDraft(draft, inputs);
      return true;
    } catch (error) {
      state.error = errorMessage(error);
      return false;
    } finally {
      state.pending = false;
    }
  }

  async function restart(): Promise<boolean> {
    if (!(await discardDraft())) return false;
    resetInputs();
    return true;
  }

  // 保存串行化：预览与阶段切换可能几乎同时触发保存，并发请求会拿同一个 expected_revision
  // 撞上后端乐观修订门禁（409）；串行执行保证后一次读到前一次回灌的修订。
  let saveQueue: Promise<boolean> = Promise.resolve(true);

  function save(force = false): Promise<boolean> {
    saveQueue = saveQueue.then(() => runSave(force), () => runSave(force));
    return saveQueue;
  }

  async function runSave(force = false): Promise<boolean> {
    if (state.draftId === "") return true;
    const signature = saveSignature();
    if (!force && signature === savedSignature) return true;
    state.pending = true;
    state.error = "";
    try {
      const saved = await api.saveDraft({
        draftId: state.draftId,
        expectedRevision: state.revision,
        step: state.step,
        targetPath: targetPath(),
        sheetsetValues: {...state.sheetsetValues},
        groups: state.groups.map(cloneGroup),
      });
      // 保存只回灌修订：提交内容就是界面当前输入，无需覆盖界面状态
      state.revision = saved.revision;
      savedSignature = signature;
      invalidatePreview();
      return true;
    } catch (error) {
      state.error = errorMessage(error);
      return false;
    } finally {
      state.pending = false;
    }
  }

  function group(groupId: string): CreationGroupState {
    const found = state.groups.find(item => item.group_id === groupId);
    if (found === undefined) throw new Error(`CREATION_GROUP_NOT_FOUND: ${groupId}`);
    return found;
  }

  function addGroup(): CreationGroupState {
    const createdOrder = creationNextOrder(state.groups);
    const groupId = creationNextGroupId(state.groups, createdOrder);
    const latest = creationLatestGroup(state.groups);
    const added =
      latest === null
        ? creationDefaultGroup(state.standard, groupId, createdOrder)
        : creationCopiedGroup(latest, groupId, createdOrder);
    state.groups = [...state.groups, added];
    invalidatePreview();
    return added;
  }

  function updateGroup(groupId: string, patch: CreationGroupPatch): void {
    state.groups = state.groups.map(item =>
      item.group_id === groupId ? {...item, ...patch} : item,
    );
    invalidatePreview();
  }

  function batchUpdate(groupIds: string[], fieldId: string, change: CreationBatchChange): void {
    const targets = new Set(groupIds);
    if (targets.size === 0) return;
    state.groups = state.groups.map(item => {
      if (!targets.has(item.group_id)) return item;
      const patch = creationBatchPatch(item, state.standard, fieldId, change);
      return patch === null ? item : {...item, ...patch};
    });
    invalidatePreview();
  }

  async function importWorkbook(file: File): Promise<boolean> {
    if (state.draftId === "") return false;
    state.importPending = true;
    clearImportState();
    try {
      const outcome = await api.importWorkbook({
        draftId: state.draftId,
        file,
        expectedRevision: state.revision,
      });
      if (!outcome.ok) {
        // 失败零变更：草稿输入、阶段与预览状态一律保持原样
        state.importMessage = outcome.message;
        state.importDiagnostics = outcome.diagnostics;
        return false;
      }
      // 成功一次性替换输入（保留固定标准身份）并使预览失效
      adoptDraft(outcome.draft);
      return true;
    } catch (error) {
      state.importMessage = errorMessage(error);
      return false;
    } finally {
      state.importPending = false;
    }
  }

  return Object.assign(state, {
    targetPath,
    groupIssues: (groupId: string) => creationGroupIssues(state.groups, state.standard)[groupId] ?? [],
    selectedGroups: () => state.groups.filter(item => state.selectedGroupIds.includes(item.group_id)),
    loadCandidates,
    chooseStandard,
    resumeDraft,
    restart,
    goToStep: async (step: CreationStep): Promise<void> => {
      state.step = step;
      await save();
    },
    save,
    setSheetsetValue: (propertyId: string, value: string): void => {
      // 用户主动清空后不得回填标准默认值：这里只写入显式值，不查默认值
      state.sheetsetValues = {...state.sheetsetValues, [propertyId]: value};
      invalidatePreview();
    },
    setParentPath: (value: string): void => {
      state.parentPath = value;
      invalidatePreview();
    },
    setFolderName: (value: string): void => {
      state.folderName = value;
      invalidatePreview();
    },
    addGroup,
    updateGroup,
    setGroupSheetValue: (groupId: string, propertyId: string, value: string): void => {
      updateGroup(groupId, {
        sheet_values: {...group(groupId).sheet_values, [propertyId]: value},
      });
    },
    removeGroup: (groupId: string): void => {
      state.groups = state.groups.filter(item => item.group_id !== groupId);
      state.selectedGroupIds = state.selectedGroupIds.filter(id => id !== groupId);
      invalidatePreview();
    },
    moveGroup: (from: number, to: number): void => {
      const groups = [...state.groups];
      if (from < 0 || from >= groups.length || to < 0 || to >= groups.length || from === to) return;
      const [moved] = groups.splice(from, 1);
      if (moved === undefined) return;
      groups.splice(to, 0, moved);
      // 重排只改数组顺序（最终组序），不改变 `created_order`
      state.groups = groups;
      invalidatePreview();
    },
    toggleGroup: (groupId: string, selected?: boolean): void => {
      const has = state.selectedGroupIds.includes(groupId);
      const next = selected ?? !has;
      if (next && !has) state.selectedGroupIds = [...state.selectedGroupIds, groupId];
      else if (!next && has) {
        state.selectedGroupIds = state.selectedGroupIds.filter(id => id !== groupId);
      }
    },
    selectAllGroups: (): void => {
      state.selectedGroupIds = state.groups.map(item => item.group_id);
    },
    clearGroupSelection: (): void => {
      state.selectedGroupIds = [];
    },
    batchUpdate,
    invalidatePreview,
    invalidateForSettingsChange: previewSession.invalidateForSettingsChange,
    preview: previewSession.preview,
    execute: previewSession.execute,
    group,
    templateUrl: (): string => (state.draftId === "" ? "" : api.templateUrl(state.draftId)),
    importWorkbook,
    clearImportState,
    hasInput: (): boolean =>
      creationHasInput(
        {target_path: targetPath(), sheetset_values: state.sheetsetValues, groups: state.groups},
        state.standard,
      ),
  }) as CreationStore;
}
