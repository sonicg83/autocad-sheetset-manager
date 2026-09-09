// 属性页会话缓冲与提交生命周期（PLAN-DM-016 任务 2，SPEC-DM-010 §5.4）。
// 三层快照：正式基准（baseWorkspace）/草稿投影（workspace）/当前输入（input），均来自 Task 1 纯模型。
// - workspace/revision 切换时重建三层快照（输入不跨基准保留；切换前由 guardAllInputs 统一三选一）；
// - 普通投影变化 syncFromProjection()：采纳草稿投影并保留未加入草稿的本地编辑（不回填用户输入）；
// - submitValues() 只生成一个完整 update_sheet_set 命令，经既有 submitCommands('metadata') 进入
//   权威投影与保存失败重试，不另建属性草稿栈、不做前端最终校验；
// - invalidateDefinitions(keys)：删除属性定义后对应图纸集值字段进入失效集合（App 按命令簿整体重算传入，
//   撤销/移除命令后自动解除）；失效字段阻断提交但保留输入供核对；
// - guard(next)：三选一（加入草稿后继续/放弃输入/留在此处），与图纸页共享同一个 UnsavedInputDialog 实例。
// - 面板会话态（任务 6）：定义折叠/查询/作用域/页码、值面板折叠、CSV 面板折叠与导入区开关、
//   新增字段表单均在此持有；切工作区（基准重建）重置为定义折叠、值展开，切主标签保留（P-09）。
import {computed, reactive, ref, watch} from "vue";
import type {ComputedRef, Ref} from "vue";
import {useI18n} from "vue-i18n";
import type {ChangeCommand, PropertyType, Workspace} from "../api/contracts";
import {buildSheetSetCommand, createPropertyBuffer, filterValueKeys, valueStatus} from "../features/properties/model";
import type {DefinitionScopeFilter} from "../features/properties/model";
import type {
  PropertyBuffer, PropertyKey, PropertySearchMode, PropertySubmitResult, ValueKey, ValueStatus,
} from "../features/properties/types";
import type {GuardChoice} from "../features/sheets/types";

export type PropertiesWorkspaceDeps = {
  workspace: Ref<Workspace | null>;
  baseWorkspace: Ref<Workspace | null>;
  submitCommands: (commands: ChangeCommand[], label: string, category: "metadata" | "structural" | "property") => Promise<PropertySubmitResult>;
  // 新增属性定义命令簿门禁（App 既有 addCommand(...,'property')）：返回 false 表示未入栈
  addPropertyDefinition: (form: {type: PropertyType; name: string; defaultValue: string}) => boolean;
  // 页面级错误呈现（App 既有 error 通知条）
  notifyError: (message: string) => void;
};

export type GuardState = {open: boolean; summary: string; canSave: boolean};

const EMPTY_STATUS: ValueStatus = {dirty: false, pending: false, invalid: false};

export function usePropertiesWorkspace(deps: PropertiesWorkspaceDeps) {
  const {t} = useI18n();
  const base = ref<PropertyBuffer | null>(null);
  const draft = ref<PropertyBuffer | null>(null);
  const input = ref<PropertyBuffer | null>(null);
  // 失效字段集合：整体替换触发重算，不在原集合上就地修改
  const invalidKeys = ref<ReadonlySet<ValueKey>>(new Set());
  const errors = ref<Partial<Record<ValueKey, string>>>({});
  const summaryError = ref("");
  const guardState = ref<GuardState>({open: false, summary: "", canSave: true});
  // 查询/仅看修改/活动字段：任务 3 值面板直接消费；hiddenDirtyCount 依此计算隐藏修改数
  const search = ref("");
  const searchMode = ref<PropertySearchMode>("all");
  const changedOnly = ref(false);
  const activeKey = ref<ValueKey | null>(null);
  // —— 面板会话态（PLAN-DM-016 任务 6）：折叠/查询/页码/导入区开关为工作区会话态 ——
  // 切工作区（基准重建）重置为定义折叠、值展开、导入区关闭、查询与页码清零；同一会话内切主标签保留。
  const definitionsCollapsed = ref(true);
  const valuesCollapsed = ref(false);
  const csvCollapsed = ref(false);   // 面板体折叠（默认展开）
  const csvOpen = ref(false);        // 导入区开关（默认关闭）
  const definitionsQuery = ref("");
  const definitionsScope = ref<DefinitionScopeFilter>("all");
  const definitionsPage = ref(1);
  // 新增字段表单（原 App propertyForm 移交）：作用域/名称/默认值，成功清空、失败保留
  const definitionForm = reactive<{type: PropertyType; name: string; defaultValue: string}>({type: "sheet", name: "", defaultValue: ""});
  let guardResolver: ((choice: GuardChoice) => void) | null = null;
  let seen = "";

  function statusOf(key: ValueKey): ValueStatus {
    if (!base.value || !draft.value || !input.value) return EMPTY_STATUS;
    return valueStatus(base.value, draft.value, input.value, key, invalidKeys.value);
  }
  function allKeys(): ValueKey[] {
    if (!input.value) return [];
    return ["@name" as ValueKey, ...Object.keys(input.value.values).map((name) => `sheetset:${name}` as ValueKey)];
  }
  const dirtyKeys: ComputedRef<ValueKey[]> = computed(() => allKeys().filter((key) => statusOf(key).dirty));
  const pendingKeys: ComputedRef<ValueKey[]> = computed(() => allKeys().filter((key) => statusOf(key).pending));
  const matchedKeys = computed(() => input.value ? filterValueKeys(input.value, search.value, searchMode.value, changedOnly.value, statusOf) : []);
  // 隐藏修改数：未加入草稿、不匹配当前过滤且不是暂留活动字段的键数（任务 1 契约口径）。
  // 图纸集名称独立展示且始终可见，永不计入「被隐藏」。
  const hiddenDirtyCount = computed(() => {
    const active = activeKey.value;
    return dirtyKeys.value.filter((key) => key !== "@name" && !matchedKeys.value.includes(key) && key !== active).length;
  });

  // —— 缓冲编辑：错误随编辑清除，属性值只使用字符串（不 trim/转换）——
  function setValue(key: ValueKey, value: string) {
    const buffer = input.value;
    if (!buffer) return;
    if (key === "@name") buffer.name = value;
    else {
      const name = key.slice("sheetset:".length);
      if (name in buffer.values) buffer.values[name] = value;
    }
    if (errors.value[key]) {
      const next = {...errors.value};
      delete next[key];
      errors.value = next;
    }
    if (Object.keys(errors.value).length === 0) summaryError.value = "";
  }
  // 撤回仅回到草稿投影（不是正式基准）
  function revertValue(key: ValueKey) {
    const buffer = input.value;
    const projected = draft.value;
    if (!buffer || !projected) return;
    if (key === "@name") buffer.name = projected.name;
    else {
      const name = key.slice("sheetset:".length);
      if (name in projected.values) buffer.values[name] = projected.values[name];
    }
  }
  // 放弃输入：只清当前输入（回到草稿投影），不动草稿与命令簿
  function discardInput() {
    const projected = draft.value;
    if (!projected) return;
    input.value = {name: projected.name, values: {...projected.values}};
    errors.value = {};
    summaryError.value = "";
    activeKey.value = null;
  }

  // —— 快照生命周期 ——
  function resetSessionState() {
    definitionsCollapsed.value = true;   // 定义折叠
    valuesCollapsed.value = false;       // 值展开
    csvCollapsed.value = false;          // CSV 面板展开
    csvOpen.value = false;               // 导入区关闭
    definitionsQuery.value = "";
    definitionsScope.value = "all";
    definitionsPage.value = 1;
    definitionForm.type = "sheet";
    definitionForm.name = "";
    definitionForm.defaultValue = "";
  }
  function resetBuffers() {
    base.value = null;
    draft.value = null;
    input.value = null;
    invalidKeys.value = new Set();
    errors.value = {};
    summaryError.value = "";
    activeKey.value = null;
    seen = "";
    resetSessionState();
  }
  function rebuild(ws: Workspace, baseWs: Workspace) {
    base.value = createPropertyBuffer(baseWs);
    draft.value = createPropertyBuffer(ws);
    input.value = createPropertyBuffer(ws);
    invalidKeys.value = new Set();
    errors.value = {};
    summaryError.value = "";
    activeKey.value = null;
    resetSessionState();
  }
  // 普通投影变化：采纳草稿投影并保留未加入草稿的本地编辑
  function syncFromProjection() {
    const ws = deps.workspace.value;
    if (!ws) return;
    const nextDraft = createPropertyBuffer(ws);
    const currentInput = input.value;
    const currentDraft = draft.value;
    draft.value = nextDraft;
    if (!currentInput || !currentDraft) {
      input.value = {name: nextDraft.name, values: {...nextDraft.values}};
      return;
    }
    const values: Record<string, string> = {};
    for (const name of Object.keys(nextDraft.values)) {
      values[name] = currentInput.values[name] !== currentDraft.values[name] && currentInput.values[name] !== undefined
        ? currentInput.values[name]
        : nextDraft.values[name];
    }
    input.value = {
      name: currentInput.name !== currentDraft.name ? currentInput.name : nextDraft.name,
      values,
    };
  }
  watch([deps.workspace, deps.baseWorkspace], ([ws, baseWs]) => {
    if (!ws || !baseWs) { resetBuffers(); return; }
    const signature = `${ws.id}:${ws.revision_id}`;
    if (signature !== seen) { seen = signature; rebuild(ws, baseWs); return; }
    syncFromProjection();
  });

  // 删除属性定义使活动值字段进入失效集合（保留输入供核对；整体重算语义，撤销命令后自动解除）
  function invalidateDefinitions(keys: ReadonlySet<PropertyKey>) {
    const buffer = input.value;
    if (!buffer) { invalidKeys.value = new Set(); return; }
    const next = new Set<ValueKey>();
    for (const key of keys) {
      if (!key.startsWith("sheetset:")) continue; // sheet 定义不拥有图纸集值字段
      const name = key.slice("sheetset:".length);
      if (name in buffer.values) next.add(`sheetset:${name}` as ValueKey);
    }
    invalidKeys.value = next;
  }

  // —— 提交：只生成一个完整 update_sheet_set 命令，走既有 submitCommands 权威投影与保存失败重试 ——
  // 不做整段串行：命令在提交开始即同步入栈（与既有 addCommand 语义一致），仅草稿保存由
  // draftSaveQueue 顺序冲刷；并发提交各自等待同一保存队列。
  async function submitValues(): Promise<PropertySubmitResult> {
    return doSubmitValues();
  }
  async function doSubmitValues(): Promise<PropertySubmitResult> {
    const buffer = input.value;
    if (!buffer) return {ok: false, message: t("shell.errors.noWorkspace")};
    let command: ChangeCommand;
    try {
      command = buildSheetSetCommand(buffer, invalidKeys.value);
    } catch {
      return {ok: false, message: t("properties.errors.staleFields")};
    }
    const result = await deps.submitCommands([command], t("shell.commands.updateSheetSet"), "metadata");
    if (result.ok) {
      summaryError.value = "";
      errors.value = {};
    } else {
      summaryError.value = result.message || t("shell.errors.addDraftFailed");
      // 未给字段路径的错误只保留摘要，不编造字段归因
      if (result.fields) {
        const mapped: Partial<Record<ValueKey, string>> = {};
        for (const [field, message] of Object.entries(result.fields)) {
          if (field === "name") mapped["@name"] = message;
          else if (buffer.values[field] !== undefined) mapped[`sheetset:${field}` as ValueKey] = message;
        }
        errors.value = mapped;
      }
    }
    return result;
  }

  // —— 新增属性定义（PLAN-DM-016 任务 6）：表单状态在此，命令簿门禁仍由 App 的 addCommand 执行 ——
  // 名称必填（空文本直接通知错误）；入栈成功清空名称与默认值，失败（如结构分批阻断）保留输入。
  function queuePropertyDefinition() {
    const name = definitionForm.name.trim();
    if (!name) { deps.notifyError(t("properties.errors.propertyNameEmpty")); return; }
    if (deps.addPropertyDefinition({type: definitionForm.type, name, defaultValue: definitionForm.defaultValue})) {
      definitionForm.name = "";
      definitionForm.defaultValue = "";
    }
  }

  // —— 全局输入保护三选一（与图纸页共享同一个 UnsavedInputDialog 实例，由 App 串联）——
  async function guard(next: () => void | Promise<void>): Promise<void> {
    if (guardState.value.open) return;          // 防重入
    // 不等待在途提交：其命令已在栈内，草稿保存/关闭路径会统一冲刷（等待会与被阻断的保存死锁）。
    // 「加入草稿后继续」分支内的 submitValues 会自然排在在途保存之后。
    const prompt = dirtyKeys.value.length > 0 || invalidKeys.value.size > 0;
    if (!prompt) { await next(); return; }
    guardState.value = {open: true, summary: t("properties.guard.summary"), canSave: invalidKeys.value.size === 0};
    const choice = await new Promise<GuardChoice>((resolve) => { guardResolver = resolve; });
    guardState.value.open = false;
    guardResolver = null;
    if (choice === "stay") return;              // 留在此处：不继续 next
    if (choice === "discard") { discardInput(); await next(); return; } // 放弃：只清输入
    const result = await submitValues();        // 加入草稿后继续：等待保存与投影
    if (!result.ok) return;                     // 保存失败不能继续 next
    await next();
  }
  function resolveGuard(choice: GuardChoice) { guardResolver?.(choice); }

  return {
    input, base, draft, invalidKeys, errors, summaryError, guardState,
    dirtyKeys, pendingKeys, hiddenDirtyCount, matchedKeys,
    search, searchMode, changedOnly, activeKey, statusOf,
    definitionsCollapsed, valuesCollapsed, csvCollapsed, csvOpen,
    definitionsQuery, definitionsScope, definitionsPage, definitionForm,
    setValue, revertValue, discardInput, submitValues, queuePropertyDefinition,
    syncFromProjection, invalidateDefinitions, guard, resolveGuard,
  };
}
