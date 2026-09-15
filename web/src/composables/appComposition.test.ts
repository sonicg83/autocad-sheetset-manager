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
import {ApiError} from "../api/client";
import type {ChangeCommand, Workspace} from "../api/contracts";

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
