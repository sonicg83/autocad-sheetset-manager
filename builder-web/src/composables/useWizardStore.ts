// 向导应用状态（PLAN-DB-001 Task 5）：组合 useWizardGuard（门禁状态机）、
// useDraftAutosave（500 ms 防抖 + base_updated_at CAS）与 API client。
// 步骤完成条件由草稿内容 + 后端字段诊断共同推导（ARCH-DB-001 §7）：
// 后端诊断是权威，前端只做"必填非空 + 派生值可生成"的最小判断。
import {computed, inject, reactive, ref, type ComputedRef, type InjectionKey, type Ref} from "vue";
import {
  api,
  BuilderApiError,
  type AssetModel,
  type DiagnosticModel,
  type DraftFieldsModel,
  type ProjectModel,
  type ProjectStateResponse,
} from "../api/client";
import {createDraftAutosave, type AutosaveStatus} from "./useDraftAutosave";
import {
  createWizardGuard,
  restoreTargetStep,
  type StepCompletion,
} from "./useWizardGuard";

export function emptyDraft(): DraftFieldsModel {
  return {
    schema_version: 1,
    project: {name: "", stage: "", discipline: "", output_path: ""},
    numbering: {prefix: "", start: 0, width: 3},
    cad_version: "",
    sheets: [{title: ""}],
    template: {base_asset_id: "", layout_asset_id: "", source_layout: ""},
  };
}

/** SPEC-DB-001 §4 派生值：sheet_number = prefix + zero_pad(start, width)。 */
export function sheetNumber(prefix: string, start: number, width: number): string | null {
  if (!Number.isInteger(start) || start < 0 || start > 999_999) {
    return null;
  }
  if (!Number.isInteger(width) || width < 1 || width > 6) {
    return null;
  }
  if (String(start).length > width) {
    return null;
  }
  return `${prefix}${String(start).padStart(width, "0")}`;
}

/** 诊断 field 路径 → 所属步骤（1 起）。无法归类时不阻断任何步骤。 */
export function stepOfField(field: string): number {
  if (field.startsWith("project.")) {
    return 1;
  }
  if (field.startsWith("numbering.") || field === "cad_version") {
    return 2;
  }
  if (field.startsWith("sheets.")) {
    return 3;
  }
  if (field.startsWith("template.")) {
    return 4;
  }
  return 0;
}

export interface ToastMessage {
  kind: "info" | "error" | "success";
  message: string;
}

export interface WizardStore {
  ready: Ref<boolean>;
  project: Ref<ProjectModel | null>;
  draft: DraftFieldsModel;
  updatedAt: Ref<string | null>;
  diagnostics: Ref<DiagnosticModel[]>;
  step: Ref<number>;
  completion: ComputedRef<StepCompletion>;
  canEnter: (step: number) => boolean;
  /** 启动：读取当前项目并按恢复语义回到目标步骤。 */
  init: () => Promise<void>;
  visit: (step: number) => Promise<void>;
  advance: () => Promise<void>;
  goBack: () => Promise<void>;
  autosaveStatus: Ref<AutosaveStatus>;
  focusedField: Ref<string | null>;
  toast: Ref<ToastMessage | null>;
  showToast: (toast: ToastMessage) => void;
  dismissToast: () => void;
  /** 字段错误（后端诊断 + 保存失败），供错误摘要与行内错误渲染。 */
  fieldErrors: ComputedRef<{field: string; message: string; code: string}[]>;
  planConfirmed: Ref<boolean>;
  buildSucceeded: Ref<boolean>;
  /** Task 9 接线：确认后的计划 ID 与构建 ID 上收，供步骤 5/6 使用。 */
  planId: Ref<string | null>;
  buildId: Ref<string | null>;
  buildStatus: Ref<string | null>;
  /** 构建进行中：字段只读（§6 运行中冻结计划不可编辑）。 */
  buildRunning: ComputedRef<boolean>;
  createProject: (input: {projectRoot: string; name: string; stage: string; discipline: string; outputPath: string}) => Promise<void>;
  createProjectError: Ref<string | null>;
  intakeAsset: (role: "base" | "layout", sourcePath: string) => Promise<AssetModel | null>;
  refreshCadabilities: () => Promise<void>;
  cadabilities: Ref<{cad_version: string; available: boolean}[]>;
}

function cloneDraft(source: DraftFieldsModel): DraftFieldsModel {
  return JSON.parse(JSON.stringify(source)) as DraftFieldsModel;
}

export const WIZARD_STORE_KEY: InjectionKey<WizardStore> = Symbol("wizard-store");

/** 组件统一经此注入向导状态；缺失注入视为编程错误。 */
export function injectWizardStore(): WizardStore {
  const store = inject(WIZARD_STORE_KEY);
  if (!store) {
    throw new Error("WizardStore 未注入：组件必须在 WizardShell 提供的组件树内使用");
  }
  return store;
}

export function createWizardStore(): WizardStore {
  const ready = ref(false);
  const project = ref<ProjectModel | null>(null);
  const draft = reactive<DraftFieldsModel>(emptyDraft());
  const updatedAt = ref<string | null>(null);
  const diagnostics = ref<DiagnosticModel[]>([]);
  const focusedField = ref<string | null>(null);
  const toast = ref<ToastMessage | null>(null);
  const createProjectError = ref<string | null>(null);
  const cadabilities = ref<{cad_version: string; available: boolean}[]>([]);
  const planConfirmed = ref(false);
  const buildSucceeded = ref(false);
  const planId = ref<string | null>(null);
  const buildId = ref<string | null>(null);
  const buildStatus = ref<string | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  /** 恢复/创建时水合草稿不应触发自动保存。 */
  let hydrating = false;

  const autosave = createDraftAutosave({
    draft,
    save: async (patch) => {
      const result = await api.patchDraft({
        base_updated_at: patch.base_updated_at ?? "",
        draft: patch.draft,
        wizard_step: patch.wizard_step,
        focused_field: patch.focused_field,
      });
      return {updated_at: result.updated_at, diagnostics: result.diagnostics};
    },
    getBaseUpdatedAt: () => updatedAt.value,
    getWizardStep: () => guard.currentStep.value,
    getFocusedField: () => focusedField.value,
    onSaved: (result) => {
      updatedAt.value = result.updated_at;
      applyServerState({diagnostics: result.diagnostics as DiagnosticModel[] | undefined});
      // 保存失败造成的行内错误在成功保存后清除（诊断以服务端最新响应为准）
      saveError.value = null;
    },
    onConflict: () => {
      showToast({kind: "error", message: "草稿冲突：项目已在他处被修改，请刷新应用后重试"});
    },
    onError: (error) => {
      const apiError = error as BuilderApiError;
      saveError.value = {
        field: apiError.field ?? "",
        message: apiError.message,
        code: apiError.code,
      };
      showToast({kind: "error", message: `保存失败：${apiError.message}`});
    },
  });

  const saveError = ref<{field: string; message: string; code: string} | null>(null);

  const guard = createWizardGuard({completion: () => completion.value});

  const completion = computed<StepCompletion>(() => {
    const blockingByStep = new Set<number>();
    for (const diagnostic of diagnostics.value) {
      if (diagnostic.severity === "blocking" && diagnostic.field) {
        blockingByStep.add(stepOfField(diagnostic.field));
      }
    }
    if (saveError.value && saveError.value.field) {
      blockingByStep.add(stepOfField(saveError.value.field));
    }
    const projectFieldsOk =
      project.value !== null &&
      draft.project.name.trim().length > 0 &&
      draft.project.stage.trim().length > 0 &&
      draft.project.discipline.trim().length > 0 &&
      draft.project.output_path.trim().length > 0;
    const number = sheetNumber(draft.numbering.prefix, draft.numbering.start, draft.numbering.width);
    const rulesOk =
      (draft.cad_version === "2016" || draft.cad_version === "2020") &&
      number !== null &&
      draft.numbering.prefix.length <= 20 &&
      !/[<>:"/\\|?*]/.test(draft.numbering.prefix);
    const sheetsOk = draft.sheets.length === 1 && draft.sheets[0].title.trim().length > 0;
    const templatesOk =
      draft.template.base_asset_id.length > 0 &&
      draft.template.layout_asset_id.length > 0 &&
      draft.template.source_layout.trim().length > 0;
    return [
      projectFieldsOk && !blockingByStep.has(1),
      rulesOk && !blockingByStep.has(2),
      sheetsOk && !blockingByStep.has(3),
      templatesOk && !blockingByStep.has(4),
      planConfirmed.value,
      buildSucceeded.value,
    ];
  });

  // 草稿变更的调度由 useDraftAutosave 内部的 watch 负责；水合期间经 pause/resume 抑制。

  function applyServerState(state: Partial<ProjectStateResponse>): void {
    hydrating = true;
    try {
      if (state.diagnostics !== undefined) {
        diagnostics.value = state.diagnostics;
      }
      if (state.project) {
        project.value = state.project;
      }
    } finally {
      hydrating = false;
    }
  }

  function hydrateFromResponse(response: ProjectStateResponse): void {
    autosave.pause();
    hydrating = true;
    try {
      project.value = response.project;
      Object.assign(draft, cloneDraft(response.draft));
      updatedAt.value = response.updated_at;
      diagnostics.value = response.diagnostics;
      focusedField.value = response.focused_field;
      planConfirmed.value = false;
      buildSucceeded.value = false;
      planId.value = null;
      buildId.value = null;
      buildStatus.value = null;
    } finally {
      hydrating = false;
      autosave.resume();
    }
  }

  async function init(): Promise<void> {
    try {
      const response = await api.getCurrentProject();
      hydrateFromResponse(response);
      // 恢复语义：不超过需确认的步骤 5，回退到最后一个可进入步骤（不自动越过确认）
      guard.visit(restoreTargetStep(response.wizard_step, completion.value));
    } catch {
      // 未初始化（404 等）：停留在第 1 步创建模式
    } finally {
      ready.value = true;
    }
  }

  async function persistStep(): Promise<void> {
    // 步骤切换必须持久化 wizard_step，即使草稿字段无待保存变更
    await autosave.flush(true);
  }

  async function visit(step: number): Promise<void> {
    if (!guard.visit(step)) {
      return;
    }
    await persistStep();
  }

  async function advance(): Promise<void> {
    if (!guard.advance()) {
      return;
    }
    await persistStep();
  }

  async function goBack(): Promise<void> {
    if (!guard.goBack()) {
      return;
    }
    await persistStep();
  }

  function showToast(message: ToastMessage): void {
    toast.value = message;
    if (toastTimer !== null) {
      clearTimeout(toastTimer);
    }
    toastTimer = setTimeout(() => {
      toast.value = null;
    }, 6000);
  }

  function dismissToast(): void {
    if (toastTimer !== null) {
      clearTimeout(toastTimer);
    }
    toast.value = null;
  }

  async function createProject(input: {
    projectRoot: string;
    name: string;
    stage: string;
    discipline: string;
    outputPath: string;
  }): Promise<void> {
    createProjectError.value = null;
    try {
      const response = await api.createProject({
        project_root: input.projectRoot.trim().length > 0 ? input.projectRoot.trim() : null,
        name: input.name.trim(),
        stage: input.stage.trim(),
        discipline: input.discipline.trim(),
        output_path: input.outputPath.trim(),
      });
      hydrateFromResponse(response);
      if (response.opened_existing) {
        // 幂等创建：目录已是 Builder 项目，本次为打开而非新建（壳重启恢复场景）。
        showToast({kind: "success", message: "该目录已是 Builder 项目，已为你打开既有项目"});
      }
    } catch (error) {
      const apiError = error as BuilderApiError;
      createProjectError.value = apiError.message;
      showToast({kind: "error", message: `创建项目失败：${apiError.message}`});
    }
  }

  async function intakeAsset(role: "base" | "layout", sourcePath: string): Promise<AssetModel | null> {
    try {
      const asset = await api.createAsset({role, source_path: sourcePath});
      if (role === "base") {
        draft.template.base_asset_id = asset.id;
      } else {
        draft.template.layout_asset_id = asset.id;
        draft.template.source_layout = "";
      }
      showToast({kind: "success", message: `已纳入${role === "base" ? "基础 DWG" : "布局模板"}：${asset.source_name}`});
      return asset;
    } catch (error) {
      const apiError = error as BuilderApiError;
      showToast({kind: "error", message: `资产纳入失败：${apiError.message}`});
      return null;
    }
  }

  async function refreshCadabilities(): Promise<void> {
    try {
      const response = await api.getCadabilities();
      cadabilities.value = response.capabilities.map((capability) => ({
        cad_version: capability.cad_version,
        available: capability.available,
      }));
    } catch {
      cadabilities.value = [];
    }
  }

  return {
    ready,
    project,
    draft,
    updatedAt,
    diagnostics,
    step: guard.currentStep,
    completion,
    canEnter: guard.canEnter,
    init,
    visit,
    advance,
    goBack,
    autosaveStatus: autosave.status,
    focusedField,
    toast,
    showToast,
    dismissToast,
    fieldErrors: computed(() => {
      const errors = new Map<string, {field: string; message: string; code: string}>();
      for (const diagnostic of diagnostics.value) {
        if (diagnostic.field && diagnostic.severity !== "info") {
          errors.set(diagnostic.field, {
            field: diagnostic.field,
            message: diagnostic.message,
            code: diagnostic.code,
          });
        }
      }
      if (saveError.value && saveError.value.field) {
        errors.set(saveError.value.field, saveError.value);
      }
      return [...errors.values()];
    }),
    planConfirmed,
    buildSucceeded,
    planId,
    buildId,
    buildStatus,
    buildRunning: computed(
      () =>
        buildStatus.value !== null &&
        !["SUCCEEDED", "FAILED", "CANCELLED"].includes(buildStatus.value),
    ),
    createProject,
    createProjectError,
    intakeAsset,
    refreshCadabilities,
    cadabilities,
  };
}
