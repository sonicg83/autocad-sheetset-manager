// @vitest-environment happy-dom
// Task 11 第 11b 轮：壳层导航组合层（页签 / 任务浮层）的单测。
//
// 为什么需要这组单测（Step 2 的原意）：11b 是**纯搬迁**——把 `App.vue` 里的页签与浮层导航搬进
// `useShellNavigation`。E2E 能覆盖端到端行为，但搬错时最难发现的恰恰是**组合语义**：
// ① 页签激活态**由既有 `useShellTabs` 驱动**（动态列表里激活项被移除时回退到首个核心页签）——
//    若本模块自己另写一份页签列表状态，E2E 仍可能全绿，而这条语义会静默丢失；
// ② 图纸目录页未保存草稿闸门的**三种走法**（重复点当前页签不重开闸门 / 无草稿同步切换 / 有草稿走闸门）
//    是 PLAN-DM-020 与 SPEC-DM-012 §3.2 的既定语义，搬动时必须逐条保住。
// 本组用例故意不 mock `useShellTabs`：要固定的正是「组合它」这一事实本身。
import {computed, nextTick, ref} from "vue";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {useShellNavigation, type ExtensionPageLike, type ShellNavigationDeps} from "./useShellNavigation";
import {useDraftGuards, type DraftGuardsDeps, type EditorApi, type PropertiesApi, type SheetsFilterApi} from "./useDraftGuards";
import {useWorkspaceLifecycle, type WorkspaceLifecycleOptions} from "./useWorkspaceLifecycle";
import {useWorkspaceCommands, type PreviewContext, type WorkspaceCommandsOptions} from "./useWorkspaceCommands";
import {createCommand} from "../api/contracts";
import {ApiError} from "../api/client";
import type {ChangeCommand, Sheet, Workspace} from "../api/contracts";

// 11c 的草稿栈测试要控制草稿读写的 HTTP 结果（尤其 DRAFT_CONFLICT），故只 mock API client。
// `./drafts` 的投影实现**不 mock**：搬运要求沿用既有投影，这也正是「组合而非复制」的守卫点。
const apiRequest = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => {
  class ApiError extends Error {
    code: string;
    fields?: Record<string, string>;
    constructor(code: string, message: string, fields?: Record<string, string>) {
      super(message);
      this.code = code;
      this.fields = fields;
    }
  }
  return {request: apiRequest, ApiError};
});

function makeDeps(overrides: Partial<ShellNavigationDeps> = {}): ShellNavigationDeps {
  return {
    workspace: ref<{id: string} | null>(null),
    extensionPages: computed<readonly ExtensionPageLike[]>(() => []),
    isRestoreExecuting: ref(false),
    isWorkspaceLoading: ref(false),
    // 宿主注入 i18n 与域动作：本模块不自行取 i18n，也不依赖 useRestore/useSheetCatalog
    t: (key: string) => key,
    loadRevisions: vi.fn(async () => {}),
    catalogNavigationNeeded: vi.fn(() => false),
    guardCatalogPage: vi.fn(async (next: () => void | Promise<void>) => {
      await next();
      return "continue";
    }),
    ...overrides,
  };
}

describe("useShellNavigation：页签导航", () => {
  it("无工作区时只有三个核心页签，初始激活为 sheets", () => {
    const nav = useShellNavigation(makeDeps());
    expect(nav.tabDescriptors.value.map(d => d.id)).toEqual(["sheets", "properties", "revisions"]);
    expect(nav.tabDescriptors.value.map(d => d.number)).toEqual(["①", "②", "③"]);
    expect(nav.tabDescriptors.value.every(d => d.source === "core")).toBe(true);
    expect(nav.active.value).toBe("sheets");
  });

  it("有工作区时把扩展页面追加为核心页签之后的扩展页签", () => {
    const nav = useShellNavigation(
      makeDeps({
        workspace: ref<{id: string} | null>({id: "w1"}),
        extensionPages: computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "extensions.sheetCatalog.title"}}]),
      }),
    );
    expect(nav.tabDescriptors.value.map(d => d.id)).toEqual(["sheets", "properties", "revisions", "ext.sheetCatalog"]);
    const ext = nav.tabDescriptors.value[3]!;
    expect(ext.source).toBe("extension");
    expect(ext.number).toBeUndefined();
    // 扩展页签的 label 是宿主 i18n 渲染后的文本（name_key 经注入的 t 翻译）
    expect(ext.label).toBe("extensions.sheetCatalog.title");
  });

  it("恢复执行中或工作区加载中：修订历史与扩展页签停用，核心前两项不受影响", async () => {
    const isRestoreExecuting = ref(false);
    const nav = useShellNavigation(
      makeDeps({
        workspace: ref<{id: string} | null>({id: "w1"}),
        extensionPages: computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "k"}}]),
        isRestoreExecuting,
      }),
    );
    expect(nav.tabDescriptors.value.map(d => Boolean(d.disabled))).toEqual([false, false, false, false]);
    isRestoreExecuting.value = true;
    await nextTick();
    expect(nav.tabDescriptors.value.map(d => Boolean(d.disabled))).toEqual([false, false, true, true]);
  });

  it("动态列表移除激活项时回退到首个核心页签（组合 useShellTabs 的可观测后果）", async () => {
    const workspace = ref<{id: string} | null>({id: "w1"});
    const extensionPages = computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "k"}}]);
    const nav = useShellNavigation(makeDeps({workspace, extensionPages}));
    nav.selectTab("ext.sheetCatalog");
    await nextTick();
    expect(nav.active.value).toBe("ext.sheetCatalog");
    // 工作区关闭 ⇒ 扩展页签消失 ⇒ 激活项不能在列表里“悬空”
    workspace.value = null;
    await nextTick();
    expect(nav.active.value).toBe("sheets");
  });

  it("切到修订历史会重新加载列表；切到其它页签不会", () => {
    const loadRevisions = vi.fn(async () => {});
    const nav = useShellNavigation(makeDeps({loadRevisions}));
    nav.selectTab("revisions");
    expect(nav.active.value).toBe("revisions");
    expect(loadRevisions).toHaveBeenCalledTimes(1);
    nav.selectTab("properties");
    expect(nav.active.value).toBe("properties");
    expect(loadRevisions).toHaveBeenCalledTimes(1);
  });

  it("重复点击当前页签不重开闸门，但修订历史页签仍重新加载列表", () => {
    const catalogNavigationNeeded = vi.fn(() => true);
    const loadRevisions = vi.fn(async () => {});
    const nav = useShellNavigation(makeDeps({catalogNavigationNeeded, loadRevisions}));
    nav.selectTab("sheets"); // 初始即 sheets：重复点击
    expect(catalogNavigationNeeded).not.toHaveBeenCalled();
    expect(nav.active.value).toBe("sheets");
    nav.selectTab("revisions"); // 目标=revisions：先非重复分支
    expect(catalogNavigationNeeded).toHaveBeenCalledTimes(1);
  });

  it("无未保存草稿时同步切换；有草稿时经闸门切换", async () => {
    const noDraft = makeDeps();
    const navA = useShellNavigation(noDraft);
    navA.selectTab("properties");
    expect(navA.active.value).toBe("properties");
    expect(noDraft.guardCatalogPage).not.toHaveBeenCalled();

    const withDraft = makeDeps({catalogNavigationNeeded: vi.fn(() => true)});
    const navB = useShellNavigation(withDraft);
    navB.selectTab("properties");
    // 有草稿：交给闸门决定，闸门未 resolve 前不切换
    expect(withDraft.guardCatalogPage).toHaveBeenCalledTimes(1);
    await nextTick();
    expect(navB.active.value).toBe("properties");
  });

  it("方向键：无草稿时同步跟随；有草稿时先回退激活项再走闸门（取消则不留在错页签）", async () => {
    const noDraft = makeDeps();
    const navA = useShellNavigation(noDraft);
    navA.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    expect(navA.active.value).toBe("properties");

    // 有草稿且用户【取消】：闸门不执行 next()。此时若没先回退 active，UI 会留在错页签。
    const cancelled = makeDeps({
      catalogNavigationNeeded: vi.fn(() => true),
      guardCatalogPage: vi.fn(async (_next: () => void | Promise<void>) => "cancel"),
    });
    const navB = useShellNavigation(cancelled);
    navB.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    expect(navB.active.value).toBe("sheets");
    expect(cancelled.guardCatalogPage).toHaveBeenCalledTimes(1);

    // 有草稿且闸门放行：闸门内部才真正切换页签
    const proceed = makeDeps({catalogNavigationNeeded: vi.fn(() => true)});
    const navC = useShellNavigation(proceed);
    navC.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    await nextTick();
    expect(proceed.guardCatalogPage).toHaveBeenCalledTimes(1);
    expect(navC.active.value).toBe("properties");
  });
});

describe("useShellNavigation：任务浮层", () => {
  it("openOverlay 同时设置页签与展开态；resetOverlay 复位为 prog/收起", () => {
    const nav = useShellNavigation(makeDeps());
    expect(nav.overlayOpen.value).toBe(false);
    expect(nav.overlayTab.value).toBe("prog");
    nav.openOverlay("prev");
    expect(nav.overlayOpen.value).toBe(true);
    expect(nav.overlayTab.value).toBe("prev");
    nav.resetOverlay();
    expect(nav.overlayOpen.value).toBe(false);
    expect(nav.overlayTab.value).toBe("prog");
  });

  it("jumpOverlay 只放行三个合法页签（非法值忽略且不改动状态）", () => {
    const nav = useShellNavigation(makeDeps());
    nav.openOverlay("prev");
    nav.jumpOverlay("diagnostics-typo");
    expect(nav.overlayOpen.value).toBe(true);
    expect(nav.overlayTab.value).toBe("prev");
    nav.jumpOverlay("diag");
    expect(nav.overlayTab.value).toBe("diag");
  });
});

// —— 11c：未提交输入与草稿门禁（草稿栈 + 三选一 guard）——
//
// 为什么需要这组单测：11c 把 `App.vue` 的草稿域整体搬进 `useDraftGuards`。其中多数语义在 E2E 里
// 要「造真实草稿并制造版本冲突」才可见，单测把它们钉成可核验契约：
// ① 草稿栈投影语义（撤销/重做/移除与游标的关系、新动作截断重做尾巴）；
// ② `DRAFT_CONFLICT` 引发的只读降级（草稿 stale、命令清空、错误文案）；
// ③ 图纸页/属性页两个输入域的过闸顺序与「留在此处」终止；
// ④ 范围改变隐藏当前编辑对象时「先还原快照、再三选一」的次序。
function makeEditor(overrides: Partial<EditorApi> = {}): EditorApi {
  return {
    // 每个强转只针对单个成员、转到该成员的真实类型；其余成员仍受结构检查
    context: ref(null) as EditorApi["context"],
    hasUnsavedChanges: computed(() => false),
    guard: vi.fn(async (next: () => void | Promise<void>) => { await next(); }),
    resolveGuard: vi.fn(),
    guardState: ref({open: false, summary: "", canSave: true}) as EditorApi["guardState"],
    ...overrides,
  };
}

function makeProperties(overrides: Partial<PropertiesApi> = {}): PropertiesApi {
  return {
    guard: vi.fn(async (next: () => void | Promise<void>) => { await next(); }),
    resolveGuard: vi.fn(),
    guardState: ref({open: false, summary: "", canSave: true}) as PropertiesApi["guardState"],
    ...overrides,
  };
}

function makeSheets(overrides: Partial<SheetsFilterApi> = {}): SheetsFilterApi {
  return {
    filteredRows: rows([]),
    snapshotState: vi.fn(() => ({})),
    restoreState: vi.fn(),
    ...overrides,
  } as unknown as SheetsFilterApi;
}

function makeDraftDeps(overrides: Partial<DraftGuardsDeps> = {}): DraftGuardsDeps {
  return {
    workspace: ref<Workspace | null>({id: "w1", revision_id: "r1"} as unknown as Workspace),
    baseWorkspace: ref<Workspace | null>(null),
    error: ref(""),
    t: (key: string) => key,
    cloneJson: <T,>(value: T): T => JSON.parse(JSON.stringify(value)),
    invalidatePreview: vi.fn(),
    refreshSheetProjection: vi.fn(async () => ({ok: true})),
    getActive: () => "sheets",
    getEditor: () => makeEditor(),
    getProperties: () => makeProperties(),
    getSheets: () => makeSheets(),
    reloadWorkspace: vi.fn(async () => {}),
    confirmAction: vi.fn(async () => true),
    ...overrides,
  };
}

/** 测试用命令夹具：类型字段由调用方给出，其余按各命令自身字段补。 */
const cmd = (type: ChangeCommand["type"], extra: Record<string, unknown> = {}): ChangeCommand => ({type, ...extra} as ChangeCommand);

// mock 的 ApiError 构造签名（code, message）与真实类的（HTTP status + body）不同，
// 而模块靠 `instanceof` 判定 DRAFT_CONFLICT，因此必须用 mock 类构造；此处只强转构造器。
const MockApiError = ApiError as unknown as new (code: string, message: string) => ApiError;
const makeApiError = (code: string, message: string): ApiError => new MockApiError(code, message);

/** 图纸行夹具：本组用例只用到 `row.sheet.id`（可见性判定），其余字段不影响被测行为。 */
const rows = (ids: string[]): SheetsFilterApi["filteredRows"] => computed(() => ids.map(id => ({sheet: {id}})) as unknown as SheetsFilterApi["filteredRows"]["value"]);

/** 触发一次 DRAFT_CONFLICT，使草稿进入 stale 只读降级。 */
async function makeConflicted(deps: DraftGuardsDeps) {
  const guards = useDraftGuards(deps);
  guards.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
  apiRequest.mockRejectedValueOnce(makeApiError("DRAFT_CONFLICT", "草稿版本冲突"));
  await guards.pendingDraftSave();
  return guards;
}

describe("useDraftGuards：草稿栈语义", () => {
  beforeEach(() => { apiRequest.mockReset(); apiRequest.mockResolvedValue({draft: {version: 2}}); });

  it("入栈使游标到栈顶并投影出命令；撤销回退、重做恢复", () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    expect(g.commands.value).toEqual([]);
    expect(g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural")).toBe(true);
    expect(g.draftCursor.value).toBe(1);
    expect(g.draftActions.value).toHaveLength(1);
    expect(g.commands.value.map(c => c.type)).toEqual(["delete_sheet"]);
    g.undoDraft();
    expect(g.draftCursor.value).toBe(0);
    // 游标回到 0：投影按游标截断，命令为空（草稿栈仍在，撤销不等于丢弃）
    expect(g.commands.value).toEqual([]);
    expect(g.draftActions.value).toHaveLength(1);
    g.redoDraft();
    expect(g.draftCursor.value).toBe(1);
    expect(g.commands.value.map(c => c.type)).toEqual(["delete_sheet"]);
  });

  it("撤销后再入栈会截断重做尾巴（不保留被撤销动作）", () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    g.addCommand(cmd("delete_sheet", {sheet_id: "s2"}), "structural");
    g.undoDraft();
    g.addCommand(cmd("delete_sheet", {sheet_id: "s3"}), "structural");
    expect(g.draftActions.value).toHaveLength(2);
    expect(g.draftCursor.value).toBe(2);
    expect(g.commands.value.map(c => (c as {sheet_id?: string}).sheet_id)).toEqual(["s1", "s3"]);
  });

  it("撤销/重做在栈边界与 stale 时是空操作", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    expect(() => g.undoDraft()).not.toThrow();
    expect(g.draftCursor.value).toBe(0);
    // 冲突后的草稿转只读：游标保持冲突前的值，undo/redo 都不再改动它
    const g2 = await makeConflicted(deps);
    const cursorAtConflict = g2.draftCursor.value;
    expect(g2.draftStale.value).toBe(true);
    g2.redoDraft();
    expect(g2.draftCursor.value).toBe(cursorAtConflict);
    g2.undoDraft();
    expect(g2.draftCursor.value).toBe(cursorAtConflict);
    expect(g2.commands.value).toEqual([]);
  });

  it("移除活动动作时游标减一；移除栈尾动作时游标不变并按长度收敛", () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    g.addCommand(cmd("delete_sheet", {sheet_id: "s2"}), "structural");
    g.undoDraft();
    // 移除被撤销的那条（index=1 ≥ cursor=1，不算活动）→ 游标保持 1
    g.removeDraftAction(1);
    expect(g.draftActions.value).toHaveLength(1);
    expect(g.draftCursor.value).toBe(1);
    // 移除活动项（index=0 < cursor=1）→ 游标减一
    g.addCommand(cmd("delete_sheet", {sheet_id: "s3"}), "structural");
    g.undoDraft();
    g.removeDraftAction(0);
    expect(g.draftCursor.value).toBe(0);
    expect(g.commands.value).toEqual([]);
  });

  it("混批拒绝：结构命令与已有属性定义命令不能共存", () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    expect(g.addCommand(cmd("add_custom_property", {property_type: "sheetset", name: "p1"}), "property")).toBe(true);
    expect(g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural")).toBe(false);
    expect(deps.error.value).toBe("shell.errors.mixedBatches");
    expect(g.draftActions.value).toHaveLength(1);
  });

  it("空批次不入栈", () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    expect(g.addCommandBatch([], {key: "shell.commands.deleteSheet"}, "structural")).toBe(false);
    expect(g.draftActions.value).toEqual([]);
  });

  it("DRAFT_CONFLICT：草稿转 stale、命令清空、保存失败标记与文案就位", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    expect(g.commands.value).toHaveLength(1);
    apiRequest.mockRejectedValueOnce(makeApiError("DRAFT_CONFLICT", "草稿版本冲突"));
    await g.pendingDraftSave();
    expect(g.draftStale.value).toBe(true);
    expect(g.draftStaleReasons.value).toEqual(["DRAFT_VERSION_CONFLICT"]);
    expect(g.commands.value).toEqual([]);
    expect(g.draftSaveFailed.value).toBe(true);
    expect(g.lastDraftError.value?.code).toBe("DRAFT_CONFLICT");
    expect(deps.error.value).toBe("shell.errors.draftConflictOverwrite");
  });

  it("stale 后入栈被拒绝并给出只读提示", async () => {
    const deps = makeDraftDeps();
    const g = await makeConflicted(deps);
    expect(g.addCommand(cmd("delete_sheet", {sheet_id: "s2"}), "structural")).toBe(false);
    expect(deps.error.value).toBe("shell.errors.draftStaleAction");
  });

  it("保存成功推进草稿版本并清除失败标记", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    // 保存排在串行队列上，请求体要等队列推进后才发出（不是入栈即发）
    await g.pendingDraftSave();
    expect(apiRequest).toHaveBeenCalledTimes(1);
    const [url, init] = apiRequest.mock.calls[0]! as [string, {method: string; body: string}];
    expect(url).toBe("/api/workspaces/w1/draft");
    expect(init.method).toBe("PUT");
    // 载荷形状是既有契约：expected_version + cursor + actions 必须齐备
    expect(JSON.parse(init.body)).toMatchObject({schema_version: 1, base_revision_id: "r1", expected_version: 0, cursor: 1});
    expect(g.draftVersion.value).toBe(2);
    expect(g.draftSaveFailed.value).toBe(false);
  });

  it("非冲突的保存失败只置失败标记，不进入 stale", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    apiRequest.mockRejectedValueOnce(new Error("网络中断"));
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    await g.pendingDraftSave();
    expect(g.draftSaveFailed.value).toBe(true);
    expect(g.lastDraftError.value).toBeNull();
    expect(g.draftStale.value).toBe(false);
  });

  it("discardDraft：DELETE 带 expected_version，成功后清空草稿态", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    g.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    await g.pendingDraftSave();
    apiRequest.mockClear();
    await g.discardDraft();
    const [url, init] = apiRequest.mock.calls[0]! as [string, {method: string; body: string}];
    expect(url).toBe("/api/workspaces/w1/draft");
    expect(init.method).toBe("DELETE");
    expect(JSON.parse(init.body)).toEqual({expected_version: 2});
    expect(g.draftActions.value).toEqual([]);
    expect(g.commands.value).toEqual([]);
    expect(g.draftVersion.value).toBe(0);
  });

  it("discardDraft 遇 DRAFT_CONFLICT：转 stale 并给出删除冲突文案", async () => {
    const deps = makeDraftDeps();
    const g = useDraftGuards(deps);
    await g.pendingDraftSave();
    apiRequest.mockRejectedValueOnce(makeApiError("DRAFT_CONFLICT", "草稿版本冲突"));
    await g.discardDraft();
    expect(g.draftStale.value).toBe(true);
    expect(g.draftStaleReasons.value).toEqual(["DRAFT_VERSION_CONFLICT"]);
    expect(deps.error.value).toBe("shell.errors.draftConflictDelete");
  });

  it("reloadAfterDraftConflict：无冲突原因时不确认也不刷新；有冲突且确认时刷新", async () => {
    const reloadWorkspace = vi.fn(async () => {});
    const confirmAction = vi.fn(async () => true);
    const deps = makeDraftDeps({reloadWorkspace, confirmAction});
    const g = useDraftGuards(deps);
    await g.reloadAfterDraftConflict();
    expect(confirmAction).not.toHaveBeenCalled();
    expect(reloadWorkspace).not.toHaveBeenCalled();
    const g2 = await makeConflicted(deps);
    await g2.reloadAfterDraftConflict();
    expect(confirmAction).toHaveBeenCalledTimes(1);
    expect(reloadWorkspace).toHaveBeenCalledWith("w1");
    expect(g2.draftSaveFailed.value).toBe(false);
  });

  it("reloadAfterDraftConflict：用户取消确认则不刷新", async () => {
    const reloadWorkspace = vi.fn(async () => {});
    const deps = makeDraftDeps({reloadWorkspace, confirmAction: vi.fn(async () => false)});
    const g = await makeConflicted(deps);
    await g.reloadAfterDraftConflict();
    expect(reloadWorkspace).not.toHaveBeenCalled();
  });
});

describe("useDraftGuards：未提交输入过闸", () => {
  beforeEach(() => { apiRequest.mockReset(); apiRequest.mockResolvedValue({draft: {version: 2}}); });

  it("先处理当前主标签：属性页激活时属性域先过闸，否则图纸域先过闸", async () => {
    const order: string[] = [];
    const editor = makeEditor({guard: vi.fn(async (next: () => void | Promise<void>) => { order.push("editor"); await next(); })});
    const properties = makeProperties({guard: vi.fn(async (next: () => void | Promise<void>) => { order.push("properties"); await next(); })});
    const deps = makeDraftDeps({getActive: () => "properties", getEditor: () => editor, getProperties: () => properties});
    const g = useDraftGuards(deps);
    await g.guardAllInputs(() => { order.push("next"); });
    expect(order).toEqual(["properties", "editor", "next"]);
    order.length = 0;
    const deps2 = makeDraftDeps({getActive: () => "sheets", getEditor: () => editor, getProperties: () => properties});
    await useDraftGuards(deps2).guardAllInputs(() => { order.push("next"); });
    expect(order).toEqual(["editor", "properties", "next"]);
  });

  it("任一步「留在此处」终止 next", async () => {
    const next = vi.fn();
    // 第一域不调用 next（等价于用户选择留在此处）
    const editor = makeEditor({guard: vi.fn(async () => {})});
    const properties = makeProperties();
    const deps = makeDraftDeps({getActive: () => "sheets", getEditor: () => editor, getProperties: () => properties});
    await useDraftGuards(deps).guardAllInputs(next);
    expect(next).not.toHaveBeenCalled();
    expect(properties.guard).not.toHaveBeenCalled();
  });

  it("共享三选一状态取当前打开者：属性域打开时优先", () => {
    const editor = makeEditor();
    const properties = makeProperties();
    const deps = makeDraftDeps({getEditor: () => editor, getProperties: () => properties});
    const g = useDraftGuards(deps);
    expect(g.sharedGuardState.value).toBe(editor.guardState.value);
    properties.guardState.value = {open: true, summary: "属性页有未提交输入", canSave: true};
    expect(g.sharedGuardState.value).toBe(properties.guardState.value);
  });

  it("resolveSharedGuard 同时通知两个输入域（同一实例不叠加模态）", () => {
    const editor = makeEditor();
    const properties = makeProperties();
    const deps = makeDraftDeps({getEditor: () => editor, getProperties: () => properties});
    useDraftGuards(deps).resolveSharedGuard("discard");
    expect(editor.resolveGuard).toHaveBeenCalledWith("discard");
    expect(properties.resolveGuard).toHaveBeenCalledWith("discard");
  });

  it("无未保存输入时范围改变直接生效（不还原快照、不经 guard）", () => {
    const sheets = makeSheets();
    const editor = makeEditor();
    const deps = makeDraftDeps({getSheets: () => sheets, getEditor: () => editor});
    const apply = vi.fn();
    useDraftGuards(deps).runScopeChange(apply);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(sheets.snapshotState).not.toHaveBeenCalled();
    expect(editor.guard).not.toHaveBeenCalled();
  });

  it("有未保存输入但对象仍可见：保留改变结果，不还原也不经 guard", () => {
    const sheets = makeSheets({filteredRows: rows(["s1"])});
    const editor = makeEditor({
      hasUnsavedChanges: computed(() => true),
      context: ref({kind: "sheet", objectId: "s1"}) as EditorApi["context"],
    });
    const deps = makeDraftDeps({getSheets: () => sheets, getEditor: () => editor});
    const apply = vi.fn();
    useDraftGuards(deps).runScopeChange(apply);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(sheets.restoreState).not.toHaveBeenCalled();
    expect(editor.guard).not.toHaveBeenCalled();
  });

  it("范围改变隐藏当前编辑对象：先还原快照、再三选一", () => {
    const sheets = makeSheets({filteredRows: rows([])});
    const editor = makeEditor({
      hasUnsavedChanges: computed(() => true),
      context: ref({kind: "sheet", objectId: "s1"}) as EditorApi["context"],
    });
    const deps = makeDraftDeps({getSheets: () => sheets, getEditor: () => editor});
    const apply = vi.fn();
    useDraftGuards(deps).runScopeChange(apply);
    expect(sheets.snapshotState).toHaveBeenCalledTimes(1);
    expect(sheets.restoreState).toHaveBeenCalledWith({});
    expect(editor.guard).toHaveBeenCalledTimes(1);
  });

  it("guardedFilter 返回的包装器经同一条范围保护路径", () => {
    const sheets = makeSheets({filteredRows: rows([])});
    const editor = makeEditor({
      hasUnsavedChanges: computed(() => true),
      context: ref({kind: "sheet", objectId: "s1"}) as EditorApi["context"],
    });
    const deps = makeDraftDeps({getSheets: () => sheets, getEditor: () => editor});
    const target = ref("");
    const guarded = useDraftGuards(deps).guardedFilter((value: string) => { target.value = value; });
    guarded("abc");
    // 被隐藏 → 先还原快照，改值本身已生效（与 v-model 语义一致），但要走 guard
    expect(target.value).toBe("abc");
    expect(sheets.restoreState).toHaveBeenCalledTimes(1);
    expect(editor.guard).toHaveBeenCalledTimes(1);
  });
});

// —— 11d：工作区生命周期域（打开 / 关闭 / 刷新 + 代次闸门）——

/**
 * 本域测试用**真实** `useDraftGuards` 注入：本域与草稿域的组合关系本身就是被测对象之一
 * （打开前须等保存队列、关闭前须丢弃草稿），故不用手写草稿桩。
 */
function makeLifecycleDeps(overrides: Partial<WorkspaceLifecycleOptions> = {}): WorkspaceLifecycleOptions {
  const workspace = ref<Workspace | null>(null);
  const baseWorkspace = ref<Workspace | null>(null);
  const error = ref("");
  const draft = useDraftGuards(makeDraftDeps({workspace, baseWorkspace, error}));
  return {
    workspace, baseWorkspace, error,
    isWorkspaceLoading: ref(false),
    isRestoreExecuting: ref(false),
    draft,
    cloneJson: <T,>(value: T): T => JSON.parse(JSON.stringify(value)),
    invalidatePreview: vi.fn(),
    t: (key: string) => key,
    confirmAction: vi.fn(async () => true),
    invalidateLayoutReads: vi.fn(),
    resetSheetsWorkspace: vi.fn(),
    reloadExtensions: vi.fn(),
    clearExtensions: vi.fn(),
    loadRevisions: vi.fn(),
    invalidateRevisionState: vi.fn(),
    invalidateJobMonitor: vi.fn(),
    resetOverlay: vi.fn(),
    resetEditor: vi.fn(),
    invalidateCsvPreview: vi.fn(),
    isSettingsOpen: () => false,
    getActive: () => "sheets",
    ...overrides,
  };
}

/** 打开流程的两个响应：`POST /api/workspaces/open` 与随后的 `GET /api/workspaces/:id/draft`。 */
function mockOpenFlow(id = "w1", draftEnvelope: unknown = {corrupted: false, stale: false, stale_reasons: [], draft: null}) {
  apiRequest.mockImplementation(async (url: string) => {
    if (url === "/api/workspaces/open") return {id, revision_id: "r1"};
    if (url === `/api/workspaces/${id}/draft`) return draftEnvelope;
    throw new Error(`未预期的请求：${url}`);
  });
  return id;
}

const openCalls = () => apiRequest.mock.calls.filter((call) => call[0] === "/api/workspaces/open");

describe("useWorkspaceLifecycle：打开 / 关闭 / 刷新", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({draft: {version: 2}});
  });

  it("打开成功后以 POST 打开并按 dst_path 传参，双快照各自独立克隆", async () => {
    const id = mockOpenFlow();
    const deps = makeLifecycleDeps();
    const lifecycle = useWorkspaceLifecycle(deps);

    await lifecycle.openByPath("/tmp/a.dst");

    expect(apiRequest).toHaveBeenCalledWith("/api/workspaces/open", expect.objectContaining({method: "POST", body: JSON.stringify({dst_path: "/tmp/a.dst"})}));
    expect(deps.workspace.value?.id).toBe(id);
    expect(deps.baseWorkspace.value?.id).toBe(id);
    // 克隆语义：两份快照互不同一（改其中一份不得影响另一份）
    expect(deps.workspace.value).not.toBe(deps.baseWorkspace.value);
    expect(deps.isWorkspaceLoading.value).toBe(false);
    // 打开后仍停留在 sheets 页：不额外拉修订列表
    expect(deps.loadRevisions).not.toHaveBeenCalled();
  });

  it("打开前草稿保存失败 ⇒ 中止且不发打开请求（不静默丢弃未落盘草稿）", async () => {
    const deps = makeLifecycleDeps();
    // 需要有工作区，入栈才会真的排一次保存（无工作区时 scheduleDraftSave 不发请求）
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    // 先挂上拒绝，再入栈：保存排在微任务队列上，入栈后紧接着的 mockRejectedValueOnce 才轮到它
    apiRequest.mockRejectedValueOnce(new Error("network down"));
    deps.draft.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    await deps.draft.pendingDraftSave();
    expect(deps.draft.draftSaveFailed.value).toBe(true);
    apiRequest.mockClear();

    const lifecycle = useWorkspaceLifecycle(deps);
    await lifecycle.openByPath("/tmp/a.dst");

    expect(openCalls()).toHaveLength(0);
    // 中止而非清空：当前工作区保持不变，加载标志回落
    expect(deps.workspace.value?.id).toBe("w1");
    expect(deps.isWorkspaceLoading.value).toBe(false);
  });

  it("恢复执行中拒绝打开并给出文案，且不发任何请求", async () => {
    const deps = makeLifecycleDeps({isRestoreExecuting: ref(true)});
    const lifecycle = useWorkspaceLifecycle(deps);

    await lifecycle.openByPath("/tmp/a.dst");

    expect(deps.error.value).toBe("shell.errors.restoreRunning");
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("loadDraft：无草稿体时清空草稿标记，corrupted 只留标记（照实钤住既有口径）", async () => {
    // ★ 既有口径，**非本次搬运引入**（原 App.vue 同构：`if(!draft){resetDraftState();draftCorrupted=…;return}`）：
    // 服务端给 stale/corrupted 但 `draft` 为 null 时，该分支先 `resetDraftState()` 清空标记后**直接 return**，
    // 不设 `draftStale`/不写错误文案；corrupted 因在 return 前单独赋值而保留标记。
    // 本用例的任务是**钉住搬运前后的行为不变**，因此照实现写断言；该口径是否合理属既有缺口，已在报告登记。
    const staleDeps = makeLifecycleDeps();
    mockOpenFlow("w1", {corrupted: false, stale: true, stale_reasons: ["DRAFT_VERSION_CONFLICT"], draft: null});
    await useWorkspaceLifecycle(staleDeps).openByPath("/tmp/a.dst");
    expect(staleDeps.draft.draftStale.value).toBe(false);
    expect(staleDeps.draft.draftStaleReasons.value).toEqual([]);
    expect(staleDeps.error.value).toBe("");

    const corruptDeps = makeLifecycleDeps();
    mockOpenFlow("w2", {corrupted: true, stale: false, stale_reasons: [], draft: null});
    await useWorkspaceLifecycle(corruptDeps).openByPath("/tmp/b.dst");
    expect(corruptDeps.draft.draftCorrupted.value).toBe(true);
  });

  it("关闭（无未落盘草稿）：不弹确认，清空工作区并重置各域", async () => {
    const deps = makeLifecycleDeps();
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    deps.baseWorkspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    const lifecycle = useWorkspaceLifecycle(deps);

    await lifecycle.closeWorkspace();

    expect(deps.confirmAction).not.toHaveBeenCalled();
    expect(deps.workspace.value).toBeNull();
    expect(deps.baseWorkspace.value).toBeNull();
    expect(deps.resetEditor).toHaveBeenCalledTimes(1);
    expect(deps.resetSheetsWorkspace).toHaveBeenCalledTimes(1);
    expect(deps.invalidateJobMonitor).toHaveBeenCalledWith(true);
    expect(deps.invalidateRevisionState).toHaveBeenCalledTimes(1);
    expect(deps.clearExtensions).toHaveBeenCalledTimes(1);
    expect(deps.invalidateLayoutReads).toHaveBeenCalledTimes(1);
  });

  it("关闭（有草稿）：按不可逆破坏类弹确认并丢弃草稿；取消则保留工作区", async () => {
    const deps = makeLifecycleDeps();
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    deps.draft.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");

    const lifecycle = useWorkspaceLifecycle(deps);
    await lifecycle.closeWorkspace();

    expect(deps.confirmAction).toHaveBeenCalledWith(expect.objectContaining({danger: true, requireCheckbox: true, reversibility: "irreversible"}));
    expect(deps.workspace.value).toBeNull();
    // 丢弃草稿是一次真实 DELETE（不是本地静默清空）
    expect(apiRequest.mock.calls.some((call) => String(call[0]) === "/api/workspaces/w1/draft" && (call[1] as {method?: string})?.method === "DELETE")).toBe(true);

    const cancelledDeps = makeLifecycleDeps({confirmAction: vi.fn(async () => false)});
    cancelledDeps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    cancelledDeps.draft.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
    await useWorkspaceLifecycle(cancelledDeps).closeWorkspace();
    expect(cancelledDeps.workspace.value?.id).toBe("w1");
  });

  it("代次闸门：关闭后迟到的打开响应不得复活工作区", async () => {
    const deps = makeLifecycleDeps();
    let releaseOpen: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => { releaseOpen = resolve; });
    apiRequest.mockImplementation(async (url: string) => {
      if (url === "/api/workspaces/open") return pending;
      if (String(url).endsWith("/draft")) return {corrupted: false, stale: false, stale_reasons: [], draft: null};
      return {draft: {version: 2}};
    });
    const lifecycle = useWorkspaceLifecycle(deps);

    const opening = lifecycle.openByPath("/tmp/a.dst");
    // 必须先等打开流程真正进入「已发起 POST、等响应」的状态：POST 在 beginWorkspaceLoad 之后才发出，
    // 若此时就 close，关闭会先递增代次、随后 beginWorkspaceLoad 再递增，代次反而匹配（这并非被测语义）。
    await vi.waitFor(() => expect(openCalls()).toHaveLength(1));
    await lifecycle.closeWorkspace();
    releaseOpen({id: "w1", revision_id: "r1"});
    await opening;

    expect(deps.workspace.value).toBeNull();
    expect(deps.baseWorkspace.value).toBeNull();
  });

  it("刷新：工作区 id 不匹配直接返回；匹配则重新拉取并更新双快照", async () => {
    const deps = makeLifecycleDeps();
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    const lifecycle = useWorkspaceLifecycle(deps);

    await lifecycle.refreshWorkspace("w2");
    expect(apiRequest).not.toHaveBeenCalled();

    apiRequest.mockImplementation(async (url: string) => {
      if (url === "/api/workspaces/w1") return {id: "w1", revision_id: "r2"};
      if (String(url).endsWith("/draft")) return {corrupted: false, stale: false, stale_reasons: [], draft: null};
      return {draft: {version: 2}};
    });
    await lifecycle.refreshWorkspace("w1");

    expect(deps.workspace.value?.revision_id).toBe("r2");
    expect(deps.baseWorkspace.value?.revision_id).toBe("r2");
    expect(deps.workspace.value).not.toBe(deps.baseWorkspace.value);
  });

  it("草稿冲突后的重载走未过闸门的刷新（钉住根装配的 reloadWorkspace 接线）", async () => {
    // 复刻根装配的接线：草稿域的 reloadWorkspace 指向生命周期域的 doRefreshWorkspace
    let lifecycle: ReturnType<typeof useWorkspaceLifecycle>;
    const deps = makeLifecycleDeps({
      draft: undefined as unknown as WorkspaceLifecycleOptions["draft"],
    });
    const draftDeps = makeDraftDeps({
      workspace: deps.workspace, baseWorkspace: deps.baseWorkspace, error: deps.error,
      reloadWorkspace: (workspaceId) => lifecycle.doRefreshWorkspace(workspaceId),
    });
    draftDeps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    // 冲突必须发生在本用例将要调用的那个实例上：makeConflicted 内部自建 useDraftGuards，取其返回值
    deps.draft = await makeConflicted(draftDeps);
    lifecycle = useWorkspaceLifecycle(deps);

    apiRequest.mockImplementation(async (url: string) => {
      if (url === "/api/workspaces/w1") return {id: "w1", revision_id: "r9"};
      if (String(url).endsWith("/draft")) return {corrupted: false, stale: false, stale_reasons: [], draft: null};
      return {draft: {version: 2}};
    });
    expect(deps.draft.draftStaleReasons.value).toContain("DRAFT_VERSION_CONFLICT");
    const before = apiRequest.mock.calls.length;
    await deps.draft.reloadAfterDraftConflict();

    expect(apiRequest.mock.calls.length).toBeGreaterThan(before);
    expect(apiRequest.mock.calls.some((call) => String(call[0]) === "/api/workspaces/w1")).toBe(true);
    expect(deps.workspace.value?.revision_id).toBe("r9");
  });
});

// ===== Task 11 第 11e 轮：命令/API 编排组合层 =====
// 为什么需要这组单测（Step 2 的原意）：11e 把「页面事件 → 命令/API 编排」搬进 useWorkspaceCommands。
// 三处最容易搬错、而 e2e 未必立刻暴露的语义：
//   ① submitCommands 的**分批规则**（结构变更与属性定义变更不得同批，SPEC-DM-009）与拒绝优先级；
//   ② ActionDock 门禁矩阵（SPEC-DM-006 §6.9）——它是预览/写入的唯一出口，**分支顺序即优先级**；
//   ③ 删除与 CSV 导入在**确认/写入前**必须先过未提交输入闸门，不能静默丢草稿。
// useHotkeys 以 mock 替换：快捷键注册需要组件实例（onMounted），其端到端行为由 e2e 覆盖；
// 此处只钉住「注册了哪几个动作」与各动作的门禁分支。
const hotkeysSpy = vi.hoisted(() => vi.fn());
vi.mock("./useHotkeys", () => ({useHotkeys: hotkeysSpy}));

/** 草稿保存与投影的宽容响应：本组用例关注编排分支，不关注草稿存储细节。 */
function mockDraftSave() {
  apiRequest.mockImplementation(async (url: string) => {
    if (String(url).endsWith("/draft")) return {corrupted: false, stale: false, stale_reasons: [], draft: {version: 1}};
    return {ok: true};
  });
}

function makeCommandsDeps(overrides: Partial<WorkspaceCommandsOptions> = {}): WorkspaceCommandsOptions {
  const workspace = ref<Workspace | null>(null);
  const error = ref("");
  const draft = useDraftGuards(makeDraftDeps({workspace, error}));
  let previewGeneration = 0;
  let layoutReadGeneration = 0;
  return {
    workspace, error,
    preview: ref(null),
    previewContext: ref<PreviewContext | null>(null),
    isPreviewing: ref(false),
    isWorkspaceLoading: ref(false),
    isRestoreExecuting: ref(false),
    cadVersion: ref("2020"),
    t: (key: string) => key,
    confirmAction: vi.fn(async () => true),
    pushToast: vi.fn(),
    cloneJson: <T,>(value: T): T => JSON.parse(JSON.stringify(value)),
    invalidatePreview: vi.fn(),
    nextPreviewGeneration: () => ++previewGeneration,
    currentPreviewGeneration: () => previewGeneration,
    nextLayoutReadGeneration: () => ++layoutReadGeneration,
    currentLayoutReadGeneration: () => layoutReadGeneration,
    draft,
    nav: {openOverlay: vi.fn()},
    getLifecycle: () => ({refreshWorkspace: vi.fn(async () => {})}) as unknown as ReturnType<WorkspaceCommandsOptions["getLifecycle"]>,
    getEditor: () => ({context: ref(null), guard: async (next: () => void | Promise<void>) => {await next()}, discardIfTargeting: vi.fn()}) as unknown as ReturnType<WorkspaceCommandsOptions["getEditor"]>,
    getProperties: () => ({guard: async (next: () => void | Promise<void>) => {await next()}, csvOpen: ref(false)}) as unknown as ReturnType<WorkspaceCommandsOptions["getProperties"]>,
    getSheets: () => ({selectedIds: ref<string[]>([]), allRows: ref([])}) as unknown as ReturnType<WorkspaceCommandsOptions["getSheets"]>,
    getJobMonitor: () => ({job: ref(null), terminal: () => false, watchJob: vi.fn(), invalidateJobMonitor: vi.fn(() => 1), isCurrentJobGeneration: () => true}),
    getRepair: () => ({dstValidation: ref(null), repairWritesDisabled: ref(false)}) as unknown as ReturnType<WorkspaceCommandsOptions["getRepair"]>,
    getCsvImport: () => ({importCsv: vi.fn(async () => {}), invalidateCsvPreview: vi.fn(), csvText: ref(""), csvPreview: ref(null)}),
    setJob: vi.fn(),
    hasShell: ref(false),
    selectAndOpenDst: vi.fn(),
    refreshSheetProjection: vi.fn(async (): Promise<{ok: true}> => ({ok: true})),
    ...overrides,
  };
}

describe("useWorkspaceCommands：提交命令与门禁编排", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    hotkeysSpy.mockReset();
  });

  it("submitCommands：草稿已失效时拒绝，且不发起任何请求（优先级高于分批规则）", async () => {
    const deps = makeCommandsDeps();
    deps.draft.draftStale.value = true;
    const commands = useWorkspaceCommands(deps);

    const result = await commands.submitCommands([], {key: "k"}, "structural");

    expect(result).toEqual({ok: false, message: "shell.errors.draftStaleAction"});
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("submitCommands：结构变更不得与属性定义变更同批，而属性值（metadata）批次可以共存", async () => {
    const deps = makeCommandsDeps();
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    mockDraftSave();
    // 让草稿里真的存在一条「属性定义」类动作，而不是假造 computed
    deps.draft.addCommandBatch([createCommand.addCustomProperty("sheetset", "P", "")], {key: "k"}, "property");
    expect(deps.draft.hasPropertyDefinitionCommands.value).toBe(true);
    const commands = useWorkspaceCommands(deps);

    const structural = await commands.submitCommands([createCommand.deleteSheet("s1")], {key: "k"}, "structural");
    expect(structural).toEqual({ok: false, message: "shell.errors.mixedBatches"});

    const metadata = await commands.submitCommands([createCommand.updateSheetProperties("s1", {})], {key: "k"}, "metadata");
    expect(metadata).toEqual({ok: true});
  });

  it("dock：门禁矩阵按 §6.9 顺序判定（任务中 > 待人工检查 > DST 状态 > 无变更 > 未预览 > 预览过期 > 不可执行 > 放行）", async () => {
    const deps = makeCommandsDeps();
    const commands = useWorkspaceCommands(deps);
    deps.workspace.value = {id: "w1", revision_id: "r1"} as unknown as Workspace;
    const previewContext = deps.previewContext;
    const setPreview = (workspaceId: string, revisionId: string, executable: boolean) => {
      previewContext.value = {workspaceId, baseRevisionId: revisionId, cadVersion: "2020", commands: [], result: {executable} as PreviewContext["result"]};
    };

    expect(commands.dock.value.writeDisabledReason).toBe("shell.dock.reasonNoChanges");

    deps.draft.addCommandBatch([createCommand.deleteSheet("s1")], {key: "k"}, "structural");
    expect(commands.dock.value.writeDisabledReason).toBe("shell.dock.reasonPreviewFirst");
    expect(commands.dock.value.canPreview).toBe(true);

    setPreview("w1", "r1", true);
    expect(commands.dock.value.canWrite).toBe(true);
    expect(commands.dock.value.writeNeedsModal).toBe(true);

    // 预览上下文与当前修订不一致 ⇒ 过期（不可写、但可重新预览）
    deps.workspace.value = {id: "w1", revision_id: "r2"} as unknown as Workspace;
    expect(commands.dock.value.writeDisabledReason).toBe("shell.dock.reasonPreviewStale");

    // 上下文可执行性由服务端裁决，前端只据此锁定写入（修订必须与当前工作区一致，否则先命中过期分支）
    setPreview("w1", "r2", false);
    expect(commands.dock.value.writeDisabledReason).toBe("shell.dock.reasonNotExecutable");
  });

  it("queueDelete：先过编辑未提交闸门，未确认则不产生命令", async () => {
    const deps = makeCommandsDeps();
    const guard = vi.fn(async (next: () => void | Promise<void>) => {await next()});
    deps.getEditor = () => ({context: ref(null), guard, discardIfTargeting: vi.fn()}) as unknown as ReturnType<WorkspaceCommandsOptions["getEditor"]>;
    deps.confirmAction = vi.fn(async () => false);
    const commands = useWorkspaceCommands(deps);

    await commands.queueDelete({id: "s1", number: "A-101"} as unknown as Sheet);

    expect(guard).toHaveBeenCalledTimes(1);
    expect(deps.draft.commands.value).toHaveLength(0);
    expect(deps.pushToast).not.toHaveBeenCalled();
  });

  it("guardedImportCsv：导入被未提交输入闸门包住（闸门未放行则不得导入）", async () => {
    const deps = makeCommandsDeps();
    const importCsv = vi.fn(async () => {});
    deps.getCsvImport = () => ({importCsv, invalidateCsvPreview: vi.fn(), csvText: ref(""), csvPreview: ref(null)});
    const guardAllInputs = vi.fn(async (next: () => Promise<void> | void) => {await next()});
    deps.draft.guardAllInputs = guardAllInputs;
    const commands = useWorkspaceCommands(deps);

    await commands.guardedImportCsv();
    expect(guardAllInputs).toHaveBeenCalledTimes(1);
    expect(importCsv).toHaveBeenCalledTimes(1);

    // 闸门停下（用户选「留在此处」）⇒ next 不执行 ⇒ 不得发生正式写入
    guardAllInputs.mockImplementation(async () => {});
    await commands.guardedImportCsv();
    expect(importCsv).toHaveBeenCalledTimes(1);
  });

  it("快捷键：注册 open/preview/write/undo/redo 五个动作，且 preview 在门禁不允许时只提示不动作", () => {
    const deps = makeCommandsDeps();
    useWorkspaceCommands(deps);

    expect(hotkeysSpy).toHaveBeenCalledTimes(1);
    const handlers = hotkeysSpy.mock.calls[0][0] as {open: () => void; preview: () => void; write: () => void; undo: () => void; redo: () => void};
    expect(Object.keys(handlers).sort()).toEqual(["open", "preview", "redo", "undo", "write"]);
    // 无命令时 canPreview 为假 ⇒ 不预览，只把门禁原因写进 error（非阻断提示）
    handlers.preview();
    expect(deps.error.value).toBe("shell.dock.reasonNoChanges");
  });
});
