// 创建域状态控制器单测（PLAN-DM-036 Task 8）：按组复制、重排、批量修改与标准替换。
// api 以可编程测试替身注入；替身经 `seed` 同步给出起点（草稿 + 已解析的标准输入模型），
// 使按组编辑用例不必先走一次异步草稿恢复。
import {describe, expect, it, vi} from "vitest";
import {createCreationStore} from "./store";
import {creationCascadeOptions, creationStandardInputs} from "./inputModel";
import type {
  CreationApi,
  CreationDerivedEvaluation,
  CreationDraftState,
  CreationImportOutcome,
  CreationSaveInput,
  CreationStandardCandidate,
  CreationStandardInputs,
} from "./types";

/** 起点草稿：三个组，`prop-stage` 只在组 2 上是「保留」（批量明确清空的对照组）。 */
function seedDraft(): CreationDraftState {
  return {
    id: "draft-1",
    standard_id: "00000000-0000-4000-8000-000000000046",
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

function seedStandard(standardId = "00000000-0000-4000-8000-000000000046"): CreationStandardInputs {
  return {
    identity: {standardId},
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

function cascadeStandardDocument(): Record<string, unknown> {
  return {
    properties: [
      {
        property_id: "prop-major", name: "专业", scope: "sheetset", kind: "enum",
        required: true, default_value: "道路",
        enum_items: [{item_id: "enum-road", value: "道路"}, {item_id: "enum-gas", value: "燃气"}],
      },
      {
        property_id: "prop-region", name: "区域", scope: "sheetset", kind: "cascade",
        source_property_id: "prop-major",
        cascade_options: [
          {source_item_id: "enum-road", values: ["东区", "西区"]},
          {source_item_id: "enum-gas", values: ["北区", "南区"]},
        ],
      },
      {
        property_id: "prop-route", name: "线路类型", scope: "sheet", kind: "enum",
        required: false, default_value: "道路",
        enum_items: [{item_id: "enum-route-road", value: "道路"}, {item_id: "enum-route-gas", value: "燃气"}],
      },
      {
        property_id: "prop-route-detail", name: "线路等级", scope: "sheet", kind: "cascade",
        source_property_id: "prop-route",
        cascade_options: [
          {source_item_id: "enum-route-road", values: ["城市道路", "公路", "通用"]},
          {source_item_id: "enum-route-gas", values: ["庭院管网", "长输管线", "通用"]},
        ],
      },
    ],
  };
}

function cascadeStandard(): CreationStandardInputs {
  return creationStandardInputs(
    {standardId: "00000000-0000-4000-8000-000000000046"},
    "市政燃气施工图",
    cascadeStandardDocument(),
    seedStandard().asset_options,
  );
}

function cascadeDraft(): CreationDraftState {
  const draft = seedDraft();
  return {
    ...draft,
    sheetset_values: {"prop-major": "道路", "prop-region": "东区"},
    groups: draft.groups.map((group, index) => ({
      ...group,
      sheet_values: {
        ...group.sheet_values,
        "prop-route": index === 1 ? "燃气" : "道路",
        "prop-route-detail": index === 1 ? "庭院管网" : index === 2 ? "通用" : "城市道路",
      },
    })),
  };
}

function cascadeApi(): CreationApi {
  const api = fakeCreationApi();
  api.seed = {draft: cascadeDraft(), standard: cascadeStandard()};
  return api;
}

function candidate(standardId: string): CreationStandardCandidate {
  return {
    standard_id: standardId,
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    available: true,
    reasons: [],
    asset_options: seedStandard(standardId).asset_options,
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
      standard_id: "00000000-0000-4000-8000-000000000046",
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
    evaluateSheetsetDerived: vi.fn(async () => ({draft_id: "draft-1", values: {}, diagnostics: []})),
  };
}

describe("createCreationStore", () => {
  it("resolves cascade choices from the current same-scope parent and disables without one", () => {
    const standard = cascadeStandard();
    const region = standard.sheetset_properties.find(property => property.property_id === "prop-region");
    expect(region?.kind).toBe("cascade");
    if (region?.kind !== "cascade") throw new Error("missing cascade fixture");

    expect(creationCascadeOptions(standard, region, {})).toEqual([]);
    expect(creationCascadeOptions(standard, region, {"prop-major": "道路"})).toEqual(["东区", "西区"]);
    expect(creationCascadeOptions(standard, region, {"prop-major": "燃气"})).toEqual(["北区", "南区"]);
  });

  it("clears dependent cascade values only on the changed object and copies the latest pair", () => {
    const store = createCreationStore(cascadeApi());
    store.setSheetsetValue("prop-major", "燃气");
    expect(store.sheetsetValues["prop-region"]).toBe("");

    store.setGroupSheetValue("group-1", "prop-route", "燃气");
    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("");
    expect(store.group("group-2").sheet_values["prop-route-detail"]).toBe("庭院管网");

    const copied = store.addGroup();
    expect(copied.sheet_values["prop-route"]).toBe("道路");
    expect(copied.sheet_values["prop-route-detail"]).toBe("通用");
  });

  it("clears cascades for only selected groups when batch changing their parent", () => {
    const store = createCreationStore(cascadeApi());
    store.batchUpdate(["group-1", "group-2"], "prop-route", {kind: "set", value: "道路"});

    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("城市道路");
    expect(store.group("group-2").sheet_values["prop-route-detail"]).toBe("");
    expect(store.group("group-3").sheet_values["prop-route-detail"]).toBe("通用");
  });

  it("rejects an invalid cascade batch atomically and applies values in the shared choice intersection", () => {
    const store = createCreationStore(cascadeApi());
    store.previewDigest = "digest-before-batch";
    store.canExecute = true;
    expect(store.batchUpdate(["group-1", "group-2"], "prop-route-detail", {kind: "set", value: "城市道路"})).toBe(false);

    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("城市道路");
    expect(store.group("group-2").sheet_values["prop-route-detail"]).toBe("庭院管网");
    expect(store.previewDigest).toBe("digest-before-batch");
    expect(store.canExecute).toBe(true);

    expect(store.batchUpdate(["group-1", "group-2"], "prop-route-detail", {kind: "set", value: "通用"})).toBe(true);
    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("通用");
    expect(store.group("group-2").sheet_values["prop-route-detail"]).toBe("通用");
    expect(store.previewDigest).toBeNull();

    store.setGroupSheetValue("group-2", "prop-route-detail", "旧线路值");
    expect(store.batchUpdate(["group-1", "group-2"], "prop-route-detail", {kind: "clear"})).toBe(true);
    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("");
    expect(store.group("group-2").sheet_values["prop-route-detail"]).toBe("");
  });

  it("preserves an invalid restored cascade value until the user clears it", async () => {
    const api = fakeCreationApi();
    const draft = cascadeDraft();
    draft.groups[0]!.sheet_values["prop-route-detail"] = "旧线路值";
    api.fetchDraft = vi.fn(async () => draft);
    api.fetchStandardDocument = vi.fn(async () => cascadeStandardDocument());
    const basePreview = await api.previewDraft("draft-1");
    api.previewDraft = vi.fn(async () => ({
      ...basePreview,
      executable: false,
      diagnostics: [{
        code: "STANDARD_CASCADE_VALUE_INVALID",
        message: "线路等级与线路类型不匹配",
        severity: "error",
        group_id: "group-1",
        property_id: "prop-route-detail",
      }],
    }));
    const store = createCreationStore(api);

    expect(await store.resumeDraft("draft-1")).toBe(true);
    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("旧线路值");
    expect(await store.preview()).toBe(true);
    expect(store.previewState?.diagnostics[0]).toMatchObject({
      code: "STANDARD_CASCADE_VALUE_INVALID",
      group_id: "group-1",
      property_id: "prop-route-detail",
    });

    store.setGroupSheetValue("group-1", "prop-route-detail", "");
    expect(store.group("group-1").sheet_values["prop-route-detail"]).toBe("");
  });

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

  it("同名图纸组独立保留且不标错，空图名仍提示错误", () => {
    const store = createCreationStore(fakeCreationApi());
    store.updateGroup("group-1", {title: "平面图", count: 2});
    store.updateGroup("group-2", {title: " 平面图 ", count: 3});

    expect(store.groupIssues("group-1")).toEqual([]);
    expect(store.groupIssues("group-2")).toEqual([]);
    expect(store.group("group-1").count).toBe(2);
    expect(store.group("group-2").count).toBe(3);
    store.updateGroup("group-1", {title: ""});
    expect(store.groupIssues("group-1")).toContain("title_empty");
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

  it("refreshDerived 把界面输入交给后端求值并写入 derivedValues（不失效预览）", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    api.evaluateSheetsetDerived = vi.fn(
      async (draftId: string, sheetsetValues: Record<string, string>): Promise<CreationDerivedEvaluation> => ({
        draft_id: draftId,
        values: sheetsetValues["prop-major"] === "燃气" ? {"prop-code": "RQ"} : {},
        diagnostics: [],
      }),
    );

    store.setSheetsetValue("prop-major", "燃气");
    await store.refreshDerived();

    expect(api.evaluateSheetsetDerived).toHaveBeenCalledWith("draft-1", {"prop-major": "燃气"});
    expect(store.derivedValues).toEqual({"prop-code": "RQ"});
    expect(store.derivedPending).toBe(false);
    // 只读求值不进入保存签名，也不失效预览会话
    expect(store.previewDigest).toBeNull();
  });

  it("refreshDerived 失败时保留既有结果并清除 pending", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    api.evaluateSheetsetDerived = vi.fn(async () => {
      throw new Error("NETWORK_DOWN");
    });
    store.derivedValues = {"prop-code": "RQ"};

    await store.refreshDerived();

    expect(store.derivedValues).toEqual({"prop-code": "RQ"});
    expect(store.derivedPending).toBe(false);
    expect(store.error).toBe("");
  });

  it("adoptDraft 替换草稿时清空旧派生值", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    store.derivedValues = {"prop-code": "RQ"};
    await store.resumeDraft("draft-1");
    expect(store.derivedValues).toEqual({});
  });

  it("clears incompatible inputs when the fixed standard is replaced", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    store.setSheetsetValue("prop-major", "建筑");
    api.createDraft = vi.fn(async (): Promise<CreationDraftState> => ({
      id: "draft-2",
      standard_id: "00000000-0000-4000-8000-000000000047",
      revision: 1,
      step: "project",
      target_path: "",
      sheetset_values: {},
      groups: [],
    }));
    api.fetchStandardDocument = vi.fn(async () => ({}));

    await store.chooseStandard(candidate("00000000-0000-4000-8000-000000000047"), {replace: true});

    expect(api.deleteDraft).toHaveBeenCalledWith("draft-1");
    expect(store.groups).toHaveLength(0);
    expect(store.sheetsetValues).toEqual({});
    expect(store.standard?.identity.standardId).toBe("00000000-0000-4000-8000-000000000047");
    expect(store.step).toBe("project");
    expect(store.previewDigest).toBeNull();
  });

  it("keeps an empty folder name empty instead of degrading to the parent directory", async () => {
    const api = fakeCreationApi();
    const base = await api.previewDraft("draft-1");
    const savedPaths: string[] = [];
    api.saveDraft = vi.fn(async (input: CreationSaveInput) => {
      savedPaths.push(input.targetPath);
      return {...seedDraft(), target_path: input.targetPath};
    });
    // 后端对空目标路径给 CREATION_TARGET_PATH_EMPTY 阻断诊断（前端不重算这条规则）
    api.previewDraft = vi.fn(async () => ({
      ...base,
      target_path: "",
      executable: false,
      diagnostics: [
        {code: "CREATION_TARGET_PATH_EMPTY", message: "项目目录不能为空", severity: "error", group_id: "", property_id: ""},
      ],
      preview_digest: "digest-empty",
    }));
    const store = createCreationStore(api);
    store.setParentPath("D:\\项目");
    store.setFolderName("");

    // 清空目录名不得变成「用上级目录当项目」：最终路径为空
    expect(store.targetPath()).toBe("");
    expect(await store.preview()).toBe(true);
    expect(savedPaths).toContain("");
    expect(store.canExecute).toBe(false);
    expect(await store.execute()).toBeNull();
    expect(api.executeDraft).not.toHaveBeenCalled();
  });
});
