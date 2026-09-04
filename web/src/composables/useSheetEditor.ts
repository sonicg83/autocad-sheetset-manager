// 分页编辑缓冲与全局输入保护（PLAN-DM-015 任务 5，SPEC-DM-009 §6.1/§6.2）。
// 唯一活动编辑上下文为 null 或 sheet/rename/insert-sheet/insert-subset/bulk 联合分支，
// 每分支保留 workspaceId/revisionId/投影快照/objectId/original/values/errors（类型见 types.ts）。
// sheet 分支在 custom_properties 完整副本上编辑，搜索/翻页只派生视图（不改缓冲）；
// 提交 createCommand.updateSheetProperties(id,{...values}) 覆盖全部属性页，不只当前页。
// guard(next) 统一处理预览/写入/关闭/切换/删除等全局动作：无改动直接继续；
// 有改动三选一「加入草稿后继续/放弃输入/留在此处」，保存失败不能继续 next。
// 基准刷新或对象消失：标记上下文失效，保留可见输入供核对，禁止提交到新基准或其它对象。
import {computed, ref, watch} from "vue";
import type {Ref} from "vue";
import {createCommand} from "../api/contracts";
import type {ChangeCommand, Workspace} from "../api/contracts";
import type {
  EditContext, GuardChoice, ProjectionStamp, PropertyEditContext,
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
};

export type GuardState = {open: boolean; summary: string; canSave: boolean};

export function useSheetEditor(deps: SheetEditorDeps) {
  const context = ref<EditContext>(null);
  const guardState = ref<GuardState>({open: false, summary: "", canSave: true});
  let guardResolver: ((choice: GuardChoice) => void) | null = null;
  let submitInFlight: Promise<SubmitResult> | null = null;
  let opener: HTMLElement | null = null;

  // —— 派生视图（跨页已修改数 / 是否未加入草稿 / 分页视图）——
  const modifiedCount = computed(() => {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return 0;
    return ctx.propertyNames.filter((name) => (ctx.values[name] ?? "") !== (ctx.original[name] ?? "")).length;
  });
  const hasUnsavedChanges = computed(() => modifiedCount.value > 0);
  // 搜索/翻页只派生展示：在完整副本上过滤与切片，不丢输入
  const sheetView = computed(() => {
    const ctx = context.value;
    if (!ctx || ctx.kind !== "sheet") return null;
    const query = ctx.search.trim().toLocaleLowerCase();
    const filtered = query ? ctx.propertyNames.filter((name) => name.toLocaleLowerCase().includes(query)) : [...ctx.propertyNames];
    const totalPages = Math.max(1, Math.ceil(filtered.length / PROPERTY_PAGE_SIZE));
    const page = Math.min(ctx.page, totalPages - 1);
    return {
      filteredNames: filtered,
      totalPages,
      page,
      pageNames: filtered.slice(page * PROPERTY_PAGE_SIZE, (page + 1) * PROPERTY_PAGE_SIZE),
    };
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
      added: false,
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
    const view = sheetView.value;
    if (!view) return;
    ctx.page = Math.max(0, Math.min(page, view.totalPages - 1));
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
    if (ctx.kind !== "sheet") return {ok: false, message: "该编辑类型尚未接入提交"};
    if (ctx.invalid) return {ok: false, message: "编辑上下文已失效（基准已刷新或对象已消失），禁止提交"};
    const command = createCommand.updateSheetProperties(ctx.objectId, {...ctx.values});
    const result = await deps.submitCommands([command], "更新图纸属性", "metadata");
    if (result.ok) {
      discard();
    } else {
      ctx.added = true;
      ctx.summaryError = result.message || "加入草稿失败";
      // 未给字段路径的错误只保留摘要，不编造字段归因
      if (result.fields) for (const [field, message] of Object.entries(result.fields)) ctx.errors[field] = message;
    }
    return result;
  }

  // —— 全局输入保护（SPEC-DM-009 §6.2 三选一）——
  async function guard(next: () => void | Promise<void>): Promise<void> {
    if (guardState.value.open) return;          // 防重入
    if (submitInFlight) await submitInFlight;   // 保存中切换：等保存完成再判断
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
    }
  });

  // 关闭/重开工作区时清空本域状态（不在此清除失效缓冲：基准刷新由 watch 标记失效并保留输入）
  function reset() {
    context.value = null;
    guardState.value = {open: false, summary: "", canSave: true};
    guardResolver = null;
  }

  return {
    context, guardState, hasUnsavedChanges, modifiedCount, sheetView,
    openSheetEditor, startSheetEditor, discard, cancel,
    setFieldValue, setPage, setSearch, jumpToError,
    submit, guard, resolveGuard, reset,
  };
}

// 供组件/测试引用的上下文类型辅助：从联合中提取 sheet 分支
export type SheetEditorContext = PropertyEditContext;
