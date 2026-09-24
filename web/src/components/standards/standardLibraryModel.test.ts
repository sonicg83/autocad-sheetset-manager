// 标准库视图模型单测（PLAN-DM-035 Task 8；PLAN-DM-041 Task 6）：
// 筛选空态、按 ID 归集、整数降序、组标题口径、只读边界与版本历史。
import {describe, expect, it} from "vitest";
import {
  buildLibraryState,
  DEFAULT_FILTERS,
  detailActions,
  filterStandardList,
  formatStandardVersion,
  groupStandardList,
  versionHistory,
} from "./standardLibraryModel";
import type {StandardSummary} from "../../features/standards/types";

function published(
  standardId: string,
  version: number,
  name: string,
  source: "official" | "user" = "user",
): StandardSummary {
  return {source, status: "published", standard_id: standardId, version, name, draft_id: null};
}

function draft(standardId: string, name: string, draftId: string): StandardSummary {
  return {source: "user", status: "draft", standard_id: standardId, version: null, name, draft_id: draftId};
}

function officialStandard(): StandardSummary {
  return published("szmedi.gas", 2, "市政燃气施工图", "official");
}

function publishedUserStandard(): StandardSummary {
  return published("szmedi.gas", 1, "市政燃气施工图");
}

describe("buildLibraryState", () => {
  it("separates an empty library from an empty filter result", () => {
    expect(buildLibraryState([], DEFAULT_FILTERS).kind).toBe("empty-library");
    expect(buildLibraryState([officialStandard()], {source: "user", status: "all", query: ""}).kind).toBe("empty-filter");
  });

  it("matches entries by query across id and name", () => {
    const state = buildLibraryState([officialStandard(), draft("szmedi.gas", "我的草稿", "draft-1")], {
      source: "all",
      status: "all",
      query: "燃气",
    });
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.groups.map(group => group.standard_id)).toEqual(["szmedi.gas"]);
  });

  it("keeps the empty-filter state visible when the query filters everything out", () => {
    const state = buildLibraryState([officialStandard()], {source: "all", status: "draft", query: "不存在的名字"});
    expect(state.kind).toBe("empty-filter");
  });
});

describe("filterStandardList", () => {
  it("filters by source and status independently", () => {
    const items = [officialStandard(), publishedUserStandard(), draft("szmedi.gas", "我的草稿", "draft-1")];
    expect(filterStandardList(items, {source: "official", status: "all", query: ""})).toEqual([officialStandard()]);
    expect(filterStandardList(items, {source: "all", status: "draft", query: ""})).toEqual([
      draft("szmedi.gas", "我的草稿", "draft-1"),
    ]);
  });
});

describe("groupStandardList", () => {
  it("orders integer versions descending so v10 precedes v9", () => {
    const items = [published("a.b", 9, "九"), published("a.b", 10, "十"), published("a.b", 2, "二")];
    const [group] = groupStandardList(items, DEFAULT_FILTERS);
    expect(group.versions.map(item => item.version)).toEqual([10, 9, 2]);
  });

  it("groups official, user versions and drafts of one id together", () => {
    const items = [
      published("szmedi.gas", 1, "市政燃气施工图", "official"),
      published("szmedi.gas", 4, "市政燃气施工图"),
      draft("szmedi.gas", "我的草稿", "draft-1"),
      published("szmedi.other", 1, "其他标准"),
    ];
    const groups = groupStandardList(items, DEFAULT_FILTERS);
    expect(groups.map(group => group.standard_id)).toEqual(["szmedi.gas", "szmedi.other"]);
    expect(groups[0].versions.map(item => item.source)).toEqual(["user", "official"]);
    expect(groups[0].drafts.map(item => item.draft_id)).toEqual(["draft-1"]);
    // 不同 ID 的同版本号不会串组。
    expect(groups[1].versions.map(item => item.standard_id)).toEqual(["szmedi.other"]);
  });

  it("takes the group title from the highest visible version and falls back to the id for drafts only", () => {
    const renamed = [published("a.b", 1, "旧名称"), published("a.b", 2, "新名称")];
    expect(groupStandardList(renamed, DEFAULT_FILTERS)[0].title).toBe("新名称");
    expect(groupStandardList([draft("a.b", "我的草稿", "draft-1")], DEFAULT_FILTERS)[0].title).toBe("a.b");
  });

  it("keeps historical names visible on their own versions", () => {
    const items = [published("a.b", 1, "旧名称"), published("a.b", 2, "新名称")];
    const [group] = groupStandardList(items, DEFAULT_FILTERS);
    expect(group.versions.map(item => item.name)).toEqual(["新名称", "旧名称"]);
  });

  it("drops groups that no longer have a matching version", () => {
    const items = [published("a.b", 1, "甲"), published("c.d", 1, "乙", "official")];
    const groups = groupStandardList(items, {source: "official", status: "all", query: ""});
    expect(groups.map(group => group.standard_id)).toEqual(["c.d"]);
  });

  it("restores every group when filters are cleared", () => {
    const items = [published("a.b", 1, "甲"), published("c.d", 1, "乙", "official")];
    expect(groupStandardList(items, DEFAULT_FILTERS)).toHaveLength(2);
  });
});

describe("formatStandardVersion", () => {
  it("renders the v-prefixed display form", () => {
    expect(formatStandardVersion(10)).toBe("v10");
  });
});

describe("detailActions", () => {
  it("keeps official and published versions read-only", () => {
    expect(detailActions(officialStandard()).canEdit).toBe(false);
    expect(detailActions(publishedUserStandard()).canEdit).toBe(false);
    expect(detailActions(draft("szmedi.gas", "我的草稿", "draft-1")).canEdit).toBe(true);
  });

  it("attaches a stable read-only reason code to read-only entries", () => {
    expect(detailActions(officialStandard()).readOnlyReason).toBe("official");
    expect(detailActions(publishedUserStandard()).readOnlyReason).toBe("published");
    expect(detailActions(draft("szmedi.gas", "我的草稿", "draft-1")).readOnlyReason).toBeNull();
  });

  it("allows deriving and exporting published versions but only deleting drafts", () => {
    for (const summary of [officialStandard(), publishedUserStandard()]) {
      const actions = detailActions(summary);
      expect(actions.canDerive).toBe(true);
      expect(actions.canExport).toBe(true);
      expect(actions.canDelete).toBe(false);
    }
    expect(detailActions(draft("szmedi.gas", "我的草稿", "draft-1")).canDelete).toBe(true);
  });
});

describe("versionHistory", () => {
  it("lists published versions of the same standard id, newest first", () => {
    const items = [
      officialStandard(),
      publishedUserStandard(),
      published("szmedi.gas", 7, "市政燃气施工图"),
      draft("szmedi.gas", "我的草稿", "draft-1"),
    ];
    expect(versionHistory("szmedi.gas", items)).toEqual([
      {version: 7, source: "user", name: "市政燃气施工图"},
      {version: 2, source: "official", name: "市政燃气施工图"},
      {version: 1, source: "user", name: "市政燃气施工图"},
    ]);
  });

  it("ignores other standard ids", () => {
    expect(versionHistory("other.id", [officialStandard()])).toEqual([]);
  });
});
