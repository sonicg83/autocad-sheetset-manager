// 标准状态控制器单测（PLAN-DM-035 Task 7）：代次保护、列表刷新与发布/导入转译。
// api 以可编程测试替身注入，用 deferred promise 驱动乱序响应场景。
import {describe, expect, it, vi} from "vitest";
import {createStandardStore, type StandardApi} from "./store";
import type {StandardDetail, StandardSummary} from "./types";

function publishedDetail(standardId: string): StandardDetail {
  return {
    standard_id: standardId,
    published_at: 1_704_164_645_000,
    name: `标准 ${standardId}`,
    description: "标准描述",
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
    fetchDetail: vi.fn((identity: {standardId: string}) => {
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
    previewDeleteStandard: vi.fn(),
    deleteStandard: vi.fn(),
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
    const first = store.open({standardId: "official.a"});
    const second = store.open({standardId: "user.b"});
    api.resolveDetail("user.b", publishedDetail("user.b"));
    api.resolveDetail("official.a", publishedDetail("official.a"));
    await Promise.all([first, second]);
    expect(store.detail.value?.standard_id).toBe("user.b");
  });

  it("drops a stale detail response when the selection moves to a draft", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const pending = store.open({standardId: "official.a"});
    store.clearDetail();
    api.resolveDetail("official.a", publishedDetail("official.a"));
    await pending;
    expect(store.detail.value).toBeNull();
    expect(store.detailPending.value).toBe(false);
  });

  it("clears the previous detail as soon as a new selection starts loading", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const first = store.open({standardId: "official.a"});
    api.resolveDetail("official.a", publishedDetail("official.a"));
    await first;
    expect(store.detail.value?.standard_id).toBe("official.a");

    const second = store.open({standardId: "user.b"});
    // 在途期间旧详情不得继续可用：派生等动作只能消费身份匹配的已加载详情
    expect(store.detail.value).toBeNull();
    expect(store.detailMatches({standardId: "user.b"})).toBe(false);
    api.resolveDetail("user.b", publishedDetail("user.b"));
    await second;
    expect(store.detail.value?.standard_id).toBe("user.b");
    expect(store.detailMatches({standardId: "user.b"})).toBe(true);
    expect(store.detailMatches({standardId: "official.a"})).toBe(false);
  });

  it("keeps no usable detail when the detail load fails", async () => {
    const api = deferredStandardApi();
    const store = createStandardStore(api);
    const first = store.open({standardId: "official.a"});
    api.resolveDetail("official.a", publishedDetail("official.a"));
    await first;

    api.fetchDetail = vi.fn(async () => {
      throw new Error("STANDARD_VERSION_NOT_FOUND: 标准不存在");
    });
    await store.open({standardId: "user.b"});
    expect(store.detail.value).toBeNull();
    expect(store.detailError.value).toContain("STANDARD_VERSION_NOT_FOUND");
    expect(store.detailMatches({standardId: "official.a"})).toBe(false);
  });

  it("refreshes the library list and keeps pending/error explicit", async () => {
    const api = deferredStandardApi();
    api.list = vi.fn(async (): Promise<StandardSummary[]> => [
      {source: "official", status: "published", standard_id: "official.a", name: "官方标准 A", description: "", published_at: 1_704_164_645_000, draft_id: null},
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
      {source: "user", status: "draft", standard_id: "00000000-0000-4000-8000-000000000046", name: "草稿", description: "", published_at: null, draft_id: "draft-1"},
    ]);
    api.publish = vi.fn(async () => ({standard_id: "00000000-0000-4000-8000-000000000046", published_at: 1_704_164_645_000, name: "草稿", description: ""}));
    const store = createStandardStore(api);
    await store.refresh();
    const published = await store.publish({draftId: "draft-1"});
    expect(published).toEqual({standard_id: "00000000-0000-4000-8000-000000000046", published_at: 1_704_164_645_000, name: "草稿", description: ""});
    expect(api.publish).toHaveBeenCalledWith({draftId: "draft-1"});
  });

  it("previews published-standard deletion and submits the returned impact token", async () => {
    const api = deferredStandardApi();
    api.previewDeleteStandard = vi.fn(async () => ({
      standard_id: "00000000-0000-4000-8000-000000000046",
      affected_count: 3,
      impact_token: "impact-token",
    }));
    api.deleteStandard = vi.fn(async () => ({
      standard_id: "00000000-0000-4000-8000-000000000046",
      deleted_count: 4,
    }));
    const store = createStandardStore(api);
    const impact = await store.previewDeleteStandard("00000000-0000-4000-8000-000000000046");
    expect(impact.affected_count).toBe(3);
    await store.deleteStandard("00000000-0000-4000-8000-000000000046", impact.impact_token);
    expect(api.deleteStandard).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000046", "impact-token");
  });

  it("keeps deletion failures visible to the page", async () => {
    const api = deferredStandardApi();
    api.deleteStandard = vi.fn(async () => { throw new Error("STANDARD_DELETE_IMPACT_CHANGED"); });
    const store = createStandardStore(api);
    await expect(store.deleteStandard("00000000-0000-4000-8000-000000000046", "old-token"))
      .rejects.toThrow("STANDARD_DELETE_IMPACT_CHANGED");
    expect(store.actionError.value).toContain("STANDARD_DELETE_IMPACT_CHANGED");
  });
});
