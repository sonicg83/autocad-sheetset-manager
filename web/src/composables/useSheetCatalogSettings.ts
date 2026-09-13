// 图纸目录扩展全局设置的唯一状态所有者（PLAN-DM-025 Task 8 / SPEC-DM-012 §6.2、§6.4、§11）。
//
// 它把「目录设置」这一业务域架在扩展设置协议层（useExtensionSettings）之上：协议层负责
// GET/PUT、schema_version 与 expected_revision 的乐观并发、409 冲突、高版本只读；本模块
// 负责模板集合与输出图纸过滤的编辑缓冲、草稿、光标、脏标记，以及「保存」这一动作。
//
// 保存只有一条路径：把完整设置值（user_templates + excluded_title_keywords）写进协议层的
// 编辑缓冲，再提交一次 PUT —— 保存模板与保存过滤词提交的是同一份设置快照，永不互相覆盖
// （SPEC-DM-012 §6.4）。模板条目的 schema_version 与设置本身 schema_version 是两件事：
// 前者由 catalogTemplateSnapshot 写死 1（templates.py 的 TEMPLATE_SCHEMA_VERSION），后者取自服务端快照。
//
// 业务页（useSheetCatalog）与设置中心 custom 面板（SheetCatalogSettingsPanel）各持一份实例：
// 它们共享同一 API 与同一状态模型，但不共享任何可变状态；并行编辑靠 revision 冲突收敛，
// 不采用最后写入覆盖。两份实例都不复制后端最终校验规则（超限/重名/语法以后端诊断为准）。
import {computed, ref, watch} from "vue";
import type {ComputedRef, Ref} from "vue";
import {useI18n} from "vue-i18n";
import {isRevisionConflict} from "./useExtensionSettings";
import type {ExtensionSettingsState} from "./useExtensionSettings";

export const CATALOG_EXTENSION_ID = "dst-manager.sheet-catalog";

// 扩展设置 Schema 版本：与后端 Manifest `settings_schema`
//（src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml）一致。PUT 提交的
// 顶层 schema_version 取自服务端快照（见 useExtensionSettings），本常量只用于断言口径
// 与工作区偏好写入；升级 Manifest 时必须同步提升。
export const CATALOG_SETTINGS_SCHEMA_VERSION = 2;

// 模板条目自身的 Schema（templates.py 的 TEMPLATE_SCHEMA_VERSION）：内置模板与用户模板
// 共用，与上面的设置 Schema 无关。
const TEMPLATE_SCHEMA_VERSION = 1;

// 输出图纸过滤字段名（settings.py 的 EXCLUDED_TITLE_KEYWORDS_FIELD）：字段级错误的
// params.field 与 i18n/测试定位共用同一拼写。
export const EXCLUDED_TITLE_KEYWORDS_FIELD = "excluded_title_keywords";

// SPEC-DM-012 §5.3 首版限制值的展示镜像（“N / 50 列”计数）。权威校验仍在后端
// templates.MAX_COLUMNS；前端只用它渲染分母，不据此拦截输入。
export const SHEET_CATALOG_MAX_COLUMNS = 50;

// SPEC §4.2：点号形式只接受可作单一标识符读取的名称；与固有字段重名的自定义属性必须
// 走方括号形式。字符集与 expressions.py 的 _DOT_NAME_FORBIDDEN 对齐。
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
  // total_rows 是过滤后的实际输出行数，filtered_rows 是被过滤掉的图纸数（SPEC-DM-012 §8.1）
  totalRows: number;
  filteredRows: number;
  previewDigest: string;
  executable: boolean;
}
export type PreviewStatus = "idle" | "pending" | "ready" | "failed";

export type GuardChoice = "save" | "discard" | "stay";
export type NavigationResult = "continue" | "stay";
export type SheetCatalogNavigationGuard = (next: () => void | Promise<void>) => Promise<NavigationResult>;

// 校验反馈：预览诊断与状态。业务页传入真实反馈（显示兼容性徽标与摘要），设置中心面板
// 无工作区快照、不伪造 preview，因此不传（徽标与摘要隐藏，表达式错误也不伪造）。
export interface SheetCatalogValidationFeedback {
  preview: Ref<CatalogPreviewData | null>;
  previewStatus: Ref<PreviewStatus>;
  previewError: Ref<string>;
}

// 模板编辑接口：模板选择、草稿、列增删改序、光标与保存/另存/删除。TemplateBar 只接收
// 这一层；列编辑器另可接收可选的校验反馈。
export interface SheetCatalogTemplateController {
  loading: ComputedRef<boolean>;
  templates: Ref<CatalogTemplate[]>;
  selectedId: Ref<string | null>;
  selectedTemplate: ComputedRef<CatalogTemplate>;
  draft: Ref<CatalogTemplate>;
  draftName: ComputedRef<string>;
  dirty: ComputedRef<boolean>;
  canSaveInPlace: ComputedRef<boolean>;
  saving: ComputedRef<boolean>;
  saveError: ComputedRef<string>;
  conflict: ComputedRef<boolean>;
  // 高版本只读（协议层判定，来源见 useExtensionSettings 的 readOnly）：保存入口据此停用，
  // 不留"点了没反应"的静默出口（I5）。
  readOnly: ComputedRef<boolean>;
  caretRequest: Ref<{columnId: string; position: number} | null>;
  selectTemplate(id: string | null): Promise<void>;
  saveInPlace(): Promise<boolean>;
  saveAs(name: string): Promise<boolean>;
  removeTemplate(): Promise<boolean>;
  retryAfterConflict(): Promise<boolean>;
  addColumn(): void;
  updateColumn(columnId: string, patch: Partial<Pick<CatalogColumn, "header" | "expression">>): void;
  removeColumn(columnId: string): void;
  moveColumn(columnId: string, direction: -1 | 1): void;
  trackCaret(columnId: string, start: number, end: number): void;
}

// 完整设置接口：模板接口 + 输出图纸过滤。custom 设置面板接收完整接口。
export interface SheetCatalogSettingsController extends SheetCatalogTemplateController {
  filterText: Ref<string>;
  filterError: ComputedRef<string>;
  filterDirty: ComputedRef<boolean>;
  setFilterText(value: string): void;
  saveFilter(): Promise<boolean>;
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

// 只比较列内容（列名 + 表达式）的稳定投影：与 UUID 无关的脏判定。
// 脏判定只用它：表头与表达式逐一相同、仅列 UUID 不同的两份模板之间切换不是"未保存修改"。
export function catalogColumnSignature(columns: {header: string; expression: string}[]): string {
  return JSON.stringify(columns.map(column => [column.header, column.expression]));
}

// 预览重放与导出门禁的变更键：在内容投影之上**纳入列 UUID**。
// 后端 preview_digest 按列的规范 ID 计算（preview.py 的 DigestColumn），因此等值但列 ID 不同的
// 两份模板（例如另存为后的内置默认模板会重新铸造 UUID）是两次不同的预览输入。
// 只比较内容会让切换后的导出按钮保持可用：前端带着新列 ID 复用旧摘要上送，执行被
// REPREVIEW_REQUIRED 拒绝，而页面上连"预览已过期"的提示都不会出现（I3）。
export function catalogColumnChangeKey(columns: {columnId: string; header: string; expression: string}[]): string {
  return JSON.stringify(columns.map(column => [column.columnId, column.header, column.expression]));
}

// 模板 → 设置负载条目（templates.py 的 template_to_json 同形）
export function catalogTemplateSnapshot(template: CatalogTemplate) {
  return {
    template_id: template.templateId,
    name: template.name,
    schema_version: TEMPLATE_SCHEMA_VERSION,
    columns: template.columns.map(column => ({column_id: column.columnId, header: column.header, expression: column.expression})),
  };
}

// 设置负载中的模板条目 → 领域模板；结构不符的条目整条拒绝（与旧实现同口径）
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

function cloneTemplate(template: CatalogTemplate): CatalogTemplate {
  return {templateId: template.templateId, name: template.name, columns: template.columns.map(column => ({...column}))};
}

export function useSheetCatalogSettings(
  settings: ExtensionSettingsState,
  options: {
    // SPEC §3.2 的三选一闸门由页面装配（设置中心面板没有该闸门，切换模板直接生效）；
    // 缺省放行，业务页传入自己的 guardNavigation。
    guard?: SheetCatalogNavigationGuard;
    // 选中已保存模板后的 best-effort 工作区偏好记录由页面承担（设置面板无工作区）
    onSelected?: (id: string | null) => void;
  } = {},
): SheetCatalogSettingsOwner {
  const {t, locale} = useI18n();
  const guard = options.guard ?? (async next => { await next(); return "continue" as const; });

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

  // ---- 服务端镜像（唯一权威：协议层快照的持久值） ----
  function serverTemplates(): CatalogTemplate[] {
    const raw = settings.snapshot.value?.value?.["user_templates"];
    if (!Array.isArray(raw)) return [];
    return raw.map(fromEntry).filter((template): template is CatalogTemplate => template !== null);
  }
  function serverFilterText(): string {
    const raw = settings.snapshot.value?.value?.[EXCLUDED_TITLE_KEYWORDS_FIELD];
    return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string").join(", ") : "";
  }

  // ---- 编辑缓冲 ----
  const templates = ref<CatalogTemplate[]>([]);
  const filterText = ref("");
  const selectedId = ref<string | null>(null); // null = 内置默认模板
  const draft = ref<CatalogTemplate>(builtinTemplate());
  // 与当前草稿一致的服务端列基线：加载窗口内 dirty 恒为 false，导航不被误判为未保存草稿
  const savedSnapshot = ref(catalogColumnSignature(draft.value.columns));
  const caret = ref<{columnId: string; start: number; end: number} | null>(null);
  const caretRequest = ref<{columnId: string; position: number} | null>(null);
  // 另存为名称的前端预检错误（空名/与内置显示名冲突）：与保存失败分开，避免互相覆盖
  const nameError = ref("");

  function draftOf(id: string | null): CatalogTemplate {
    if (id === null) return builtinTemplate();
    const source = templates.value.find(template => template.templateId === id);
    return source ? cloneTemplate(source) : builtinTemplate();
  }

  const selectedTemplate = computed<CatalogTemplate>(() => {
    const id = selectedId.value;
    if (id === null) return builtinTemplate();
    return templates.value.find(template => template.templateId === id) ?? builtinTemplate();
  });
  const dirty = computed(() => catalogColumnSignature(draft.value.columns) !== savedSnapshot.value);
  const filterDirty = computed(() => filterText.value !== serverFilterText());
  const canSaveInPlace = computed(() => selectedId.value !== null);
  const draftName = computed(() => (dirty.value && !canSaveInPlace.value ? t("extensions.sheetCatalog.unnamedDraft") : draft.value.name));
  const loading = computed(() => settings.loading.value && settings.snapshot.value === null);
  const saving = computed(() => settings.saving.value);
  // 修订冲突（expected_revision 漂移）才是有专属面板与两条出路的那种冲突：设置 PUT 端点上
  // 还有 Provider 级 409（名称重复/模板上限等），它们不是修订问题，按普通保存失败呈现，
  // 否则用户会看到"按新修订重试"的出路却永远重试不成（确定性死循环）。
  // 判别口径与宿主横幅同源，不在这里再写一份码字面量。
  const revisionConflict = computed(() => isRevisionConflict(settings.conflict.value));
  const conflict = computed(() => revisionConflict.value);

  // ---- 协议层编辑缓冲同步：待保存的完整设置值 ----
  // 待保存意图 = 当前模板集合（选中模板用草稿替换）+ 当前过滤词文本。与「保存」按钮同一
  // 语义：用户点保存时提交的就是这份快照，因此它必须随时与服务端值比较出脏标记。
  function pendingPayload(): {templates: CatalogTemplate[]; filterText: string} {
    const id = selectedId.value;
    const list = templates.value.map(template => (id !== null && template.templateId === id ? cloneTemplate(draft.value) : cloneTemplate(template)));
    return {templates: list, filterText: filterText.value};
  }
  function canonical(list: CatalogTemplate[], filter: string): string {
    return JSON.stringify([list.map(catalogTemplateSnapshot), filter]);
  }
  function serverCanonical(): string {
    return canonical(serverTemplates(), serverFilterText());
  }
  // 只有显式提交才写协议层缓冲：避免「草稿未改」时把无变化的负载提交给宿主保存按钮，
  // 也避免失败/冲突路径上的陈旧负载覆盖用户输入。
  function syncEdits(payload: {templates: CatalogTemplate[]; filterText: string} = pendingPayload()): void {
    const next = {...settings.edits.value};
    // 只读保护（高版本 Schema）：子视图不可脏，编辑缓冲一律不持有待保存负载
    if (settings.readOnly.value || canonical(payload.templates, payload.filterText) === serverCanonical()) {
      delete next["user_templates"];
      delete next[EXCLUDED_TITLE_KEYWORDS_FIELD];
    } else {
      next["user_templates"] = payload.templates.map(catalogTemplateSnapshot);
      next[EXCLUDED_TITLE_KEYWORDS_FIELD] = payload.filterText;
    }
    settings.edits.value = next;
  }
  // 保存等动作展开时的脏标记：草稿、过滤词或模板集合任一与服务端不同即为脏
  const pendingDirty = computed(() => canonical(pendingPayload().templates, pendingPayload().filterText) !== serverCanonical());

  // 由服务端值重建缓冲：载入完成与保存成功后调用。其余时刻保留本地草稿（冲突不丢输入）
  function refresh(): void {
    templates.value = serverTemplates().map(cloneTemplate);
    if (selectedId.value !== null && !templates.value.some(template => template.templateId === selectedId.value)) {
      selectedId.value = null; // 服务端已无此模板（如其他窗口删除）：回到内置默认模板
    }
    draft.value = draftOf(selectedId.value);
    savedSnapshot.value = catalogColumnSignature(draft.value.columns);
    filterText.value = serverFilterText();
    nameError.value = "";
    syncEdits();
  }

  // 协议层丢弃本地编辑时（子视图「放弃本地修改」或高版本只读的 applyReadOnly），本地缓冲
  // 必须一并复位——否则界面上还挂着"有未保存修改"，再点保存会把刚被判废的草稿重新提交。
  // 冲突或成功落盘的路径不会走到这里：前者冲突横幅仍在（等用户裁决），后者提交路径已重建。
  watch(() => Object.keys(settings.edits.value).length, count => {
    if (count > 0 || settings.conflict.value !== null) return;
    if (canonical(pendingPayload().templates, pendingPayload().filterText) === serverCanonical()) return;
    refresh();
  });

  // ---- 选择模板（SPEC §3.2：有未保存修改先三选一）；只有已保存模板写入工作区偏好 ----
  async function selectTemplate(id: string | null): Promise<void> {
    if (id === selectedId.value) return;
    if (dirty.value) {
      const result = await guard(async () => applySelection(id));
      if (result === "stay") return;
    } else {
      applySelection(id);
    }
    options.onSelected?.(id);
  }
  function applySelection(id: string | null): void {
    selectedId.value = id;
    draft.value = draftOf(id);
    savedSnapshot.value = catalogColumnSignature(draft.value.columns);
    nameError.value = "";
    syncEdits();
  }

  // ---- 草稿编辑（草稿是选中模板的编辑副本，保存成功前不写回集合） ----
  function updateColumn(columnId: string, patch: Partial<Pick<CatalogColumn, "header" | "expression">>): void {
    draft.value = {
      ...draft.value,
      columns: draft.value.columns.map(column => (column.columnId === columnId ? {...column, ...patch} : column)),
    };
    syncEdits();
  }
  function addColumn(): void {
    draft.value = {
      ...draft.value,
      columns: [...draft.value.columns, {columnId: crypto.randomUUID(), header: "", expression: ""}],
    };
    syncEdits();
  }
  function removeColumn(columnId: string): void {
    draft.value = {...draft.value, columns: draft.value.columns.filter(column => column.columnId !== columnId)};
    syncEdits();
  }
  function moveColumn(columnId: string, direction: -1 | 1): void {
    const index = draft.value.columns.findIndex(column => column.columnId === columnId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= draft.value.columns.length) return;
    const columns = [...draft.value.columns];
    [columns[index], columns[target]] = [columns[target], columns[index]];
    draft.value = {...draft.value, columns};
    syncEdits();
  }

  // ---- 字段插入（textarea selection API；光标由 ColumnEditor 跟踪） ----
  function trackCaret(columnId: string, start: number, end: number): void {
    caret.value = {columnId, start, end};
  }
  function insertField(columnId: string, reference: string, selectionStart: number, selectionEnd: number): void {
    const column = draft.value.columns.find(item => item.columnId === columnId);
    if (!column) return;
    const start = Math.max(0, Math.min(selectionStart, column.expression.length));
    const end = Math.max(start, Math.min(selectionEnd, column.expression.length));
    updateColumn(columnId, {expression: column.expression.slice(0, start) + reference + column.expression.slice(end)});
    caretRequest.value = {columnId, position: start + reference.length};
  }
  function insertReference(reference: string): void {
    const column = draft.value.columns[0];
    if (!column) return;
    const tracked = caret.value;
    if (tracked && draft.value.columns.some(item => item.columnId === tracked.columnId)) {
      insertField(tracked.columnId, reference, tracked.start, tracked.end);
      return;
    }
    insertField(column.columnId, reference, column.expression.length, column.expression.length);
  }

  // ---- 输出图纸过滤（SPEC §6.4；规格化在 Provider，前端只回显服务端数组） ----
  function setFilterText(value: string): void {
    filterText.value = value;
    // 输入即清除本字段的服务端错误（协议层 setField 的同一语义）：字段错误不自行消失会让
    // 修正后的输入继续顶着红框与 aria-invalid=true，直到下一次成功保存。清错不等于本地校验——
    // 值仍原样上送，Provider 仍是唯一校验者。
    if (settings.fieldErrors.value[EXCLUDED_TITLE_KEYWORDS_FIELD] !== undefined) {
      const next = {...settings.fieldErrors.value};
      delete next[EXCLUDED_TITLE_KEYWORDS_FIELD];
      settings.fieldErrors.value = next;
    }
    syncEdits();
  }
  const filterError = computed(() => settings.fieldErrors.value[EXCLUDED_TITLE_KEYWORDS_FIELD]?.message ?? "");
  const saveError = computed(() => {
    if (nameError.value !== "") return nameError.value;
    const fieldKeys = Object.keys(settings.fieldErrors.value).filter(key => key !== EXCLUDED_TITLE_KEYWORDS_FIELD);
    if (fieldKeys.length > 0) return settings.fieldErrors.value[fieldKeys[0]!]!.message;
    const failure = settings.conflict.value;
    if (failure !== null) return revisionConflict.value ? "" : failure.message; // 修订冲突有专属面板
    return settings.saveFailed.value;
  });

  // ---- 保存（单一路径）：提交完整设置快照，成功后以服务端规范化值重建缓冲 ----
  async function submit(payload: {templates: CatalogTemplate[]; filterText: string}): Promise<boolean> {
    if (settings.readOnly.value) return false;
    nameError.value = "";
    syncEdits(payload);
    await settings.save();
    // 成功判定只看协议层，且不得把“只读保护拒绝”当成成功：409 SCHEMA_NEWER 会在保存过程中
    // 上调只读并丢弃本地编辑（dirty 因此变假），若只看 dirty 会把未落盘误报为保存成功
    //（模态关闭 + 成功提示）。
    if (settings.readOnly.value || settings.dirty.value) return false;
    refresh();
    return true;
  }

  async function saveInPlace(): Promise<boolean> {
    if (selectedId.value === null) return false;
    return submit(pendingPayload());
  }

  async function saveFilter(): Promise<boolean> {
    if (!filterDirty.value && !pendingDirty.value) return false;
    return submit(pendingPayload());
  }

  async function saveAs(name: string): Promise<boolean> {
    const trimmed = name.trim();
    if (!trimmed) {
      nameError.value = t("extensions.sheetCatalog.saveAsNameRequired");
      return false;
    }
    // PLAN-DM-024 Task 3 / MEMO-DM-031 F4：内置模板显示名随宿主语言变化，服务端不认识本地化
    // 文案——与内置显示名（当前 locale）大小写不敏感相同的另存名必须在前端拦截。
    const builtinName = t("extensions.sheetCatalog.builtinName");
    if (trimmed.toLocaleLowerCase(locale.value) === builtinName.trim().toLocaleLowerCase(locale.value)) {
      nameError.value = t("extensions.sheetCatalog.saveAsBuiltinConflict");
      return false;
    }
    // 冲突态另存为（SPEC §11）：先采用服务端当前的模板集合——另一窗口的写入已经落盘，
    // 用陈旧集合作负载会把别人的模板覆盖掉。本地保留草稿（草稿内容成为新模板的列）。
    if (revisionConflict.value) {
      templates.value = serverTemplates().map(cloneTemplate);
      if (selectedId.value !== null && !templates.value.some(template => template.templateId === selectedId.value)) {
        selectedId.value = null;
      }
    }
    const created: CatalogTemplate = {templateId: crypto.randomUUID(), name: trimmed, columns: draft.value.columns.map(column => ({...column}))};
    const payload = pendingPayload();
    const ok = await submit({templates: [...payload.templates, created], filterText: payload.filterText});
    if (!ok) return false;
    selectedId.value = created.templateId;
    draft.value = draftOf(created.templateId);
    savedSnapshot.value = catalogColumnSignature(draft.value.columns);
    syncEdits();
    options.onSelected?.(created.templateId);
    return true;
  }

  async function removeTemplate(): Promise<boolean> {
    const id = selectedId.value;
    if (id === null) return false;
    const payload = pendingPayload();
    const ok = await submit({templates: payload.templates.filter(template => template.templateId !== id), filterText: payload.filterText});
    if (!ok) return false;
    selectedId.value = null; // 删除后回到内置默认模板（SPEC §3.2）
    draft.value = draftOf(null);
    savedSnapshot.value = catalogColumnSignature(draft.value.columns);
    syncEdits();
    return true;
  }

  // 冲突恢复（SPEC §11）：协议层在冲突时已刷新服务端修订并保留本地编辑，重试=再提交一次
  async function retryAfterConflict(): Promise<boolean> {
    if (!revisionConflict.value) return false;
    return submit(pendingPayload());
  }

  return {
    loading, templates, selectedId, selectedTemplate, draft, draftName, dirty, canSaveInPlace,
    saving, saveError, conflict, readOnly: settings.readOnly, caretRequest,
    selectTemplate, saveInPlace, saveAs, removeTemplate, retryAfterConflict,
    addColumn, updateColumn, removeColumn, moveColumn, trackCaret,
    filterText, filterError, filterDirty, setFilterText, saveFilter,
    // 页面装配层使用（不进入组件接口闭集）：由服务端值重建缓冲、字段插入的光标协议
    // 与工作区偏好落入前的初始选择
    refresh, applySelection, caret, insertField, insertReference, pendingDirty,
  };
}

// 页面装配层额外消费的能力（不进入组件接口：TemplateBar/ColumnEditor/面板只用上面的闭集）：
// 由服务端值重建缓冲、初始选择、字段插入的光标协议与待保存脏标记。
export interface SheetCatalogSettingsOwner extends SheetCatalogSettingsController {
  refresh(): void;
  applySelection(id: string | null): void;
  caret: Ref<{columnId: string; start: number; end: number} | null>;
  insertField(columnId: string, reference: string, selectionStart: number, selectionEnd: number): void;
  insertReference(reference: string): void;
  pendingDirty: ComputedRef<boolean>;
}
