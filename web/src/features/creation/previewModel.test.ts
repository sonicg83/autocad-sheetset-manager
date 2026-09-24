// 创建预览纯模型与预览会话单测（PLAN-DM-036 Task 9）。
// 覆盖按组属性单元格摘要（首张实际值 + 是否需要「…」）、动态属性列与诊断定位，
// 以及「输入或编号设置变化 → 旧摘要失效」的门禁。求值、编号与 DWG 命名一律以后端
// 预览响应为准，模型只做投影，不复制这些规则。
import {describe, expect, it, vi} from "vitest";
import type {Job} from "../../api/contracts";
import {createCreationStore} from "./store";
import {previewDiagnosticTarget, previewPropertyColumns, summarizeSheetValues} from "./previewModel";
import type {
  CreationApi,
  CreationDraftState,
  CreationImportOutcome,
  CreationPreview,
  CreationPreviewDiagnostic,
  CreationStandardInputs,
} from "./types";

function seedDraft(): CreationDraftState {
  return {
    id: "draft-1",
    standard_id: "szmedi.gas",
    standard_version: "2.1.0",
    revision: 2,
    step: "review",
    target_path: "D:\\项目\\新建项目",
    sheetset_values: {"prop-name": "滨河路改造工程"},
    groups: [
      {
        group_id: "group-1",
        created_order: 0,
        title: "平面图",
        count: 2,
        base_asset_id: "base-a",
        layout_asset_id: "layout-a",
        paper_layout: "A2",
        sheet_values: {"prop-stage": "施工图"},
      },
    ],
  };
}

function seedStandard(): CreationStandardInputs {
  return {
    identity: {standardId: "szmedi.gas", version: "2.1.0"},
    name: "市政燃气施工图",
    sheetset_properties: [
      {
        property_id: "prop-name",
        name: "工程名称",
        scope: "sheetset",
        kind: "text",
        required: true,
        default_value: "",
        options: [],
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
        options: [{item_id: "enum-cs", value: "施工图"}],
      },
    ],
    derived_properties: [
      {property_id: "prop-code", name: "图纸代号", scope: "sheet", kind: "composition"},
      {property_id: "prop-major-code", name: "专业代码", scope: "sheetset", kind: "mapping"},
    ],
    asset_options: [
      {asset_id: "base-a", kind: "base-template", label: "市政基础.dwt", layouts: []},
      {asset_id: "layout-a", kind: "layout-template", label: "市政图框.dwt", layouts: ["A2"]},
    ],
  };
}

function seedPreview(overrides: Partial<CreationPreview> = {}): CreationPreview {
  return {
    draft_id: "draft-1",
    revision: 2,
    standard_id: "szmedi.gas",
    standard_version: "2.1.0",
    standard_name: "市政燃气施工图",
    target_path: "D:\\项目\\新建项目",
    sheetset_values: {"prop-name": "滨河路改造工程"},
    group_count: 1,
    sheet_count: 2,
    dwg_count: 1,
    numbering: {sequence_field: "subset.sequence", digits: 2, start: 1},
    suffix: {enabled: false, suffix_type: 0, unnumbered_keywords: []},
    diagnostics: [],
    groups: [
      {
        group_id: "group-1",
        created_order: 0,
        title: "平面图",
        number_range: "01-02",
        title_range: "平面图",
        base_template: "市政基础.dwt",
        layout_template: "市政图框.dwt",
        paper_layout: "A2",
        dwg_name: "RQ-平面图.dwg",
        target_path: "D:\\项目\\新建项目\\RQ-平面图.dwg",
        sheet_count: 2,
        sheets: [
          {number: "01", title: "平面图", layout_name: "平面图-01", values: {"prop-stage": "施工图"}},
          {number: "02", title: "平面图", layout_name: "平面图-02", values: {"prop-stage": "竣工图"}},
        ],
        property_cells: {
          "prop-stage": {
            property_id: "prop-stage",
            first_value: "施工图",
            sheets: [
              {number: "01", value: "施工图"},
              {number: "02", value: "竣工图"},
            ],
          },
          "prop-code": {
            property_id: "prop-code",
            first_value: "P-01",
            sheets: [
              {number: "01", value: "P-01"},
              {number: "02", value: "P-01"},
            ],
          },
        },
      },
    ],
    executable: true,
    preview_digest: "digest-1",
    ...overrides,
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
    previewDraft: vi.fn(async () => seedPreview()),
    executeDraft: vi.fn(async () => ({id: "job-1", status: "QUEUED", workspace_id: null})),
  };
}

function diagnostic(overrides: Partial<CreationPreviewDiagnostic> = {}): CreationPreviewDiagnostic {
  return {code: "CREATION_GROUP_TITLE_EMPTY", message: "图名不能为空", severity: "error", group_id: "", property_id: "", ...overrides};
}

it("shows first sheet value and opens all values only when values differ", () => {
  const cell = summarizeSheetValues([{number: "01", value: "平面图-01"}, {number: "02", value: "平面图-02"}]);
  expect(cell.text).toBe("平面图-01");
  expect(cell.showDetails).toBe(true);
  expect(cell.rows).toHaveLength(2);
});

it("invalidates preview after a project setting changes", async () => {
  const store = createCreationStore(fakeCreationApi());
  await store.preview();
  store.invalidateForSettingsChange();
  expect(store.previewDigest).toBeNull();
  expect(store.canExecute).toBe(false);
});

describe("summarizeSheetValues", () => {
  it("keeps a single value without details when every sheet shares it", () => {
    const cell = summarizeSheetValues([{number: "01", value: "施工图"}, {number: "02", value: "施工图"}]);
    expect(cell.text).toBe("施工图");
    expect(cell.showDetails).toBe(false);
    expect(cell.rows).toHaveLength(2);
  });

  it("keeps the first value empty instead of inventing a placeholder", () => {
    const cell = summarizeSheetValues([{number: "01", value: ""}, {number: "02", value: "李工"}]);
    expect(cell.text).toBe("");
    expect(cell.showDetails).toBe(true);
    expect(cell.rows.map(row => row.value)).toEqual(["", "李工"]);
  });

  it("does not offer details for a group with a single sheet", () => {
    const cell = summarizeSheetValues([{number: "00", value: "施工图"}]);
    expect(cell.text).toBe("施工图");
    expect(cell.showDetails).toBe(false);
    expect(cell.rows).toHaveLength(1);
  });
});

describe("previewPropertyColumns", () => {
  it("projects the backend cell keys in response order with standard labels", () => {
    const columns = previewPropertyColumns(seedPreview(), seedStandard());
    expect(columns).toEqual([
      {property_id: "prop-stage", label: "图纸阶段"},
      {property_id: "prop-code", label: "图纸代号"},
    ]);
  });

  it("keeps an unknown property id visible instead of dropping its column", () => {
    const preview = seedPreview();
    const group = preview.groups[0]!;
    group.property_cells["prop-extra"] = {
      property_id: "prop-extra",
      first_value: "X",
      sheets: [{number: "01", value: "X"}],
    };
    const columns = previewPropertyColumns(preview, seedStandard());
    expect(columns.map(column => column.property_id)).toEqual(["prop-stage", "prop-code", "prop-extra"]);
    expect(columns[2]?.label).toBe("prop-extra");
  });

  it("has no columns without a preview response", () => {
    expect(previewPropertyColumns(null, seedStandard())).toEqual([]);
  });
});

describe("previewDiagnosticTarget", () => {
  it("points a group diagnostic at its row and the title control", () => {
    expect(previewDiagnosticTarget(diagnostic({group_id: "group-2"}))).toEqual({
      step: "groups",
      groupId: "group-2",
      propertyId: "",
      groupField: "title",
    });
  });

  it("points a sheet property diagnostic at the group row and property", () => {
    expect(
      previewDiagnosticTarget(diagnostic({code: "CREATION_ASSET_INVALID", group_id: "group-2", property_id: "prop-stage"})),
    ).toEqual({step: "groups", groupId: "group-2", propertyId: "prop-stage", groupField: ""});
  });

  it("points count and paper layout diagnostics at their controls", () => {
    expect(previewDiagnosticTarget(diagnostic({code: "CREATION_GROUP_COUNT_INVALID", group_id: "group-2"}))?.groupField).toBe("count");
    expect(previewDiagnosticTarget(diagnostic({code: "CREATION_PAPER_LAYOUT_INVALID", group_id: "group-2"}))?.groupField).toBe("paper");
  });

  it("splits the shared asset code into base and layout template by the resolved template", () => {
    const group = seedPreview().groups[0]!;
    const assetInvalid = diagnostic({code: "CREATION_ASSET_INVALID", group_id: group.group_id});
    // 基础模板已解析成功 ⇒ 缺的是布局模板
    expect(previewDiagnosticTarget(assetInvalid, group)?.groupField).toBe("layout");
    // 基础模板路径为空 ⇒ 缺的是基础模板；没有组信息时也回退到基础模板
    expect(previewDiagnosticTarget(assetInvalid, {...group, base_template: ""})?.groupField).toBe("base");
    expect(previewDiagnosticTarget(assetInvalid)?.groupField).toBe("base");
  });

  it("points a sheetset property diagnostic at the project field", () => {
    expect(
      previewDiagnosticTarget(diagnostic({code: "CREATION_REQUIRED_VALUE_MISSING", property_id: "prop-name"})),
    ).toEqual({step: "project", groupId: "", propertyId: "prop-name", groupField: ""});
  });

  it("points path and empty-group diagnostics at their stage", () => {
    expect(previewDiagnosticTarget(diagnostic({code: "CREATION_TARGET_PATH_EMPTY"}))).toEqual({
      step: "project",
      groupId: "",
      propertyId: "",
      groupField: "",
    });
    expect(previewDiagnosticTarget(diagnostic({code: "CREATION_GROUPS_EMPTY"}))).toEqual({
      step: "groups",
      groupId: "",
      propertyId: "",
      groupField: "",
    });
  });

  it("points an unavailable standard asset at the standard stage", () => {
    expect(previewDiagnosticTarget(diagnostic({code: "CREATION_ASSET_FILE_MISSING"}))).toEqual({
      step: "standard",
      groupId: "",
      propertyId: "",
      groupField: "",
    });
  });

  it("offers no jump for a diagnostic that has no input location", () => {
    expect(previewDiagnosticTarget(diagnostic({code: "DUPLICATE_LAYOUT_NAME"}))).toBeNull();
  });
});

describe("creation preview session", () => {
  it("stores the authoritative digest and executable flag", async () => {
    const store = createCreationStore(fakeCreationApi());
    await store.preview();
    expect(store.previewDigest).toBe("digest-1");
    expect(store.canExecute).toBe(true);
    expect(store.previewState?.group_count).toBe(1);
  });

  it("keeps the previous digest disabled when the backend reports blocking errors", async () => {
    const api = fakeCreationApi();
    api.previewDraft = vi.fn(async () =>
      seedPreview({executable: false, diagnostics: [diagnostic({group_id: "group-1"})]}),
    );
    const store = createCreationStore(api);
    await store.preview();
    expect(store.canExecute).toBe(false);
  });

  it("sends only the preview digest when executing", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    await store.preview();
    const job = await store.execute();
    expect(api.executeDraft).toHaveBeenCalledWith("draft-1", "digest-1");
    expect(job?.id).toBe("job-1");
  });

  it("marks execution in flight so the wizard cannot submit twice", async () => {
    const api = fakeCreationApi();
    let release = (): void => {};
    api.executeDraft = vi.fn(
      () =>
        new Promise<Job>(resolve => {
          release = () => resolve({id: "job-1", status: "QUEUED", workspace_id: null});
        }),
    );
    const store = createCreationStore(api);
    await store.preview();
    const inFlight = store.execute();
    expect(store.executePending).toBe(true);
    // 在途重复提交不得再次入队（同一目标目录不能同时跑两个创建任务）
    expect(await store.execute()).toBeNull();
    expect(api.executeDraft).toHaveBeenCalledTimes(1);
    release();
    await inFlight;
    expect(store.executePending).toBe(false);
  });

  it("does not execute without a valid preview", async () => {
    const api = fakeCreationApi();
    const store = createCreationStore(api);
    expect(await store.execute()).toBeNull();
    expect(api.executeDraft).not.toHaveBeenCalled();
  });

  it("drops the preview when any draft input changes", async () => {
    const store = createCreationStore(fakeCreationApi());
    await store.preview();
    store.setSheetsetValue("prop-name", "改名后工程");
    expect(store.previewDigest).toBeNull();
    expect(store.canExecute).toBe(false);
    expect(store.previewState).toBeNull();
  });

  it("keeps the draft and reports a readable error when the preview request fails", async () => {
    const api = fakeCreationApi();
    api.previewDraft = vi.fn(async () => {
      throw new Error("CREATION_TARGET_NOT_EMPTY: 目标目录非空");
    });
    const store = createCreationStore(api);
    expect(await store.preview()).toBe(false);
    expect(store.error).toContain("CREATION_TARGET_NOT_EMPTY");
    expect(store.draftId).toBe("draft-1");
  });
});
