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

  it("防抖保存在途期间 flush 排队等待：不并发第二个请求，且第二次携带更新后的 base_updated_at", async () => {
    const draft = reactive({name: "首次", count: 1});
    let base = "t-1";
    let resolveInFlight: ((result: AutosaveResult) => void) | null = null;
    const save: Mock = vi.fn(async () => {
      // 第一次调用挂起（模拟在途网络请求），后续调用立即成功
      if (resolveInFlight === null) {
        return new Promise<AutosaveResult>((resolve) => {
          resolveInFlight = resolve;
        });
      }
      return {updated_at: "t-3", diagnostics: []};
    });
    const onConflict = vi.fn();
    const autosave = createDraftAutosave({
      draft,
      save: save as unknown as (patch: AutosavePatch<{name: string; count: number}>) => Promise<AutosaveResult>,
      getBaseUpdatedAt: () => base,
      getWizardStep: () => 1,
      getFocusedField: () => null,
      onSaved: (result) => {
        // 与真实 store 一致：成功后以响应里的 updated_at 作为下一次 CAS 基准
        base = result.updated_at;
      },
      onConflict,
    });

    // 1) 防抖保存发出并处于在途
    draft.name = "第二次";
    await vi.advanceTimersByTimeAsync(500);
    expect(save).toHaveBeenCalledTimes(1);
    expect((save.mock.calls[0][0] as AutosavePatch<{name: string}>).base_updated_at).toBe("t-1");

    // 2) 在途期间 flush(force)（即"下一步"persistStep 的路径）：不得并发发出第二个 PATCH
    const flushPromise = autosave.flush(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledTimes(1);
    expect(autosave.status.value).toBe("saving");

    // 3) 在途请求完成后，排队的 flush 按序发出并携带更新后的 base_updated_at
    resolveInFlight!({updated_at: "t-2", diagnostics: []});
    await flushPromise;
    expect(save).toHaveBeenCalledTimes(2);
    const second = save.mock.calls[1][0] as AutosavePatch<{name: string}>;
    expect(second.base_updated_at).toBe("t-2");
    expect(second.draft.name).toBe("第二次");
    expect(autosave.status.value).toBe("saved");
    expect(onConflict).not.toHaveBeenCalled();
    autosave.dispose();
  });

  it("防抖保存与 flush 同时挂起时也严格按序执行，无并发在途请求", async () => {
    const draft = reactive({name: "a", count: 1});
    let resolveFirst: ((result: AutosaveResult) => void) | null = null;
    const save: Mock = vi.fn(async () => {
      if (resolveFirst === null) {
        return new Promise<AutosaveResult>((resolve) => {
          resolveFirst = resolve;
        });
      }
      return {updated_at: "t-3", diagnostics: []};
    });
    let base = "t-1";
    const autosave = createDraftAutosave({
      draft,
      save: save as unknown as (patch: AutosavePatch<{name: string; count: number}>) => Promise<AutosaveResult>,
      getBaseUpdatedAt: () => base,
      getWizardStep: () => 1,
      getFocusedField: () => null,
      onSaved: (result) => {
        base = result.updated_at;
      },
    });

    draft.name = "b";
    await vi.advanceTimersByTimeAsync(500);
    // 在途期间继续编辑并触发 flush：待保存变更排队，不并发
    draft.name = "c";
    const flushPromise = autosave.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledTimes(1);
    resolveFirst!({updated_at: "t-2", diagnostics: []});
    await flushPromise;
    expect(save).toHaveBeenCalledTimes(2);
    expect((save.mock.calls[1][0] as AutosavePatch<{name: string}>).base_updated_at).toBe("t-2");
    expect((save.mock.calls[1][0] as AutosavePatch<{name: string}>).draft.name).toBe("c");
    // 排队执行已取消防抖计时器，不再有多余的第三次保存
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledTimes(2);
    expect(autosave.status.value).toBe("saved");
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
