// @vitest-environment happy-dom
// ===== Task 11 第 11e 轮：命令/API 编排组合层 =====
// 为什么需要这组单测（Step 2 的原意）：11e 把「页面事件 → 命令/API 编排」搬进 useWorkspaceCommands。
// 三处最容易搬错、而 e2e 未必立刻暴露的语义：
//   ① submitCommands 的**分批规则**（结构变更与属性定义变更不得同批，SPEC-DM-009）与拒绝优先级；
//   ② ActionDock 门禁矩阵（SPEC-DM-006 §6.9）——它是预览/写入的唯一出口，**分支顺序即优先级**；
//   ③ 删除与 CSV 导入在**确认/写入前**必须先过未提交输入闸门，不能静默丢草稿。
// useHotkeys 以 mock 替换：快捷键注册需要组件实例（onMounted），其端到端行为由 e2e 覆盖；
// 此处只钉住「注册了哪几个动作」与各动作的门禁分支。
// （Task 12 M1：原 `appComposition.test.ts` 按域拆分，共用夹具在 `./appCompositionTestSupport`。）
import {ref} from "vue";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {useWorkspaceCommands, type PreviewContext, type WorkspaceCommandsOptions} from "./useWorkspaceCommands";
import {useDraftGuards} from "./useDraftGuards";
import {createCommand} from "../api/contracts";
import {apiRequest, makeDraftDeps, mockApiClient} from "./appCompositionTestSupport";
import type {Sheet, Workspace} from "../api/contracts";

vi.mock("../api/client", async () => {
  const {mockApiClient} = await import("./appCompositionTestSupport");
  return mockApiClient();
});

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
    const errorBefore = deps.error.value;

    const structural = await commands.submitCommands([createCommand.deleteSheet("s1")], {key: "k"}, "structural");
    expect(structural).toEqual({ok: false, message: "shell.errors.mixedBatches"});
    // ★ 拒绝必须发生在**触碰草稿层之前**：否则草稿层也会以同一条混批文案拒绝，
    // 本用例就无法区分「编排层裁决」与「下游兜底」了（变异自证时实测过这个盲点）。
    // error 不被写入是「编排层直接裁决」的可见差别（下游失败会写 error 并回显）。
    expect(deps.error.value).toBe(errorBefore);

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
