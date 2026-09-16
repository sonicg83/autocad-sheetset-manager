// @vitest-environment happy-dom
// —— 11d：工作区生命周期域（打开 / 关闭 / 刷新 + 代次闸门）——
//
// （Task 12 M1：原 `appComposition.test.ts` 按域拆分，共用夹具在 `./appCompositionTestSupport`。）
import {ref} from "vue";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {useWorkspaceLifecycle, type WorkspaceLifecycleOptions} from "./useWorkspaceLifecycle";
import {useDraftGuards} from "./useDraftGuards";
import {apiRequest, cmd, makeConflicted, makeDraftDeps, mockApiClient} from "./appCompositionTestSupport";
import type {Workspace} from "../api/contracts";

vi.mock("../api/client", async () => {
  const {mockApiClient} = await import("./appCompositionTestSupport");
  return mockApiClient();
});

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
