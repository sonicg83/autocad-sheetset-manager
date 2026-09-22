// 标准库视图模型单测（PLAN-DM-035 Task 8）：筛选空态、只读边界、版本分组与可见原因。
import {describe, expect, it} from "vitest";
import {
  buildLibraryState,
  DEFAULT_FILTERS,
  detailActions,
  filterStandardList,
  versionHistory,
} from "./standardLibraryModel";
import type {StandardSummary} from "../../features/standards/types";

function officialStandard(): StandardSummary {
  return {source: "official", status: "published", standard_id: "szmedi.gas", version: "2.1.0", name: "市政燃气施工图", draft_id: null};
}

function publishedUserStandard(): StandardSummary {
  return {source: "user", status: "published", standard_id: "szmedi.gas", version: "2.0.0", name: "市政燃气施工图", draft_id: null};
}

function userDraft(): StandardSummary {
  return {source: "user", status: "draft", standard_id: "szmedi.gas", version: "", name: "我的草稿", draft_id: "draft-1"};
}

describe("buildLibraryState", () => {
  it("separates an empty library from an empty filter result", () => {
    expect(buildLibraryState([], DEFAULT_FILTERS).kind).toBe("empty-library");
    expect(buildLibraryState([officialStandard()], {source: "user", status: "all", query: ""}).kind).toBe("empty-filter");
  });

  it("matches entries by query across id and name", () => {
    const state = buildLibraryState([officialStandard(), userDraft()], {source: "all", status: "all", query: "燃气"});
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.items.map(item => item.standard_id)).toEqual(["szmedi.gas"]);
  });

  it("keeps the empty-filter state visible when the query filters everything out", () => {
    const state = buildLibraryState([officialStandard()], {source: "all", status: "draft", query: "不存在的名字"});
    expect(state.kind).toBe("empty-filter");
  });
});

describe("filterStandardList", () => {
  it("filters by source and status independently", () => {
    const items = [officialStandard(), publishedUserStandard(), userDraft()];
    expect(filterStandardList(items, {source: "official", status: "all", query: ""})).toEqual([officialStandard()]);
    expect(filterStandardList(items, {source: "all", status: "draft", query: ""})).toEqual([userDraft()]);
  });
});

describe("detailActions", () => {
  it("keeps official and published versions read-only", () => {
    expect(detailActions(officialStandard()).canEdit).toBe(false);
    expect(detailActions(publishedUserStandard()).canEdit).toBe(false);
    expect(detailActions(userDraft()).canEdit).toBe(true);
  });

  it("attaches a stable read-only reason code to read-only entries", () => {
    expect(detailActions(officialStandard()).readOnlyReason).toBe("official");
    expect(detailActions(publishedUserStandard()).readOnlyReason).toBe("published");
    expect(detailActions(userDraft()).readOnlyReason).toBeNull();
  });

  it("allows deriving and exporting published versions but only deleting drafts", () => {
    for (const summary of [officialStandard(), publishedUserStandard()]) {
      const actions = detailActions(summary);
      expect(actions.canDerive).toBe(true);
      expect(actions.canExport).toBe(true);
      expect(actions.canDelete).toBe(false);
    }
    expect(detailActions(userDraft()).canDelete).toBe(true);
  });
});

describe("versionHistory", () => {
  it("lists published versions of the same standard id, newest first", () => {
    expect(versionHistory(officialStandard(), [officialStandard(), publishedUserStandard(), userDraft()])).toEqual([
      {version: "2.1.0", source: "official"},
      {version: "2.0.0", source: "user"},
    ]);
  });
});
