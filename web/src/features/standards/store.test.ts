// 标准状态控制器单测（PLAN-DM-035 Task 7）：代次保护、列表刷新与发布/导入转译。
// api 以可编程测试替身注入，用 deferred promise 驱动乱序响应场景。
import {describe, expect, it, vi} from "vitest";
import {createStandardStore, type StandardApi} from "./store";
import type {StandardDetail, StandardSummary} from "./types";

function publishedDetail(standardId: string, version: number): StandardDetail {
  return {
    standard_id: standardId,
    version,
    name: `标准 ${standardId}`,
    supported_cad_versions: ["2016", "2020"],
    dependencies: [],
    document: {},
  };
}

interface DeferredDetail {
  resolve: (detail: StandardDetail) => void;
  promise: Promise<StandardDetail>;
}

function deferredStandardApi(): StandardApi & {resolveDetail: (standardId: string, detail: StandardDetail) => void} {
  const waiters = new Map<string, DeferredDetail>();
  const api = {
    list: vi.fn(async () => []),
    fetchDetail: vi.fn((identity: {standardId: string; version: string}) => {
      let resolve!: (detail: StandardDetail) => void;
      const promise = new Promise<StandardDetail>((done) => {resolve = done;});
      waiters.set(identity.standardId, {resolve, promise});
      return promise;
    }),
    fetchDraft: vi.fn(),
    createDraft: vi.fn(),
    saveDraft: vi.fn(),
    publish: vi.fn(),
    previewImport: vi.fn(),
    confirmImport: vi.fn(),
    cancelImport: vi.fn(),
    deleteDraft: vi.fn(),
    inspectAsset: vi.fn(),
  } as unknown as StandardApi;
  return Object.assign(api, {
    resolveDetail: (standardId: string, detail: StandardDetail) => {waiters.get(standardId)?.resolve(detail);},
  });
}

describe("createStandardStore", () => {
  it("does not let an older detail response replace the current standard", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const first = store.open({standardId: "official.a", version: 1});
    const second = store.open({standardId: "user.b", version: 2});
    api.resolveDetail("user.b", publishedDetail("user.b", 2));
    api.resolveDetail("official.a", publishedDetail("official.a", 1));
    await Promise.all([first, second]);
    expect(store.detail.value?.standard_id).toBe("user.b");
  });

  it("drops a stale detail response when the selection moves to a draft", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const pending = store.open({standardId: "official.a", version: 1});
    store.clearDetail();
    api.resolveDetail("official.a", publishedDetail("official.a", 1));
    await pending;
    expect(store.detail.value).toBeNull();
    expect(store.detailPending.value).toBe(false);
  });

  it("clears the previous detail as soon as a new selection starts loading", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const first = store.open({standardId: "official.a", version: 1});
    api.resolveDetail("official.a", publishedDetail("official.a", 1));
    await first;
    expect(store.detail.value?.standard_id).toBe("official.a");

    const second = store.open({standardId: "user.b", version: 2});
    // 在途期间旧详情不得继续可用：派生等动作只能消费身份匹配的已加载详情
    expect(store.detail.value).toBeNull();
    expect(store.detailMatches({standardId: "user.b", version: 2})).toBe(false);
    api.resolveDetail("user.b", publishedDetail("user.b", 2));
    await second;
    expect(store.detail.value?.standard_id).toBe("user.b");
    expect(store.detailMatches({standardId: "user.b", version: 2})).toBe(true);
    expect(store.detailMatches({standardId: "official.a", version: 1})).toBe(false);
  });

  it("keeps no usable detail when the detail load fails", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const first = store.open({standardId: "official.a", version: 1});
    api.resolveDetail("official.a", publishedDetail("official.a", 1));
    await first;

    api.fetchDetail = vi.fn(async () => {
      throw new Error("STANDARD_VERSION_NOT_FOUND: 标准不存在");
    });
    await store.open({standardId: "user.b", version: 2});
    expect(store.detail.value).toBeNull();
    expect(store.detailError.value).toContain("STANDARD_VERSION_NOT_FOUND");
    expect(store.detailMatches({standardId: "official.a", version: 1})).toBe(false);
  });

  it("refreshes the library list and keeps pending/error explicit", async () => {
    const api = deferredStandardApi();
    api.list = vi.fn(async (): Promise<StandardSummary[]> => [
      {source: "official", status: "published", standard_id: "official.a", version: 1, name: "官方标准 A", draft_id: null},
    ]);
    const store = createStandardStore(api);
    expect(store.summaries.value).toEqual([]);
    await store.refresh();
    expect(store.summaries.value).toHaveLength(1);
    expect(store.listPending.value).toBe(false);
    expect(store.listError.value).toBe("");
  });

  it("records a stable error message when listing fails", async () => {
    const api = deferredStandardApi();
    api.list = vi.fn(async () => {
      throw new Error("STANDARD_LIST_FAILED: 后端不可用");
    });
    const store = createStandardStore(api);
    await store.refresh();
    expect(store.listPending.value).toBe(false);
    expect(store.listError.value).toContain("STANDARD_LIST_FAILED");
  });

  it("publishes a draft and appends the published standard to the summary list", async () => {
    const api = deferredStandardApi();
    api.list = vi.fn(async (): Promise<StandardSummary[]> => [
      {source: "user", status: "draft", standard_id: "user.b", version: null, name: "草稿", draft_id: "draft-1"},
    ]);
    api.publish = vi.fn(async () => ({standard_id: "user.b", version: 2, name: "草稿"}));
    const store = createStandardStore(api);
    await store.refresh();
    const published = await store.publish({draftId: "draft-1"});
    expect(published).toEqual({standard_id: "user.b", version: 2, name: "草稿"});
    expect(api.publish).toHaveBeenCalledWith({draftId: "draft-1"});
  });
});
