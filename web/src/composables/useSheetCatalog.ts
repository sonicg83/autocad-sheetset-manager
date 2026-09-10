// 图纸目录页面唯一状态所有者（PLAN-DM-020 Task 11 / SPEC-DM-012 §3/§7/§8/§10/§11）。
// 持有模板集合/当前模板/未保存草稿/脏标记/字段目录/防抖预览/保存与导出状态；
// 六个 sheet-catalog 组件与 SheetCatalogView 只经本组合式函数读写状态，不复制
// 后端最终校验规则（超限/重名/语法错误以后端诊断为准做展示层）。
//
// 导航保护（SPEC §3.2）：guardNavigation(next) 是切换模板/切换页签/离开/关闭
// 的统一三选一闸门。页面状态属于视图实例，视图只在工作区页签激活时挂载，因此
// 通过模块级守卫登记（useTheme 同款模块级单例先例）让宿主 App.vue 在切页签、
// 停用扩展与关闭/刷新工作区时征询本页守卫；视图卸载时自动注销。
import {computed, onScopeDispose, reactive, ref, watch} from "vue";
import type {Ref} from "vue";
import {useI18n} from "vue-i18n";
import {ApiError, localizedError, request} from "../api/client";
import {openWorkspaceFolder, requestExtensionSave, shellReady} from "../api/shell";
import type {Workspace} from "../api/contracts";

export const CATALOG_EXTENSION_ID = "dst-manager.sheet-catalog";
const CATALOG_ACTION_ID = "export-xlsx";
const PREVIEW_DEBOUNCE_MS = 300;

// SPEC §4.2：点号形式只接受可作单一标识符读取的名称；与固有字段重名的自定义
// 属性必须走方括号形式。字符集与 expressions.py 的 _DOT_NAME_FORBIDDEN 对齐。
const DOT_NAME_FORBIDDEN = new Set(' \t\r\n.[]{}"\'(),;:=\\'.split(""));
const SHEET_BUILTIN_FIELDS = ["number", "title", "file_name"] as const;

export interface CatalogColumn {columnId: string; header: string; expression: string}
export interface CatalogTemplate {templateId: string | null; name: string; columns: CatalogColumn[]}
export interface CatalogField {scope: "sheetset" | "sheet"; canonicalName: string; builtin: boolean}
export interface CatalogDiagnostic {
  code: string;
  messageKey: string;
  params: Record<string, string | number>;
  columnId: string | null;
  sourcePosition: number | null;
}
export interface CatalogPreviewData {
  errors: CatalogDiagnostic[];
  warnings: CatalogDiagnostic[];
  rows: string[][];
  totalRows: number;
  previewDigest: string;
  executable: boolean;
}

type PreviewResponse = {
  normalized_template: {template_id: string | null; name: string; schema_version: number; columns: {column_id: string | null; header: string; expression: string}[]};
  field_catalog: {sheetset: {scope: "sheetset" | "sheet"; canonical_name: string; builtin: boolean}[]; sheet: {scope: "sheetset" | "sheet"; canonical_name: string; builtin: boolean}[]};
  errors: {code: string; message_key: string; params: Record<string, string | number>; column_id?: string | null; source_position?: number | null}[];
  warnings: {code: string; message_key: string; params: Record<string, string | number>; column_id?: string | null; source_position?: number | null}[];
  rows: string[][];
  total_rows: number;
  preview_digest: string;
  executable: boolean;
};

type SettingsResponse = {schema_version: number; revision: number; value: {user_templates?: unknown[]}};
type PreferenceResponse = {schema_version: number; revision: number; value: {template_id?: unknown}};
type ExecuteResponse = {artifact_id: string; file_name: string; output_path: string; warnings?: {code: string; message_key: string; params: Record<string, string | number>}[]};

export type GuardChoice = "save" | "discard" | "stay";
export type NavigationResult = "continue" | "stay";
export type SheetCatalogNavigationGuard = (next: () => void | Promise<void>) => Promise<NavigationResult>;

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

// 字段引用语法（SPEC §4.2）：按规范名称自动选择点号或方括号 JSON 字符串形式
export function fieldReference(scope: "sheetset" | "sheet", canonicalName: string): string {
  const lower = canonicalName.toLowerCase();
  const reservedConflict = scope === "sheet"
    && SHEET_BUILTIN_FIELDS.includes(lower as (typeof SHEET_BUILTIN_FIELDS)[number])
    && !(SHEET_BUILTIN_FIELDS as readonly string[]).includes(canonicalName);
  const needsQuoted = canonicalName === ""
    || reservedConflict
    || [...canonicalName].some(char => DOT_NAME_FORBIDDEN.has(char));
  if (needsQuoted) return `{${scope}[${JSON.stringify(canonicalName)}]}`;
  return `{${scope}.${canonicalName}}`;
}

function stableColumns(columns: CatalogColumn[]): string {
  return JSON.stringify(columns.map(column => [column.header, column.expression]));
}

export function useSheetCatalog(workspace: Ref<Workspace | null>) {
  const {t} = useI18n();

  // ---- 内置默认模板（SPEC §6.2，随扩展交付；表头文案经宿主 i18n） ----
  function builtinTemplate(): CatalogTemplate {
    return {
      templateId: null,
      name: t("extensions.sheetCatalog.builtinName"),
      columns: [
        {columnId: crypto.randomUUID(), header: t("extensions.sheetCatalog.defaultHeaderNumber"), expression: "{sheet.number}"},
        {columnId: crypto.randomUUID(), header: t("extensions.sheetCatalog.defaultHeaderTitle"), expression: "{sheet.title}"},
        {columnId: crypto.randomUUID(), header: t("extensions.sheetCatalog.defaultHeaderFileName"), expression: "{sheet.file_name}"},
      ],
    };
  }

  // ---- 模板与草稿 ----
  const templates = ref<CatalogTemplate[]>([]);
  const settingsRevision = ref(0);
  const selectedId = ref<string | null>(null); // null = 内置默认模板
  const draft = ref<CatalogTemplate>(builtinTemplate());
  // 与初始草稿一致：加载窗口内 dirty 恒为 false，导航不被误判为未保存草稿
  const savedSnapshot = ref(stableColumns(draft.value.columns));
  const loading = ref(true);
  // 保存冲突（SPEC §11）：保留本地编辑，提供"另存为新模板 / 按新修订重试"
  const conflict = ref(false);
  const saveError = ref("");
  const saving = ref(false);
  // 待重放的保存负载（冲突重试用）：刷新服务端修订后原样重放
  let pendingReplay: {value: Record<string, unknown>} | null = null;

  const selectedTemplate = computed<CatalogTemplate>(() => {
    if (selectedId.value === null) return builtinTemplate();
    return templates.value.find(template => template.templateId === selectedId.value) ?? builtinTemplate();
  });
  const dirty = computed(() => stableColumns(draft.value.columns) !== savedSnapshot.value);
  const canSaveInPlace = computed(() => selectedId.value !== null);
  const draftName = computed(() => (dirty.value && !canSaveInPlace.value ? t("extensions.sheetCatalog.unnamedDraft") : draft.value.name));

  // ---- 字段目录 / 预览 ----
  const fieldCatalog = ref<{sheetset: CatalogField[]; sheet: CatalogField[]}>({sheetset: [], sheet: []});
  const preview = ref<CatalogPreviewData | null>(null);
  const previewStatus = ref<"idle" | "pending" | "ready" | "failed">("idle");
  const previewError = ref("");
  // 本次预览对应的草稿列快照：导出只允许"预览与草稿一致"时进行（SPEC §3.1 第 7 步）
  const previewedColumns = ref("");
  let previewGeneration = 0;
  let previewTimer: ReturnType<typeof setTimeout> | null = null;

  // ---- 保存授权 / 导出状态（SPEC §10） ----
  const exportState = reactive({
    phase: "idle" as "idle" | "exporting" | "success" | "failed",
    outputPath: "",
    fileName: "",
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

  // ---- 模板快照与设置负载 ----
  function toSnapshot(template: CatalogTemplate) {
    return {
      template_id: template.templateId,
      name: template.name,
      schema_version: 1 as const,
      columns: template.columns.map(column => ({column_id: column.columnId, header: column.header, expression: column.expression})),
    };
  }
  function fromEntry(entry: unknown): CatalogTemplate | null {
    if (typeof entry !== "object" || entry === null) return null;
    const record = entry as Record<string, unknown>;
    const id = record.template_id;
    const name = record.name;
    const columns = record.columns;
    if (typeof id !== "string" || typeof name !== "string" || !Array.isArray(columns)) return null;
    const mapped: CatalogColumn[] = [];
    for (const item of columns) {
      if (typeof item !== "object" || item === null) return null;
      const column = item as Record<string, unknown>;
      if (typeof column.column_id !== "string" || typeof column.header !== "string" || typeof column.expression !== "string") return null;
      mapped.push({columnId: column.column_id, header: column.header, expression: column.expression});
    }
    return {templateId: id, name, columns: mapped};
  }
  function settingsPayload(userTemplates: CatalogTemplate[]) {
    return {schema_version: 1, user_templates: userTemplates.map(toSnapshot)};
  }

  // ---- 初始装配：设置 + 偏好（上次选中的已保存模板） ----
  async function initialize() {
    const current = workspace.value;
    if (!current) return;
    loading.value = true;
    try {
      const [settings, preference] = await Promise.all([
        request<SettingsResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/settings`),
        request<PreferenceResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/workspaces/${current.id}/preferences`),
      ]);
      settingsRevision.value = settings.revision;
      templates.value = (settings.value.user_templates ?? [])
        .map(fromEntry)
        .filter((template): template is CatalogTemplate => template !== null);
      const preferred = typeof preference.value?.template_id === "string" ? preference.value.template_id : null;
      applySelection(templates.value.some(template => template.templateId === preferred) ? preferred : null);
      void schedulePreview(0);
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error);
      applySelection(null);
    } finally {
      loading.value = false;
    }
  }

  function applySelection(id: string | null) {
    selectedId.value = id;
    const source = id === null ? builtinTemplate() : templates.value.find(template => template.templateId === id);
    if (!source) return;
    draft.value = {templateId: source.templateId, name: source.name, columns: source.columns.map(column => ({...column}))};
    savedSnapshot.value = stableColumns(source.columns);
    conflict.value = false;
    saveError.value = "";
    pendingReplay = null;
  }

  // 选择模板（SPEC §3.2：有未保存修改先三选一）；只有已保存模板写入工作区偏好
  async function selectTemplate(id: string | null) {
    if (id === selectedId.value) return;
    if (dirty.value) {
      const result = await guardNavigation(async () => applySelection(id));
      if (result === "stay") return;
    } else {
      applySelection(id);
    }
    await recordPreference(id);
  }

  async function recordPreference(id: string | null) {
    const current = workspace.value;
    if (!current || id === null) return; // 内置模板与未命名草稿不进入工作区偏好
    try {
      await request(`/api/extensions/${CATALOG_EXTENSION_ID}/workspaces/${current.id}/preferences`, {
        method: "PUT",
        body: JSON.stringify({schema_version: 1, value: {template_id: id}}),
      });
    } catch {
      // 偏好 best-effort：失败可诊断但不阻断模板选择
    }
  }

  // ---- 草稿编辑 ----
  function updateColumn(columnId: string, patch: Partial<Pick<CatalogColumn, "header" | "expression">>) {
    draft.value = {
      ...draft.value,
      columns: draft.value.columns.map(column => (column.columnId === columnId ? {...column, ...patch} : column)),
    };
  }
  function addColumn() {
    draft.value = {
      ...draft.value,
      columns: [...draft.value.columns, {columnId: crypto.randomUUID(), header: "", expression: ""}],
    };
  }
  function removeColumn(columnId: string) {
    draft.value = {...draft.value, columns: draft.value.columns.filter(column => column.columnId !== columnId)};
  }
  function moveColumn(columnId: string, direction: -1 | 1) {
    const index = draft.value.columns.findIndex(column => column.columnId === columnId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= draft.value.columns.length) return;
    const columns = [...draft.value.columns];
    [columns[index], columns[target]] = [columns[target], columns[index]];
    draft.value = {...draft.value, columns};
  }

  // ---- 字段插入（textarea selection API；光标由 ColumnEditor 跟踪） ----
  const caret = ref<{columnId: string; start: number; end: number} | null>(null);
  const caretRequest = ref<{columnId: string; position: number} | null>(null);
  function trackCaret(columnId: string, start: number, end: number) {
    caret.value = {columnId, start, end};
  }
  function insertField(columnId: string, reference: string, selectionStart: number, selectionEnd: number) {
    const column = draft.value.columns.find(item => item.columnId === columnId);
    if (!column) return;
    const start = Math.max(0, Math.min(selectionStart, column.expression.length));
    const end = Math.max(start, Math.min(selectionEnd, column.expression.length));
    const expression = column.expression.slice(0, start) + reference + column.expression.slice(end);
    updateColumn(columnId, {expression});
    caretRequest.value = {columnId, position: start + reference.length};
  }
  function insertReference(reference: string) {
    const column = draft.value.columns[0];
    if (!column) return;
    const tracked = caret.value;
    if (tracked && draft.value.columns.some(item => item.columnId === tracked.columnId)) {
      insertField(tracked.columnId, reference, tracked.start, tracked.end);
      return;
    }
    insertField(column.columnId, reference, column.expression.length, column.expression.length);
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
    const snapshotColumns = stableColumns(draft.value.columns);
    previewStatus.value = "pending";
    try {
      const result = await request<PreviewResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/actions/${CATALOG_ACTION_ID}/preview`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: current.id,
          base_revision_id: current.revision_id,
          template: toSnapshot({...draft.value, name: draftName.value}),
        }),
      });
      if (generation !== previewGeneration || workspace.value?.id !== current.id) return;
      fieldCatalog.value = {
        sheetset: result.field_catalog.sheetset.map(field => ({scope: field.scope, canonicalName: field.canonical_name, builtin: field.builtin})),
        sheet: result.field_catalog.sheet.map(field => ({scope: field.scope, canonicalName: field.canonical_name, builtin: field.builtin})),
      };
      preview.value = {
        errors: result.errors.map(normalizeDiagnostic),
        warnings: result.warnings.map(normalizeDiagnostic),
        rows: result.rows,
        totalRows: result.total_rows,
        previewDigest: result.preview_digest,
        executable: result.executable,
      };
      previewError.value = "";
      previewedColumns.value = snapshotColumns;
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

  // ---- 保存 / 另存为 / 删除（PUT 设置，乐观并发；冲突保留本地编辑） ----
  function handleSaveError(error: unknown) {
    if (error instanceof ApiError && (error.code === "SHEET_CATALOG_TEMPLATE_CONFLICT" || (error.status === 409 && error.code === "EXTENSION_SETTINGS_INVALID"))) {
      conflict.value = true;
      saveError.value = "";
      return;
    }
    saveError.value = error instanceof Error ? error.message : String(error);
    conflict.value = false;
  }

  async function putSettings(userTemplates: CatalogTemplate[]): Promise<boolean> {
    const payload = settingsPayload(userTemplates);
    pendingReplay = {value: payload};
    try {
      const saved = await request<SettingsResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/settings`, {
        method: "PUT",
        body: JSON.stringify({schema_version: 1, expected_revision: settingsRevision.value, value: payload}),
      });
      settingsRevision.value = saved.revision;
      templates.value = userTemplates;
      pendingReplay = null;
      conflict.value = false;
      saveError.value = "";
      return true;
    } catch (error) {
      handleSaveError(error);
      return false;
    }
  }

  async function saveInPlace(): Promise<boolean> {
    const id = selectedId.value;
    if (id === null || saving.value) return false;
    saving.value = true;
    try {
      const next = templates.value.map(template => (template.templateId === id ? {...draft.value, templateId: id} : template));
      const ok = await putSettings(next);
      if (ok) savedSnapshot.value = stableColumns(draft.value.columns);
      return ok;
    } finally {
      saving.value = false;
    }
  }

  async function saveAs(name: string): Promise<boolean> {
    const trimmed = name.trim();
    if (!trimmed || saving.value) {
      if (!trimmed) saveError.value = t("extensions.sheetCatalog.saveAsNameRequired");
      return false;
    }
    saving.value = true;
    try {
      const template: CatalogTemplate = {templateId: crypto.randomUUID(), name: trimmed, columns: draft.value.columns.map(column => ({...column}))};
      const ok = await putSettings([...templates.value, template]);
      if (ok) {
        applySelection(template.templateId);
        void recordPreference(template.templateId);
      }
      return ok;
    } finally {
      saving.value = false;
    }
  }

  async function removeTemplate(): Promise<boolean> {
    const id = selectedId.value;
    if (id === null || saving.value) return false;
    saving.value = true;
    try {
      const ok = await putSettings(templates.value.filter(template => template.templateId !== id));
      if (ok) applySelection(null); // 删除后回到内置默认模板（SPEC §3.2）
      return ok;
    } finally {
      saving.value = false;
    }
  }

  // 冲突恢复（SPEC §11）：先刷新服务端模板修订，再原样重放上次保存负载
  async function retryAfterConflict(): Promise<boolean> {
    if (!pendingReplay) return false;
    try {
      const settings = await request<SettingsResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/settings`);
      settingsRevision.value = settings.revision;
      templates.value = (settings.value.user_templates ?? []).map(fromEntry).filter((template): template is CatalogTemplate => template !== null);
    } catch (error) {
      handleSaveError(error);
      return false;
    }
    saving.value = true;
    try {
      const saved = await request<SettingsResponse>(`/api/extensions/${CATALOG_EXTENSION_ID}/settings`, {
        method: "PUT",
        body: JSON.stringify({schema_version: 1, expected_revision: settingsRevision.value, value: pendingReplay.value}),
      });
      settingsRevision.value = saved.revision;
      templates.value = (saved.value.user_templates ?? []).map(fromEntry).filter((template): template is CatalogTemplate => template !== null);
      pendingReplay = null;
      conflict.value = false;
      // 重放后把当前草稿对齐到同 ID 的已保存模板（原位保存场景）
      if (selectedId.value !== null) {
        const savedTemplate = templates.value.find(template => template.templateId === selectedId.value);
        if (savedTemplate) {
          draft.value = {templateId: savedTemplate.templateId, name: savedTemplate.name, columns: savedTemplate.columns.map(column => ({...column}))};
          savedSnapshot.value = stableColumns(savedTemplate.columns);
        }
      }
      return true;
    } catch (error) {
      handleSaveError(error);
      return false;
    } finally {
      saving.value = false;
    }
  }
  function dismissConflict() {
    conflict.value = false;
    pendingReplay = null;
  }

  // ---- 导出（SPEC §10：授权 → 执行；取消不变更草稿/预览） ----
  const exportReady = computed(() =>
    previewStatus.value === "ready"
    && preview.value !== null
    && preview.value.executable
    && previewedColumns.value === stableColumns(draft.value.columns)
    && hasShell.value
    && exportState.phase !== "exporting",
  );
  // 旧预览/在途预览：导出被禁用时的可见解释（不能只靠禁用按钮传达原因）
  const exportStale = computed(() =>
    hasShell.value
    && !exportReady.value
    && previewStatus.value !== "failed"
    && (previewStatus.value === "pending" || previewedColumns.value !== stableColumns(draft.value.columns)),
  );

  function detectShell(): boolean {
    return typeof window !== "undefined" && Boolean((window as unknown as {pywebview?: {api?: {request_extension_save?: unknown}}}).pywebview?.api?.request_extension_save);
  }

  async function exportXlsx() {
    const current = workspace.value;
    const digest = preview.value?.previewDigest;
    if (!current || !exportReady.value || !digest) return;
    exportState.phase = "exporting";
    exportState.errorText = "";
    exportState.errorCode = "";
    actionError.value = "";
    const grant = await requestExtensionSave(CATALOG_EXTENSION_ID, CATALOG_ACTION_ID, current.id);
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
          template: toSnapshot({...draft.value, name: draftName.value}),
          preview_digest: digest,
          save_grant_id: grant.value.save_grant_id,
        }),
      });
      // SPEC §10：只显示最终路径与文件名，不显示 Artifact/修订/哈希
      exportState.phase = "success";
      exportState.outputPath = result.output_path;
      exportState.fileName = result.file_name;
    } catch (error) {
      exportState.phase = "failed";
      exportState.errorCode = error instanceof ApiError ? error.code ?? "" : "";
      exportState.errorText = error instanceof Error ? error.message : String(error);
    }
  }

  async function openExportFolder() {
    const current = workspace.value;
    if (!current) return;
    const result = await openWorkspaceFolder(current.id);
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
      const saved = await saveInPlace();
      if (!saved) return "stay";
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
  watch(() => draft.value.columns, () => {
    schedulePreview();
  }, {deep: true});

  return {
    // 模板与草稿
    loading, templates, selectedId, selectedTemplate, draft, draftName, dirty, canSaveInPlace,
    settingsRevision, conflict, saveError, saving,
    selectTemplate, updateColumn, addColumn, removeColumn, moveColumn,
    saveInPlace, saveAs, removeTemplate, retryAfterConflict, dismissConflict,
    // 字段目录与预览
    fieldCatalog, preview, previewStatus, previewError, requestPreview,
    // 字段插入
    caret, caretRequest, trackCaret, insertField, insertReference, fieldReference,
    // 导出
    hasShell, exportState, exportReady, exportStale, actionError, loadError, exportXlsx, openExportFolder,
    // 守卫
    guardState, guardNavigation, resolveGuard,
    // 初始装配（设置 + 偏好 + 首次预览）
    initialize,
  };
}

export type SheetCatalogController = ReturnType<typeof useSheetCatalog>;
