// @vitest-environment happy-dom
// —— 11c：未提交输入与草稿门禁（草稿栈 + 三选一 guard）——
//
// 为什么需要这组单测：11c 把 `App.vue` 的草稿域整体搬进 `useDraftGuards`。其中多数语义在 E2E 里
// 要「造真实草稿并制造版本冲突」才可见，单测把它们钉成可核验契约：
// ① 草稿栈投影语义（撤销/重做/移除与游标的关系、新动作截断重做尾巴）；
// ② `DRAFT_CONFLICT` 引发的只读降级（草稿 stale、命令清空、错误文案）；
// ③ 图纸页/属性页两个输入域的过闸顺序与「留在此处」终止；
// ④ 范围改变隐藏当前编辑对象时「先还原快照、再三选一」的次序。
// （Task 12 M1：原 `appComposition.test.ts` 按域拆分，共用夹具在 `./appCompositionTestSupport`。）
import {computed, ref} from "vue";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {useDraftGuards, type DraftGuardsDeps, type EditorApi} from "./useDraftGuards";
import {apiRequest, cmd, makeApiError, makeConflicted, makeDraftDeps, makeEditor, makeProperties, makeSheets, mockApiClient, rows} from "./appCompositionTestSupport";

vi.mock("../api/client", async () => {
  const {mockApiClient} = await import("./appCompositionTestSupport");
  return mockApiClient();
});

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
