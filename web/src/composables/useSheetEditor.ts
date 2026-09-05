// 分页编辑缓冲与全局输入保护（PLAN-DM-015 任务 5/6，SPEC-DM-009 §6.1/§6.2/§6.3）。
// 唯一活动编辑上下文为 null 或 sheet/rename/insert-sheet/insert-subset/bulk 联合分支，
// 每分支保留 workspaceId/revisionId/投影快照/objectId/original/values/errors（类型见 types.ts）。
// sheet 分支在 custom_properties 完整副本上编辑，搜索/翻页只派生视图（不改缓冲）；
// 提交 createCommand.updateSheetProperties(id,{...values}) 覆盖全部属性页，不只当前页。
// rename/insert-sheet/insert-subset 三类操作表单（任务 6）同用一个上下文：
// 字段输入由 SheetOperationForm 直接写入缓冲，本域负责提交（参照 ID → ordinal 映射）、
// 失效校验、成功定位与三选一保护；提交前固定打开时的投影快照，基准变化由 watch 标 invalid。
// guard(next) 统一处理预览/写入/关闭/切换/删除等全局动作：无改动直接继续；
// 有改动三选一「加入草稿后继续/放弃输入/留在此处」，保存失败不能继续 next。
import {computed, nextTick, ref, watch} from "vue";
import type {Ref} from "vue";
import {createCommand} from "../api/contracts";
import type {ChangeCommand, LayoutSource, Workspace} from "../api/contracts";
import {resolveSheetOrdinal, resolveSubsetOrdinal} from "../features/sheets/commands";
import type {
  EditContext, GuardChoice, InsertSheetEditContext, InsertSubsetEditContext,
  ProjectionStamp, PropertyEditContext, RenameEditContext, SheetRef,
  SubmitCommands, SubmitResult,
} from "../features/sheets/types";

export const PROPERTY_PAGE_SIZE = 6;

export type SheetEditorDeps = {
  workspace: Ref<Workspace | null>;
  baseWorkspace: Ref<Workspace | null>;
  commands: Ref<ChangeCommand[]>;
  sheetPropertyNames: Ref<string[]>;
  projectionStamp: Ref<ProjectionStamp | null>;
  refreshSheetProjection: () => Promise<SubmitResult>;
  submitCommands: SubmitCommands;
  // 操作表单成功后定位新增/编辑对象（App 注入 useSheetsWorkspace 的定位/切范围）
  locateSheet?: (sheetId: string) => void;
  selectSubset?: (subsetId: string) => void;
};

export type GuardState = {open: boolean; summary: string; canSave: boolean};

export function useSheetEditor(deps: SheetEditorDeps) {
  const context = ref<EditContext>(null);
  const guardState = ref<GuardState>({open: false, summary: "", canSave: true});
  let guardResolver: ((choice: GuardChoice) => void) | null = null;
  let submitInFlight: Promise<SubmitResult> | null = null;
  let opener: HTMLElement | null = null;

  // —— 派生视图（跨页已修改数 / 是否未加入草稿 / 未提交输入保护判断）——
  const modifiedCount = computed(() => {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return 0;
    return ctx.propertyNames.filter((name) => (ctx.values[name] ?? "") !== (ctx.original[name] ?? "")).length;
  });
  const hasUnsavedChanges = computed(() => {
    const ctx = context.value;
    if (!ctx) return false;
    if (ctx.kind === "sheet") return modifiedCount.value > 0;
    if (ctx.kind === "rename") return ctx.values.title !== ctx.original.title;
    if (ctx.kind === "insert-sheet" || ctx.kind === "insert-subset") return ctx.dirty;
    return false;
  });

  // —— 打开/关闭 ——
  function startSheetEditor(sheetId: string) {
    const current = deps.workspace.value;
    if (!current) return;
    const sheet = current.sheet_set.subsets.flatMap((subset) => subset.sheets).find((item) => item.id === sheetId);
    if (!sheet) return;
    opener = document.activeElement as HTMLElement | null;
    context.value = {
      kind: "sheet",
      workspaceId: current.id,
      revisionId: current.revision_id,
      stamp: deps.projectionStamp.value,
      objectId: sheet.id,
      subject: `图纸 ${sheet.number}`,
      original: {...sheet.custom_properties},
      values: {...sheet.custom_properties},
      errors: {},
      summaryError: "",
      invalid: false,
      propertyNames: [...deps.sheetPropertyNames.value],
      page: 0,
      search: "",
    };
  }
  // 打开另一编辑上下文：有未提交改动先走三选一（同一图纸不重开）
  function openSheetEditor(sheetId: string) {
    const ctx = context.value;
    if (ctx?.kind === "sheet" && ctx.objectId === sheetId && !ctx.invalid) return;
    void guard(async () => { startSheetEditor(sheetId); });
  }
  // 明确丢弃当前缓冲（“取消”/“放弃输入”），归还焦点
  function discard() {
    context.value = null;
    opener?.focus?.();
  }
  function cancel() { discard(); }

  // —— 操作表单打开（任务 6）：单子集范围预填目标，全部范围必须明确选择 ——
  function openRename(subsetId: string) {
    const current = deps.workspace.value;
    if (!current) return;
    const subset = current.sheet_set.subsets.find((item) => item.id === subsetId);
    opener = document.activeElement as HTMLElement | null;
    context.value = {
      kind: "rename",
      workspaceId: current.id,
      revisionId: current.revision_id,
      stamp: deps.projectionStamp.value,
      objectId: subsetId, // 全部图纸范围打开时为空，由表单先选择编辑对象
      subject: subset ? `子集 ${subset.display_name}` : "子集标题编辑",
      original: {title: subset?.title ?? ""},
      values: {title: subset?.title ?? ""},
      errors: {},
      summaryError: "",
      invalid: false,
    };
  }
  function openInsertSheet(targetSubsetId: string) {
    const current = deps.workspace.value;
    if (!current) return;
    const target = targetSubsetId && current.sheet_set.subsets.some((item) => item.id === targetSubsetId)
      ? targetSubsetId : "";
    opener = document.activeElement as HTMLElement | null;
    context.value = {
      kind: "insert-sheet",
      workspaceId: current.id,
      revisionId: current.revision_id,
      stamp: deps.projectionStamp.value,
      objectId: target,
      subject: "新增图纸",
      errors: {},
      summaryError: "",
      invalid: false,
      original: null,
      values: null,
      targetSubsetId: target,
      reference: null,
      count: "1",
      sourceType: "template_layout",
      sourceFile: "",
      sourceLayout: "",
      layoutOptions: [],
      layoutLoading: false,
      layoutError: "",
      layoutManual: false,
      dirty: false,
    };
  }
  function openInsertSubset() {
    const current = deps.workspace.value;
    if (!current) return;
    opener = document.activeElement as HTMLElement | null;
    context.value = {
      kind: "insert-subset",
      workspaceId: current.id,
      revisionId: current.revision_id,
      stamp: deps.projectionStamp.value,
      objectId: "",
      subject: "新建子集",
      errors: {},
      summaryError: "",
      invalid: false,
      original: null,
      values: null,
      referenceSubsetId: "",
      placement: "after",
      title: "",
      initialSheetCount: "1",
      baseTemplateFile: "",
      templateFile: "",
      templateLayout: "",
      layoutOptions: [],
      layoutLoading: false,
      layoutError: "",
      layoutManual: false,
      dirty: false,
    };
  }

  // —— 缓冲编辑（sheet 分支）——
  function setFieldValue(name: string, value: string) {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return;
    ctx.values[name] = value;
    delete ctx.errors[name];
    if (Object.keys(ctx.errors).length === 0) ctx.summaryError = "";
  }
  function setPage(page: number) {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return;
    const query = ctx.search.trim().toLocaleLowerCase();
    const filtered = query ? ctx.propertyNames.filter((name) => name.toLocaleLowerCase().includes(query)) : [...ctx.propertyNames];
    const totalPages = Math.max(1, Math.ceil(filtered.length / PROPERTY_PAGE_SIZE));
    ctx.page = Math.max(0, Math.min(page, totalPages - 1));
  }
  function setSearch(query: string) {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return;
    ctx.search = query;
    ctx.page = 0;
  }
  // 错误摘要跳转到对应页和字段：清搜索、定位属性所在页，焦点由组件在 nextTick 后接管
  function jumpToError(name: string) {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return;
    const index = ctx.propertyNames.findIndex((item) => item === name);
    ctx.search = "";
    ctx.page = index >= 0 ? Math.floor(index / PROPERTY_PAGE_SIZE) : 0;
  }

  // —— 提交全部属性页（不只当前页）——
  async function submit(): Promise<SubmitResult> {
    if (submitInFlight) return submitInFlight;
    submitInFlight = doSubmit();
    try { return await submitInFlight; } finally { submitInFlight = null; }
  }
  async function doSubmit(): Promise<SubmitResult> {
    const ctx = context.value;
    if (!ctx) return {ok: false, message: "没有活动编辑上下文"};
    if (ctx.invalid) return {ok: false, message: "编辑上下文已失效（基准已刷新或对象已消失），禁止提交"};
    switch (ctx.kind) {
      case "sheet": return submitSheet(ctx);
      case "rename": return submitRename(ctx);
      case "insert-sheet": return submitInsertSheet(ctx);
      case "insert-subset": return submitInsertSubset(ctx);
      case "bulk": return {ok: false, message: "该编辑类型尚未接入提交"};
    }
  }
  async function submitSheet(ctx: PropertyEditContext): Promise<SubmitResult> {
    const command = createCommand.updateSheetProperties(ctx.objectId, {...ctx.values});
    const result = await deps.submitCommands([command], "更新图纸属性", "metadata");
    if (result.ok) {
      discard();
    } else {
      ctx.summaryError = result.message || "加入草稿失败";
      // 未给字段路径的错误只保留摘要，不编造字段归因
      if (result.fields) for (const [field, message] of Object.entries(result.fields)) ctx.errors[field] = message;
    }
    return result;
  }
  async function submitRename(ctx: RenameEditContext): Promise<SubmitResult> {
    if (!ctx.objectId) { ctx.summaryError = "请选择要编辑的子集"; return {ok: false, message: "请选择要编辑的子集"}; }
    const title = ctx.values.title.trim();
    if (!title) { ctx.summaryError = "子集标题不能为空"; return {ok: false, message: "子集标题不能为空"}; }
    const result = await deps.submitCommands([createCommand.updateSubsetTitle(ctx.objectId, title)], "更新子集标题", "structural");
    if (!result.ok) { ctx.summaryError = result.message; return result; }
    await nextTick(); // 等权威投影 watch 应用到显示 workspace 后再定位
    deps.selectSubset?.(ctx.objectId);
    discard();
    return result;
  }
  async function submitInsertSheet(ctx: InsertSheetEditContext): Promise<SubmitResult> {
    const workspace = deps.workspace.value;
    if (!workspace) return {ok: false, message: "没有活动工作区"};
    if (!ctx.targetSubsetId) { ctx.summaryError = "请选择目标子集"; return {ok: false, message: "请选择目标子集"}; }
    if (!ctx.reference) { ctx.summaryError = "请选择参照图纸"; return {ok: false, message: "请选择参照图纸"}; }
    const subset = workspace.sheet_set.subsets.find((item) => item.id === ctx.targetSubsetId);
    if (!subset || subset.sheets.length === 0) {
      ctx.summaryError = "当前子集没有可用图纸参照，新增流程不可用";
      return {ok: false, message: "当前子集没有可用图纸参照，新增流程不可用"};
    }
    const count = positiveInteger(ctx.count);
    if (count === null) { ctx.summaryError = "新增图纸数量必须为正整数"; return {ok: false, message: "新增图纸数量必须为正整数"}; }
    // 加入草稿时重新核对：参照已删除/失效则保留表单并要求重选，不静默替换对象
    let ordinal: number;
    try { ordinal = resolveSheetOrdinal(workspace, ctx.reference); }
    catch (e) {
      const message = e instanceof Error ? e.message : "参照图纸已失效，请重新选择";
      ctx.summaryError = message;
      return {ok: false, message};
    }
    let source: LayoutSource;
    if (ctx.sourceType === "existing_snapshot") {
      source = {type: "existing_snapshot", file: "", layout: ""};
    } else {
      if (!ctx.sourceFile.trim() || !ctx.sourceLayout.trim()) {
        ctx.summaryError = "布局模板文件和布局模板名称不能为空";
        return {ok: false, message: "布局模板文件和布局模板名称不能为空"};
      }
      source = {type: "template_layout", file: ctx.sourceFile.trim(), layout: ctx.sourceLayout.trim()};
    }
    // 提交前固定打开时的投影快照；请求/基准变化已由 watch 标 invalid 拦截，不会用旧索引提交
    const beforeIds = new Set(allSheetIds(workspace));
    const command = createCommand.insertSheet({
      target_subset_id: ctx.reference.subsetId,
      ordinal,
      placement: ctx.reference.placement,
      count,
      source,
    });
    const result = await deps.submitCommands([command], "新增图纸", "structural");
    if (!result.ok) { ctx.summaryError = result.message; return result; }
    // 成功：从权威派生结果取得新增 ID 并定位（不从计数拼造）；原筛选保留，隐藏目标由 locateSheet 提示
    await nextTick();
    const after = deps.workspace.value;
    const newIds = (after ? allSheetIds(after) : []).filter((id) => !beforeIds.has(id));
    const targetId = newIds[0];
    if (targetId) deps.locateSheet?.(targetId);
    discard();
    return result;
  }
  async function submitInsertSubset(ctx: InsertSubsetEditContext): Promise<SubmitResult> {
    const workspace = deps.workspace.value;
    if (!workspace) return {ok: false, message: "没有活动工作区"};
    const title = ctx.title.trim();
    if (!title) { ctx.summaryError = "子集标题不能为空"; return {ok: false, message: "子集标题不能为空"}; }
    const count = positiveInteger(ctx.initialSheetCount);
    if (count === null) { ctx.summaryError = "初始图纸数必须为正整数"; return {ok: false, message: "初始图纸数必须为正整数"}; }
    if (!ctx.baseTemplateFile.trim()) { ctx.summaryError = "基础模板文件不能为空"; return {ok: false, message: "基础模板文件不能为空"}; }
    if (!ctx.templateFile.trim() || !ctx.templateLayout.trim()) {
      ctx.summaryError = "布局模板文件和布局模板名称不能为空";
      return {ok: false, message: "布局模板文件和布局模板名称不能为空"};
    }
    const subsetCount = workspace.sheet_set.subsets.length;
    let ordinal: number;
    if (subsetCount === 0) {
      ordinal = 1; // 空图纸集首个子集沿用序号 1 契约
    } else {
      if (!ctx.referenceSubsetId) { ctx.summaryError = "请选择参照子集"; return {ok: false, message: "请选择参照子集"}; }
      try { ordinal = resolveSubsetOrdinal(workspace, ctx.referenceSubsetId); }
      catch (e) {
        const message = e instanceof Error ? e.message : "参照子集已失效，请重新选择";
        ctx.summaryError = message;
        return {ok: false, message};
      }
    }
    const beforeIds = new Set(workspace.sheet_set.subsets.map((item) => item.id));
    const command = createCommand.insertSubset({
      ordinal,
      placement: ctx.placement,
      title,
      initial_sheet_count: count,
      base_template_file: ctx.baseTemplateFile.trim(),
      source: {type: "template_layout", file: ctx.templateFile.trim(), layout: ctx.templateLayout.trim()},
    });
    const result = await deps.submitCommands([command], "新建子集", "structural");
    if (!result.ok) { ctx.summaryError = result.message; return result; }
    await nextTick();
    const after = deps.workspace.value;
    const newIds = (after?.sheet_set.subsets ?? []).map((item) => item.id).filter((id) => !beforeIds.has(id));
    const targetId = newIds[0];
    if (targetId) deps.selectSubset?.(targetId);
    discard();
    return result;
  }

  // —— 全局输入保护（SPEC-DM-009 §6.2 三选一）——
  async function guard(next: () => void | Promise<void>): Promise<void> {
    if (guardState.value.open) return;          // 防重入
    if (submitInFlight) await submitInFlight;   // 保存中切换：等保存完成再判断
    // 等待保存期间另一 guard 已打开模态：丢弃本次续延（避免后者覆盖 guardResolver 丢弃前者）
    if (guardState.value.open) return;
    const ctx = context.value;
    const prompt = Boolean(ctx) && (hasUnsavedChanges.value || ctx!.invalid);
    if (!prompt) { await next(); return; }
    guardState.value = {open: true, summary: describe(ctx!), canSave: !ctx!.invalid};
    const choice = await new Promise<GuardChoice>((resolve) => { guardResolver = resolve; });
    guardState.value.open = false;
    guardResolver = null;
    if (choice === "stay") return;              // 留在此处：不继续 next
    if (choice === "discard") { discard(); await next(); return; } // 放弃输入：明确清空缓冲
    const result = await submit();              // 加入草稿后继续：等待草稿持久化与投影成功
    if (!result.ok) return;                     // 保存失败不能继续 next
    await next();
  }
  function resolveGuard(choice: GuardChoice) { guardResolver?.(choice); }
  function describe(ctx: Exclude<EditContext, null>): string {
    return ctx.kind === "sheet" ? `${ctx.subject} 属性编辑` : `${ctx.subject} 编辑`;
  }

  // —— 基准刷新/对象消失：标记失效，保留可见输入供核对，禁止提交 ——
  watch([deps.workspace, deps.baseWorkspace], () => {
    const ctx = context.value;
    if (!ctx || ctx.invalid) return;
    const current = deps.workspace.value;
    if (!current || current.revision_id !== ctx.revisionId) { ctx.invalid = true; return; }
    if (ctx.kind === "sheet") {
      const exists = current.sheet_set.subsets.some((subset) => subset.sheets.some((sheet) => sheet.id === ctx.objectId));
      if (!exists) ctx.invalid = true;
    } else if (ctx.kind === "rename") {
      if (ctx.objectId && !current.sheet_set.subsets.some((item) => item.id === ctx.objectId)) ctx.invalid = true;
    } else if (ctx.kind === "insert-sheet") {
      // 目标子集已消失时提交无意义 → 标失效；参照图纸消失但目标仍在 → 保留表单，提交时重校验要求重选
      if (ctx.targetSubsetId && !current.sheet_set.subsets.some((item) => item.id === ctx.targetSubsetId)) ctx.invalid = true;
    }
    // insert-subset：参照子集失效不标 invalid（提交时重校验并保留表单要求重选）
  });

  // 关闭/重开工作区时清空本域状态（不在此清除失效缓冲：基准刷新由 watch 标记失效并保留输入）
  function reset() {
    context.value = null;
    guardState.value = {open: false, summary: "", canSave: true};
    guardResolver = null;
  }

  return {
    context, guardState, hasUnsavedChanges, modifiedCount,
    openSheetEditor, startSheetEditor, openRename, openInsertSheet, openInsertSubset,
    discard, cancel,
    setFieldValue, setPage, setSearch, jumpToError,
    submit, guard, resolveGuard, reset,
  };
}

// 供组件/测试引用的上下文类型辅助：从联合中提取 sheet 分支
export type SheetEditorContext = PropertyEditContext;
// 操作表单上下文联合（排除 sheet/bulk）：SheetOperationForm 渲染对象
export type OperationContext = RenameEditContext | InsertSheetEditContext | InsertSubsetEditContext;

function positiveInteger(value: string): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}
function allSheetIds(workspace: Workspace): string[] {
  return workspace.sheet_set.subsets.flatMap((subset) => subset.sheets.map((sheet) => sheet.id));
}
