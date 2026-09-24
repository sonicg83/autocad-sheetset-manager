// 创建域状态控制器单测（PLAN-DM-036 Task 8）：按组复制、重排、批量修改与标准替换。
// api 以可编程测试替身注入；替身经 `seed` 同步给出起点（草稿 + 已解析的标准输入模型），
// 使按组编辑用例不必先走一次异步草稿恢复。
import {describe, expect, it, vi} from "vitest";
import {createCreationStore} from "./store";
import type {
  CreationApi,
  CreationDraftState,
  CreationImportOutcome,
  CreationStandardCandidate,
  CreationStandardInputs,
} from "./types";

/** 起点草稿：三个组，`prop-stage` 只在组 2 上是「保留」（批量明确清空的对照组）。 */
function seedDraft(): CreationDraftState {
  return {
    id: "draft-1",
    standard_id: "szmedi.gas",
    standard_version: "2.1.0",
    revision: 1,
    step: "groups",
    target_path: "D:\\项目\\新建项目",
    sheetset_values: {"prop-major": "燃气"},
    groups: [0, 1, 2].map(order => ({
      group_id: `group-${order + 1}`,
      created_order: order,
      title: ["封面", "平面图", "纵断面图"][order] ?? "",
      count: 1,
      base_asset_id: "base-a",
      layout_asset_id: "layout-a",
      paper_layout: "A2",
      sheet_values: {"prop-stage": order === 1 ? "保留" : "施工图"},
    })),
  };
}

function seedStandard(standardId = "szmedi.gas", version = "2.1.0"): CreationStandardInputs {
  return {
    identity: {standardId, version},
    name: "市政燃气施工图",
    sheetset_properties: [
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        required: true,
        default_value: "燃气",
        options: [
          {item_id: "enum-gas", value: "燃气"},
          {item_id: "enum-jz", value: "建筑"},
        ],
      },
    ],
    sheet_properties: [
      {
        property_id: "prop-stage",
        name: "图纸阶段",
        scope: "sheet",
        kind: "enum",
        required: false,
        default_value: "施工图",
        options: [
          {item_id: "enum-cs", value: "施工图"},
          {item_id: "enum-jg", value: "竣工图"},
        ],
      },
    ],
    derived_properties: [],
    asset_options: [
      {asset_id: "base-a", kind: "base-template", label: "市政基础.dwt", layouts: []},
      {asset_id: "layout-a", kind: "layout-template", label: "市政图框.dwt", layouts: ["A2", "A1"]},
    ],
  };
}

function candidate(standardId: string, version: string): CreationStandardCandidate {
  return {
    standard_id: standardId,
    version,
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    available: true,
    reasons: [],
    asset_options: seedStandard(standardId, version).asset_options,
  };
}

function fakeCreationApi(): CreationApi {
  return {
    seed: {draft: seedDraft(), standard: seedStandard()},
    listStandards: vi.fn(async () => []),
    fetchStandardDocument: vi.fn(async () => ({})),
    createDraft: vi.fn(async () => seedDraft()),
    fetchDraft: vi.fn(async () => seedDraft()),
    saveDraft: vi.fn(async () => seedDraft()),
    deleteDraft: vi.fn(async () => undefined),
    templateUrl: vi.fn(() => "/api/creation-drafts/draft-1/xlsx-template"),
    importWorkbook: vi.fn(async (): Promise<CreationImportOutcome> => ({ok: true, draft: seedDraft()})),
    previewDraft: vi.fn(async () => ({
      draft_id: "draft-1",
      revision: 1,
      standard_id: "szmedi.gas",
      standard_version: "2.1.0",
      standard_name: "市政燃气施工图",
      target_path: "D:\\项目\\新建项目",
      sheetset_values: {},
      group_count: 0,
      sheet_count: 0,
      dwg_count: 0,
      numbering: {sequence_field: "subset.sequence", digits: 2, start: 1},
      suffix: {enabled: false, suffix_type: 0, unnumbered_keywords: []},
      diagnostics: [],
      groups: [],
      executable: true,
      preview_digest: "digest-1",
    })),
    executeDraft: vi.fn(async () => ({id: "job-1", status: "QUEUED", workspace_id: null})),
  };
}

describe("createCreationStore", () => {
  it("copies the most recently created group after reorder", async () => {
    const store = createCreationStore(fakeCreationApi());
    store.addGroup();
    const latest = store.addGroup();
    store.updateGroup(latest.group_id, {title: "平面图", count: 3});
    store.moveGroup(1, 0);
    const added = store.addGroup();
    expect(added.title).toBe("平面图");
    expect(added.count).toBe(3);
    expect(added.group_id).not.toBe(latest.group_id);
    expect(store.previewDigest).toBeNull();
  });

  it("applies an explicit clear only to selected groups", async () => {
    const store = createCreationStore(fakeCreationApi());
    store.batchUpdate(["group-1", "group-3"], "prop-stage", {kind: "clear"});
    expect(store.group("group-1").sheet_values["prop-stage"]).toBe("");
    expect(store.group("group-2").sheet_values["prop-stage"]).toBe("保留");
  });

  it("keeps a user-cleared value empty instead of refilling the standard default", async () => {
    const store = createCreationStore(fakeCreationApi());
    store.setSheetsetValue("prop-major", "");
    expect(store.sheetsetValues["prop-major"]).toBe("");
    expect(store.previewDigest).toBeNull();
  });

  it("clears incompatible inputs when the fixed standard is replaced", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    store.setSheetsetValue("prop-major", "建筑");
    api.createDraft = vi.fn(async (): Promise<CreationDraftState> => ({
      id: "draft-2",
      standard_id: "user.b",
      standard_version: "2.0.0",
      revision: 1,
      step: "project",
      target_path: "",
      sheetset_values: {},
      groups: [],
    }));
    api.fetchStandardDocument = vi.fn(async () => ({}));

    await store.chooseStandard(candidate("user.b", "2.0.0"), {replace: true});

    expect(api.deleteDraft).toHaveBeenCalledWith("draft-1");
    expect(store.groups).toHaveLength(0);
    expect(store.sheetsetValues).toEqual({});
    expect(store.standard?.identity.standardId).toBe("user.b");
    expect(store.step).toBe("project");
    expect(store.previewDigest).toBeNull();
  });
});
