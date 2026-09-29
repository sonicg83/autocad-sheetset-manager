import {describe, expect, it} from "vitest";
import {
  buildLibraryState,
  DEFAULT_FILTERS,
  detailActions,
  filterStandardList,
  formatPublishedAt,
} from "./standardLibraryModel";
import type {StandardSummary} from "../../features/standards/types";

function published(
  standardId: string,
  name: string,
  source: "official" | "user" = "user",
  description = "标准描述",
  publishedAt: number | null = 1_704_164_645_000,
): StandardSummary {
  return {source, status: "published", standard_id: standardId, name, description, published_at: publishedAt, draft_id: null};
}

function draft(standardId: string, name: string, draftId: string, description = "草稿描述"): StandardSummary {
  return {source: "user", status: "draft", standard_id: standardId, name, description, published_at: null, draft_id: draftId};
}

describe("buildLibraryState", () => {
  it("separates an empty library from an empty filter result", () => {
    expect(buildLibraryState([], DEFAULT_FILTERS).kind).toBe("empty-library");
    expect(buildLibraryState([published("00000000-0000-4000-8000-000000000001", "官方标准", "official")], {
      source: "user", status: "all", query: "",
    }).kind).toBe("empty-filter");
  });

  it("returns a flat list and searches standard UUIDs even when they are not displayed", () => {
    const items = [
      published("00000000-0000-4000-8000-000000000001", "燃气标准"),
      draft("00000000-0000-4000-8000-000000000002", "我的草稿", "draft-2"),
    ];
    const state = buildLibraryState(items, {source: "all", status: "all", query: "00000000-0000-4000-8000-000000000002"});
    expect(state).toEqual({kind: "ready", items: [items[1]]});
  });

  it("filters by source and status independently", () => {
    const official = published("00000000-0000-4000-8000-000000000001", "官方标准", "official");
    const user = published("00000000-0000-4000-8000-000000000002", "用户标准");
    const draftItem = draft("00000000-0000-4000-8000-000000000003", "我的草稿", "draft-1");
    expect(filterStandardList([official, user, draftItem], {source: "official", status: "all", query: ""})).toEqual([official]);
    expect(filterStandardList([official, user, draftItem], {source: "all", status: "draft", query: ""})).toEqual([draftItem]);
  });
});

describe("detailActions", () => {
  it("allows deleting user standards and drafts while official standards remain protected", () => {
    const official = published("00000000-0000-4000-8000-000000000001", "官方标准", "official");
    const user = published("00000000-0000-4000-8000-000000000002", "用户标准");
    const draftItem = draft("00000000-0000-4000-8000-000000000003", "我的草稿", "draft-1");
    expect(detailActions(official).canDelete).toBe(false);
    expect(detailActions(user).canDelete).toBe(true);
    expect(detailActions(draftItem).canDelete).toBe(true);
    expect(detailActions(user).canEdit).toBe(false);
    expect(detailActions(user).canDerive).toBe(true);
    expect(detailActions(user).canExport).toBe(true);
  });
});

describe("formatPublishedAt", () => {
  it("assembles local date and time from explicit numeric fields", () => {
    const timestamp = Date.parse("2024-04-05T16:07:00.000Z");
    const parts = new Intl.DateTimeFormat(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(timestamp));
    const field = (type: string) => parts.find(part => part.type === type)?.value;
    expect(formatPublishedAt(timestamp)).toBe(`${field("year")}/${field("month")}/${field("day")} ${field("hour")}:${field("minute")}`);
  });

  it("returns no date for a draft or an untrusted timestamp", () => {
    expect(formatPublishedAt(null)).toBeNull();
    expect(formatPublishedAt(Number.NaN)).toBeNull();
  });
});
