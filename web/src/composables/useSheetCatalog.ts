// 图纸目录页面唯一状态所有者（PLAN-DM-020 Task 11 / SPEC-DM-012 §3/§7/§8/§10/§11）。
// PLAN-DM-025 Task 8：全局设置（模板集合/草稿/过滤词/光标/修订冲突）已抽到
// useSheetCatalogSettings.ts；本模块只保留工作区绑定部分——字段目录、防抖预览、导出与
// 三选一导航守卫，并把设置接口组合给页面组件。业务页与设置中心 custom 面板各持一份设置
// 实例（同一 API 与状态模型、不共享任何可变状态），并行编辑靠 revision 冲突收敛。
//
// 导航保护（SPEC §3.2）：guardNavigation(next) 是切换模板/切换页签/离开/关闭的统一
// 三选一闸门。页面状态属于视图实例，视图只在工作区页签激活时挂载，因此通过模块级守卫
// 登记（useTheme 同款模块级单例先例）让宿主 App.vue 在切页签、停用扩展与关闭/刷新
// 工作区时征询本页守卫；视图卸载时自动注销。
import {computed, onScopeDispose, reactive, ref, watch} from "vue";
import type {Ref} from "vue";
import {useI18n} from "vue-i18n";
import {ApiError, localizedError, request} from "../api/client";
import {openArtifactFolder, requestExtensionSave, shellReady} from "../api/shell";
import type {ShellResult, ShellSaveGrant} from "../api/shell";
import type {Workspace} from "../api/contracts";
import {useExtensionSettings} from "./useExtensionSettings";
import {
  CATALOG_EXTENSION_ID, CATALOG_SETTINGS_SCHEMA_VERSION, catalogColumnSignature, catalogTemplateSnapshot, fieldReference,
  useSheetCatalogSettings,
} from "./useSheetCatalogSettings";
import type {
  CatalogDiagnostic, CatalogField, CatalogPreviewData, GuardChoice, NavigationResult,
  SheetCatalogNavigationGuard, SheetCatalogValidationFeedback,
} from "./useSheetCatalogSettings";

export {CATALOG_EXTENSION_ID, CATALOG_SETTINGS_SCHEMA_VERSION, EXCLUDED_TITLE_KEYWORDS_FIELD, SHEET_CATALOG_MAX_COLUMNS, fieldReference} from "./useSheetCatalogSettings";
export type {CatalogColumn, CatalogField, CatalogPreviewData, CatalogTemplate, PreviewStatus, SheetCatalogValidationFeedback} from "./useSheetCatalogSettings";

const CATALOG_ACTION_ID = "export-xlsx";
const PREVIEW_DEBOUNCE_MS = 300;

type PreviewResponse = {
  normalized_template: {template_id: string | null; name: string; schema_version: number; columns: {column_id: string | null; header: string; expression: string}[]};
  field_catalog: {sheetset: {scope: "sheetset" | "sheet"; canonical_name: string; builtin: boolean}[]; sheet: {scope: "sheetset" | "sheet"; canonical_name: string; builtin: boolean}[]};
  errors: {code: string; message_key: string; params: Record<string, string | number>; column_id?: string | null; source_position?: number | null}[];
  warnings: {code: string; message_key: string; params: Record<string, string | number>; column_id?: string | null; source_position?: number | null}[];
  rows: string[][];
  // total_rows 是过滤后的实际输出行数；filtered_rows 是被过滤掉的图纸数（SPEC-DM-012 §8.1）
  total_rows: number;
  filtered_rows: number;
  // 本次预览绑定的扩展设置修订：执行时必须原样重复提交（ARCH-DM-006 §11）
  settings_revision: number;
  preview_digest: string;
  executable: boolean;
};

type PreferenceResponse = {schema_version: number; revision: number; value: {template_id?: unknown}};
type ExecuteResponse = {artifact_id: string; file_name: string; output_path: string; warnings?: {code: string; message_key: string; params: Record<string, string | number>}[]};

// 模块级守卫登记：目录页挂载期间注册，卸载注销（见文件头说明）。
// isDirty 探针供宿主在同步路径上先判断是否需要闸门：无未保存草稿时键盘/点击
// 切换页签保持既有同步语义，不引入微任务延迟。
let activeNavigationGuard: SheetCatalogNavigationGuard | null = null;
let navigationDirtyProbe: (() => boolean) | null = null;
export function registerSheetCatalogNavigationGuard(guard: SheetCatalogNavigationGuard, isDirty: () => boolean): () => void {
  activeNavigationGuard = guard;
  navigationDirtyProbe = isDirty;
  return () => {
    if (activeNavigationGuard === guard) activeNavigationGuard = null;
    if (navigationDirtyProbe === isDirty) navigationDirtyProbe = null;
  };
}
// 目录页当前是否有未保存草稿需要闸门（未挂载 = false）
export function sheetCatalogNavigationNeeded(): boolean {
  return navigationDirtyProbe?.() ?? false;
}
// 宿主统一入口：目录页未挂载（无草稿可言）时直接放行
export async function guardSheetCatalogPage(next: () => void | Promise<void>): Promise<NavigationResult> {
  const guard = activeNavigationGuard;
  if (guard === null) {
    await next();
    return "continue";
  }
  return guard(next);
}

export function useSheetCatalog(workspace: Ref<Workspace | null>) {
  const {t} = useI18n();
  const settings = useExtensionSettings(CATALOG_EXTENSION_ID);
  // 业务页实例：修订冲突与只读由协议层承担（与设置中心面板同一状态模型）
  const owner = useSheetCatalogSettings(settings, {
    guard: guardNavigation,
    onSelected: id => { if (id !== null) void recordPreference(id); },
  });
  const {templates, selectedId, draft, dirty, draftName, canSaveInPlace, loading} = owner;

  // ---- 字段目录 / 预览 ----
  const fieldCatalog = ref<{sheetset: CatalogField[]; sheet: CatalogField[]}>({sheetset: [], sheet: []});
  const preview = ref<CatalogPreviewData | null>(null);
  const previewStatus = ref<"idle" | "pending" | "ready" | "failed">("idle");
  const previewError = ref("");
  // 本次预览对应的草稿列快照：导出只允许"预览与草稿一致"时进行（SPEC §3.1 第 7 步）
  const previewedColumns = ref("");
  // 本次预览绑定的扩展设置修订：导出时原样重复提交，后端据此拒绝"预览后设置已变"
  // （EXTENSION_SETTINGS_CHANGED/409）；不得用最新修订代替，否则会把设置漂移误报成
  // 通用预览漂移（REPREVIEW_REQUIRED）。
  // 取值只接受契约要求的数字：响应违约（字段缺失/类型不符）时不发布预览，而是给出可见
  // 诊断（R15）——静默返回会让导出按钮看似可用却点不动。
  const previewedSettingsRevision = ref<number | null>(null);
  const draftSignature = computed(() => catalogColumnSignature(draft.value.columns));
  let previewGeneration = 0;
  let previewTimer: ReturnType<typeof setTimeout> | null = null;

  // 校验反馈（兼容性徽标与摘要的唯一来源）：业务页传真实预览状态，不伪造
  const feedback: SheetCatalogValidationFeedback = {preview, previewStatus, previewError};

  // ---- 保存授权 / 导出状态（SPEC §10） ----
  const exportState = reactive({
    phase: "idle" as "idle" | "exporting" | "success" | "failed",
    outputPath: "",
    fileName: "",
    // 成功导出的 Artifact 标识：「打开所在文件夹」桥方法只传标识，路径权威在宿主
    artifactId: "",
    errorText: "",
    errorCode: "",
  });
  const actionError = ref("");
  // 初始装配失败（设置/偏好读取）与壳动作错误分开呈现：前者替换页面正文，
  // 后者只在操作区内联提示，不影响页面其余部分
  const loadError = ref("");
  // 桌面壳可用性（桥晚于首帧注入：依赖 shellReady 响应式重算）；前端不传任何路径
  const hasShell = computed(() => shellReady.value && detectShell());

  // ---- 三选一守卫状态（视图渲染目录域的未保存对话框） ----
  const guardState = ref({open: false, summary: "", canSave: false});
  let guardResolver: ((choice: GuardChoice) => void) | null = null;

  // ---- 初始装配：设置 + 偏好（上次选中的已保存模板） ----
  async function initialize() {
    const current = workspace.value;
    if (!current) return;
    await settings.load();
    if (settings.snapshot.value === null) {
      // 协议层只有 loadFailed 布尔（不发错误文本）：页面层给出可见正文并停用编辑
      loadError.value = t("extensions.sheetCatalog.settingsLoadFailed");
      return;
    }
    owner.refresh();
    try {
      const preference = await request<PreferenceResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/workspaces/${current.id}/preferences`);
      const preferred = typeof preference.value?.template_id === "string" ? preference.value.template_id : null;
      // 偏好 best-effort：读取失败退回内置默认模板，不阻断页面
      owner.applySelection(preferred !== null && templates.value.some(template => template.templateId === preferred) ? preferred : null);
    } catch {
      owner.applySelection(null);
    }
    void schedulePreview(0);
  }

  async function recordPreference(id: string | null) {
    const current = workspace.value;
    if (!current || id === null) return; // 内置模板与未命名草稿不进入工作区偏好
    try {
      await request(`/api/extensions/${CATALOG_EXTENSION_ID}/workspaces/${current.id}/preferences`, {
        method: "PUT",
        body: JSON.stringify({schema_version: CATALOG_SETTINGS_SCHEMA_VERSION, value: {template_id: id}}),
      });
    } catch {
      // 偏好 best-effort：失败可诊断但不阻断模板选择
    }
  }

  // ---- 防抖预览（SPEC §7.2：页面本地未保存草稿即时校验） ----
  function schedulePreview(delay = PREVIEW_DEBOUNCE_MS) {
    if (previewTimer !== null) clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      previewTimer = null;
      void requestPreview();
    }, delay);
  }
  async function requestPreview() {
    const current = workspace.value;
    if (!current) return;
    const generation = ++previewGeneration;
    const snapshotColumns = draftSignature.value;
    previewStatus.value = "pending";
    try {
      const result = await request<PreviewResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/actions/${CATALOG_ACTION_ID}/preview`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: current.id,
          base_revision_id: current.revision_id,
          template: catalogTemplateSnapshot({...draft.value, name: draftName.value}),
        }),
      });
      if (generation !== previewGeneration || workspace.value?.id !== current.id) return;
      fieldCatalog.value = {
        sheetset: result.field_catalog.sheetset.map(field => ({scope: field.scope, canonicalName: field.canonical_name, builtin: field.builtin})),
        sheet: result.field_catalog.sheet.map(field => ({scope: field.scope, canonicalName: field.canonical_name, builtin: field.builtin})),
      };
      // 响应违约（R15）：settings_revision 非数字时不得发布预览，否则导出按钮看似可用
      // 却点不动（点击静默返回）。给出可见失败正文 + 可用「刷新预览」重试出口。
      if (typeof result.settings_revision !== "number") {
        preview.value = null;
        previewedColumns.value = "";
        previewedSettingsRevision.value = null;
        previewStatus.value = "failed";
        previewError.value = t("extensions.sheetCatalog.previewContractInvalid");
        return;
      }
      preview.value = {
        errors: result.errors.map(normalizeDiagnostic),
        warnings: result.warnings.map(normalizeDiagnostic),
        rows: result.rows,
        totalRows: result.total_rows,
        filteredRows: result.filtered_rows,
        previewDigest: result.preview_digest,
        executable: result.executable,
      };
      previewError.value = "";
      previewedColumns.value = snapshotColumns;
      previewedSettingsRevision.value = result.settings_revision;
      previewStatus.value = "ready";
    } catch (error) {
      if (generation !== previewGeneration) return;
      previewStatus.value = "failed";
      previewError.value = error instanceof Error ? error.message : String(error);
    }
  }
  function normalizeDiagnostic(diagnostic: {code: string; message_key: string; params: Record<string, string | number>; column_id?: string | null; source_position?: number | null}): CatalogDiagnostic {
    return {
      code: diagnostic.code,
      messageKey: diagnostic.message_key,
      params: diagnostic.params ?? {},
      columnId: diagnostic.column_id ?? null,
      sourcePosition: diagnostic.source_position ?? null,
    };
  }

  // ---- 导出（SPEC §10：授权 → 执行；取消不变更草稿/预览） ----
  const exportReady = computed(() =>
    previewStatus.value === "ready"
    && preview.value !== null
    && preview.value.executable
    && previewedColumns.value === draftSignature.value
    && hasShell.value
    && exportState.phase !== "exporting",
  );
  // 旧预览/在途预览：导出被禁用时的可见解释（不能只靠禁用按钮传达原因）
  const exportStale = computed(() =>
    hasShell.value
    && !exportReady.value
    && previewStatus.value !== "failed"
    && (previewStatus.value === "pending" || previewedColumns.value !== draftSignature.value),
  );

  function detectShell(): boolean {
    return typeof window !== "undefined" && Boolean((window as unknown as {pywebview?: {api?: {request_extension_save?: unknown}}}).pywebview?.api?.request_extension_save);
  }

  async function exportXlsx() {
    const current = workspace.value;
    const digest = preview.value?.previewDigest;
    const previewSettingsRevision = previewedSettingsRevision.value;
    // 无工作区/不可导出/无摘要/无绑定设置修订都拒绝导出：最后一项必须是数字，
    // 否则请求体会丢掉 settings_revision 字段（JSON.stringify 丢弃 undefined）
    if (!current || !exportReady.value || !digest || typeof previewSettingsRevision !== "number") return;
    exportState.phase = "exporting";
    exportState.artifactId = "";
    exportState.errorText = "";
    exportState.errorCode = "";
    actionError.value = "";
    // PLAN-DM-024 Task 2 / MEMO-DM-031 F2：授权请求必须被 try/catch 覆盖——壳
    // 窗口未就绪时桥抛 RuntimeError，pywebview 把它变成 JS Promise 拒绝；未捕获
    // 会让 phase 永久卡在 exporting、导出按钮死锁。捕获后转成结构化失败离开
    // 导出中状态，同一出口可重试；用户取消的 idle 语义（下方 value===null 分支）不变。
    let grant: ShellResult<ShellSaveGrant | null> | null;
    try {
      grant = await requestExtensionSave(CATALOG_EXTENSION_ID, CATALOG_ACTION_ID, current.id);
    } catch (error) {
      exportState.phase = "failed";
      exportState.errorCode = "EXTENSION_CAPABILITY_UNAVAILABLE";
      exportState.errorText = localizedError(
        "errors.extension.capabilityUnavailable",
        {},
        error instanceof Error ? error.message : String(error),
      );
      return;
    }
    if (grant === null) {
      // 桥缺失（浏览器/旧壳）：可见说明并停用导出
      exportState.phase = "failed";
      exportState.errorText = t("extensions.sheetCatalog.noShellNotice");
      return;
    }
    if (!grant.ok) {
      exportState.phase = "failed";
      exportState.errorCode = grant.code;
      exportState.errorText = localizedError(grant.message_key, grant.params, grant.message);
      return;
    }
    if (grant.value === null) {
      // 用户取消：不生成文件、不登记 Artifact，草稿与预览保持不变
      exportState.phase = "idle";
      return;
    }
    try {
      const result = await request<ExecuteResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/actions/${CATALOG_ACTION_ID}/execute`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: current.id,
          base_revision_id: current.revision_id,
          template: catalogTemplateSnapshot({...draft.value, name: draftName.value}),
          preview_digest: digest,
          save_grant_id: grant.value.save_grant_id,
          // 预览响应回传的设置修订原样重复：与当前设置不一致时后端拒绝执行
          settings_revision: previewSettingsRevision,
        }),
      });
      // SPEC §10：只显示最终路径与文件名，不显示 Artifact/修订/哈希
      exportState.phase = "success";
      exportState.outputPath = result.output_path;
      exportState.fileName = result.file_name;
      exportState.artifactId = result.artifact_id;
    } catch (error) {
      exportState.phase = "failed";
      exportState.errorCode = error instanceof ApiError ? error.code ?? "" : "";
      exportState.errorText = error instanceof Error ? error.message : String(error);
    }
  }

  // SPEC §10「打开所在文件夹」：成功导出后用 execute 响应中的 artifact_id 调
  // 专用桥方法——前端不传任何路径，路径权威在宿主（Task 11B 起不再用
  // workspace_id 打开 DST 所在目录：用户把 XLSX 另存到任意目录后打开的才是
  // 真实成果所在目录）
  async function openExportFolder() {
    const artifactId = exportState.artifactId;
    if (!artifactId) return;
    const result = await openArtifactFolder(CATALOG_EXTENSION_ID, artifactId);
    if (!result) {
      actionError.value = t("extensions.sheetCatalog.shellUnsupported");
      return;
    }
    if (!result.ok) {
      actionError.value = localizedError(result.message_key, result.params, result.message);
    }
  }

  // ---- 三选一守卫（SPEC §3.2：切换模板/离开页面/停用/关闭统一闸门） ----
  async function guardNavigation(next: () => void | Promise<void>): Promise<NavigationResult> {
    if (!dirty.value) {
      await next();
      return "continue";
    }
    if (guardState.value.open) return "stay";
    guardState.value = {open: true, summary: draftName.value, canSave: canSaveInPlace.value};
    const choice = await new Promise<GuardChoice>(resolve => { guardResolver = resolve; });
    guardState.value.open = false;
    guardResolver = null;
    if (choice === "stay") return "stay";
    if (choice === "save") {
      // 未命名草稿不提供该分支（canSave=false）；用户模板原位保存成功后继续
      if (!await owner.saveInPlace()) return "stay";
      await next();
      return "continue";
    }
    await next();
    return "continue"; // 放弃修改：草稿随选择/卸载复位，无需显式清理
  }
  function resolveGuard(choice: GuardChoice) {
    guardResolver?.(choice);
  }
  onScopeDispose(registerSheetCatalogNavigationGuard(guardNavigation, () => dirty.value));

  // ---- 工作区/草稿变化联动 ----
  watch(workspace, current => {
    if (!current) return;
    // 基准修订漂移使旧预览失效：以新修订重新预览
    schedulePreview();
  });
  // 草稿内容变化才重放预览：按内容签名比较，避免"保存成功后以服务端值重建草稿"
  // 这类等值替换也触发一次多余预览（会推进摘要，可能作废刚取得的导出摘要）。
  watch(draftSignature, signature => {
    if (signature === previewedColumns.value) return;
    schedulePreview();
  });

  return {
    // 设置（模板/草稿/过滤词：见 useSheetCatalogSettings）
    loading, templates, selectedId, selectedTemplate: owner.selectedTemplate, draft, draftName, dirty, canSaveInPlace,
    conflict: owner.conflict, saving: owner.saving, saveError: owner.saveError,
    selectTemplate: owner.selectTemplate, updateColumn: owner.updateColumn, addColumn: owner.addColumn,
    removeColumn: owner.removeColumn, moveColumn: owner.moveColumn,
    saveInPlace: owner.saveInPlace, saveAs: owner.saveAs, removeTemplate: owner.removeTemplate,
    retryAfterConflict: owner.retryAfterConflict,
    filterText: owner.filterText, filterError: owner.filterError, filterDirty: owner.filterDirty,
    setFilterText: owner.setFilterText, saveFilter: owner.saveFilter,
    // 字段目录与预览
    fieldCatalog, preview, previewStatus, previewError, requestPreview, feedback,
    // 字段插入
    caret: owner.caret, caretRequest: owner.caretRequest, trackCaret: owner.trackCaret,
    insertField: owner.insertField, insertReference: owner.insertReference, fieldReference,
    // 导出
    hasShell, exportState, exportReady, exportStale, actionError, loadError, exportXlsx, openExportFolder,
    // 守卫
    guardState, guardNavigation, resolveGuard,
    // 初始装配（设置 + 偏好 + 首次预览）
    initialize,
  };
}

export type SheetCatalogController = ReturnType<typeof useSheetCatalog>;
