// 草稿自动保存单元测试（PLAN-DB-001 Task 5；SPEC-DB-001 §2：500 ms 防抖、
// base_updated_at 乐观并发、409 冲突提示）。
import {reactive} from "vue";
import {afterEach, beforeEach, describe, expect, it, vi, type Mock} from "vitest";
import {createDraftAutosave, type AutosavePatch, type AutosaveResult} from "./useDraftAutosave";

type SaveImpl = (patch: AutosavePatch<{name: string; count: number}>) => Promise<AutosaveResult>;

interface Env {
  draft: {name: string; count: number};
  save: Mock;
  onSaved: Mock;
  onConflict: Mock;
  onError: Mock;
  baseUpdatedAt: string;
}

function makeEnv(saveImpl?: SaveImpl): Env {
  const draft = reactive({name: "示例", count: 1});
  const save: Mock = vi.fn(saveImpl ?? (async () => ({updated_at: "t-2", diagnostics: []})));
  const onSaved: Mock = vi.fn();
  const onConflict: Mock = vi.fn();
  const onError: Mock = vi.fn();
  return {draft, save, onSaved, onConflict, onError, baseUpdatedAt: "t-1"};
}

function attach(env: Env, debounceMs = 500) {
  return createDraftAutosave({
    draft: env.draft,
    save: env.save as unknown as (patch: AutosavePatch<{name: string; count: number}>) => Promise<AutosaveResult>,
    getBaseUpdatedAt: () => env.baseUpdatedAt,
    getWizardStep: () => 2,
    getFocusedField: () => "project.name",
    debounceMs,
    onSaved: env.onSaved as unknown as (result: AutosaveResult) => void,
    onConflict: env.onConflict as unknown as (error: unknown) => void,
    onError: env.onError as unknown as (error: unknown) => void,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("createDraftAutosave", () => {
  it("字段变更后 500 ms 才发送一次 PATCH，携带 base_updated_at 与聚焦字段", async () => {
    const env = makeEnv();
    const autosave = attach(env);
    env.draft.name = "示例工程";
    vi.advanceTimersByTime(499);
    expect(env.save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(env.save).toHaveBeenCalledTimes(1);
    const patch = env.save.mock.calls[0][0] as AutosavePatch<{name: string; count: number}>;
    expect(patch.base_updated_at).toBe("t-1");
    expect(patch.draft.name).toBe("示例工程");
    expect(patch.wizard_step).toBe(2);
    expect(patch.focused_field).toBe("project.name");
    expect(autosave.status.value).toBe("saved");
    autosave.dispose();
  });

  it("窗口内的连续变更合并为一次保存", async () => {
    const env = makeEnv();
    const autosave = attach(env);
    env.draft.name = "a";
    vi.advanceTimersByTime(200);
    env.draft.name = "ab";
    vi.advanceTimersByTime(200);
    env.draft.name = "abc";
    await vi.advanceTimersByTimeAsync(500);
    expect(env.save).toHaveBeenCalledTimes(1);
    expect((env.save.mock.calls[0][0] as AutosavePatch<{name: string}>).draft.name).toBe("abc");
    autosave.dispose();
  });

  it("409 DRAFT_CONFLICT 进入冲突状态并触发 onConflict", async () => {
    const conflict = Object.assign(new Error("草稿已在他处修改"), {
      status: 409,
      code: "DRAFT_CONFLICT",
    });
    const env = makeEnv(async () => {
      throw conflict;
    });
    const autosave = attach(env);
    env.draft.name = "新名";
    await vi.advanceTimersByTimeAsync(500);
    expect(env.save).toHaveBeenCalledTimes(1);
    expect(autosave.status.value).toBe("conflict");
    expect(env.onConflict).toHaveBeenCalledWith(conflict);
    expect(env.onSaved).not.toHaveBeenCalled();
    autosave.dispose();
  });

  it("冲突后继续编辑仍能再次调度保存", async () => {
    let fail = true;
    const env = makeEnv(async () => {
      if (fail) {
        throw Object.assign(new Error("conflict"), {status: 409, code: "DRAFT_CONFLICT"});
      }
      return {updated_at: "t-3", diagnostics: []};
    });
    const autosave = attach(env);
    env.draft.name = "第一次";
    await vi.advanceTimersByTimeAsync(500);
    expect(autosave.status.value).toBe("conflict");
    fail = false;
    env.draft.name = "第二次";
    await vi.advanceTimersByTimeAsync(500);
    expect(env.save).toHaveBeenCalledTimes(2);
    expect(autosave.status.value).toBe("saved");
    autosave.dispose();
  });

  it("保存成功触发 onSaved 并携带新的 updated_at", async () => {
    const env = makeEnv();
    const autosave = attach(env);
    env.draft.count = 2;
    await vi.advanceTimersByTimeAsync(500);
    expect(autosave.status.value).toBe("saved");
    expect(env.onSaved).toHaveBeenCalledWith({updated_at: "t-2", diagnostics: []});
    autosave.dispose();
  });

  it("非冲突错误进入 error 状态并触发 onError", async () => {
    const boom = Object.assign(new Error("网络失败"), {status: 0, code: "NETWORK"});
    const env = makeEnv(async () => {
      throw boom;
    });
    const autosave = attach(env);
    env.draft.name = "x";
    await vi.advanceTimersByTimeAsync(500);
    expect(autosave.status.value).toBe("error");
    expect(env.onError).toHaveBeenCalledWith(boom);
    autosave.dispose();
  });

  it("flush 立即保存待保存变更，不必等满防抖窗口", async () => {
    const env = makeEnv();
    const autosave = attach(env);
    env.draft.name = "立即";
    await autosave.flush();
    expect(env.save).toHaveBeenCalledTimes(1);
    expect((env.save.mock.calls[0][0] as AutosavePatch<{name: string}>).draft.name).toBe("立即");
    autosave.dispose();
  });

  it("暂停期间不调度保存，恢复后继续", async () => {
    const env = makeEnv();
    const autosave = attach(env);
    autosave.pause();
    env.draft.name = "暂停期间";
    await vi.advanceTimersByTimeAsync(1000);
    expect(env.save).not.toHaveBeenCalled();
    autosave.resume();
    env.draft.name = "恢复之后";
    await vi.advanceTimersByTimeAsync(500);
    expect(env.save).toHaveBeenCalledTimes(1);
    autosave.dispose();
  });
});
