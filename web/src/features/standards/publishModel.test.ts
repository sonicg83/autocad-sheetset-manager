// 发布门禁模型单测（PLAN-DM-042 / SPEC-DM-017 §7–§8）：
// 启用图幅与实际布局的包含比较、资产引用与未引用警告、发布诊断到六分区/定位目标的映射、
// 检查失败与标准错误分离、门禁判定。全部纯函数。
import {describe, expect, it} from "vitest";
import {
  PAPER_LAYOUT_MISSING_CODE,
  PAPER_LAYOUTS_EMPTY_CODE,
  assetReferences,
  buildPublishGate,
  declaredPaperLayouts,
  inspectionRecordMatches,
  inspectionRunIsCurrent,
  missingPaperLayouts,
  nonModelLayouts,
  recordInspection,
  recordInspectionState,
  recordInspectedAt,
  type InspectionRecord,
  type PublishReport,
} from "./publishModel";
import {toDraftDocument, type DraftAsset} from "./draftModel";
import type {AssetInspection} from "./types";

function layoutAsset(assetId: string, paperLayouts: string[], kind = "layout-template"): DraftAsset {
  return {
    asset_id: assetId,
    kind,
    file: `assets/${assetId}.dwg`,
    paper_layouts: paperLayouts,
  };
}

function documentWith(assets: DraftAsset[], overrides: Record<string, unknown> = {}) {
  return toDraftDocument({
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "3.0.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [
      {
        property_id: "prop-frame",
        name: "图幅",
        scope: "sheetset",
        kind: "enum",
        default_value: "A3",
        enum_items: [{item_id: "enum-a2", value: "A2"}, {item_id: "enum-a3", value: "A3"}],
      },
      {property_id: "prop-code", name: "专业代码", scope: "sheetset", kind: "text", default_value: "RQ"},
    ],
    dwg_naming: {
      segments: [{property_id: "prop-code"}, {literal: "-"}, {system_field: "subset.scope"}],
    },
    assets,
    numbering: {sequence_field: "subset.sequence", digits: 2},
    ...overrides,
  });
}

function inspection(assetId: string, layouts: string[], diagnostics: AssetInspection["diagnostics"] = []): AssetInspection {
  return {asset_id: assetId, kind: "layout-template", layouts, diagnostics};
}

/** 勾选 A2/A3，实际布局与勾选不一致（`A3 ` 多了一个空格）。 */
function reportWithLayouts({checked, actual}: {checked: string[]; actual: string[]}): PublishReport {
  return {
    document: documentWith([layoutAsset("layouts", checked)]),
    assets: [inspection("layouts", actual)],
  };
}

/** 有效但未被标准任何取值引用的布局资产：只应产生警告。 */
function reportWithUnusedAssetWarning(): PublishReport {
  return {
    document: documentWith([layoutAsset("unused-layouts", ["A5"])]),
    assets: [inspection("unused-layouts", ["A5"])],
  };
}

describe("启用图幅与实际布局", () => {
  it("只报告勾选但文件中缺失的布局，不修剪空白也不归一大小写", () => {
    expect(missingPaperLayouts(["A2", "A3"], ["A2", "A3"])).toEqual([]);
    expect(missingPaperLayouts(["A3"], ["A3 "])).toEqual(["A3"]);
    expect(missingPaperLayouts(["A3"], ["a3"])).toEqual(["A3"]);
    // 实际布局多于勾选只是未启用，不再是问题（包含即可）
    expect(missingPaperLayouts(["A2"], ["A2", "A4"])).toEqual([]);
  });

  it("过滤空勾选并从实际布局中排除 Model（勾选不去重、保持勾选顺序）", () => {
    expect(nonModelLayouts(["Model", "A2", "A3"])).toEqual(["A2", "A3"]);
    expect(declaredPaperLayouts(layoutAsset("layouts", ["A2", "A2", ""]))).toEqual(["A2", "A2"]);
  });
});

describe("buildPublishGate", () => {
  it("blocks publish for a checked paper layout missing from the file", () => {
    const gate = buildPublishGate(reportWithLayouts({checked: ["A2", "A3"], actual: ["Model", "A2", "A3 "]}));
    expect(gate.canPublish).toBe(false);
    expect(gate.blockingErrors).toHaveLength(1);
    expect(gate.blockingErrors[0].code).toBe(PAPER_LAYOUT_MISSING_CODE);
    expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "layouts", layout: "A3"});
    expect(gate.blockingErrors[0].params).toEqual({assetId: "layouts", layout: "A3"});
  });

  it("blocks publish when a layout template enables no paper layout before inspection", () => {
    const gate = buildPublishGate({
      document: documentWith([layoutAsset("empty", [])]),
      assets: [],
    });
    expect(gate.canPublish).toBe(false);
    expect(gate.blockingErrors.map(issue => issue.code)).toEqual([PAPER_LAYOUTS_EMPTY_CODE]);
    expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "empty"});
  });

  it("allows publish with warnings only", () => {
    const gate = buildPublishGate(reportWithUnusedAssetWarning());
    expect(gate.canPublish).toBe(true);
    expect(gate.warnings).toHaveLength(1);
    expect(gate.warnings[0].code).toBe("STANDARD_ASSET_UNREFERENCED");
    expect(gate.warnings[0].target).toEqual({section: "assets", assetId: "unused-layouts"});
    expect(gate.counts).toEqual({errors: 0, warnings: 1, failures: 0});
  });

  it("accepts a clean report", () => {
    const gate = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A2", "A3"])]),
      assets: [inspection("layouts", ["Model", "A2", "A3"])],
    });
    expect(gate.canPublish).toBe(true);
    expect(gate.blockingErrors).toEqual([]);
    expect(gate.warnings).toEqual([]);
  });

  it("maps publish diagnostics to the owning section and target", () => {
    const document = documentWith([], {
      properties: [
        {
          property_id: "prop-frame",
          name: "图幅",
          scope: "sheetset",
          kind: "enum",
          enum_items: [{item_id: "enum-a2", value: "A2"}, {item_id: "enum-a3", value: "A3"}],
        },
        {
          property_id: "prop-code",
          name: "专业代码",
          scope: "sheetset",
          kind: "mapping",
          source_property_id: "prop-frame",
          mapping: [{item_id: "enum-a2", value: "RQ"}],
          confirmed_source_items: [["enum-a2", "A2"], ["enum-a3", "A3"]],
        },
        {
          property_id: "prop-label",
          name: "图签",
          scope: "sheetset",
          kind: "composition",
          segments: [{property_id: "prop-code"}, {literal: " 平面图"}],
        },
      ],
      dwg_naming: {segments: [{property_id: "prop-code"}, {literal: "-"}, {system_field: "subset.scope"}]},
    });
    const gate = buildPublishGate({document, assets: []});
    expect(gate.canPublish).toBe(false);
    expect(gate.blockingErrors.map(issue => [issue.code, issue.target.section, issue.target.itemId ?? null])).toEqual([
      ["STANDARD_MAPPING_TARGET_EMPTY", "derived", "enum-a3"],
    ]);
    // 插值参数按稳定键给出（视图经语言包渲染），属性名与枚举项 ID 都可定位
    expect(gate.blockingErrors[0].params).toEqual({
      propertyId: "prop-code",
      propertyName: "专业代码",
      itemId: "enum-a3",
    });
  });

  it("routes reserved names to the ordinary section and naming tokens to the naming section", () => {
    const document = documentWith([], {
      properties: [
        {property_id: "prop-reserved", name: "sheet.number", scope: "sheetset", kind: "text"},
      ],
      dwg_naming: {segments: [{literal: "图签.dwg"}]},
    });
    const gate = buildPublishGate({document, assets: []});
    expect(gate.blockingErrors.map(issue => [issue.code, issue.target.section])).toEqual([
      ["STANDARD_PROPERTY_NAME_RESERVED", "ordinary"],
    ]);
    // 文件名模板风险只提示不阻断（计划 Task 8 Step 5：前端只提示，发布以后端逐项目校验为准）
    expect(gate.warnings.map(issue => [issue.code, issue.target.section])).toEqual([
      ["DWG_NAMING_UNIQUENESS_UNPROVEN", "dwgNaming"],
      ["DWG_NAME_EXTENSION_FORBIDDEN", "dwgNaming"],
    ]);
  });

  it("treats template-level file name risks as warnings that do not block publishing", () => {
    const document = documentWith([], {
      dwg_naming: {
        segments: [{property_id: "prop-code"}, {literal: "-图签.dwg-"}, {system_field: "subset.scope"}],
      },
    });
    const gate = buildPublishGate({document, assets: []});
    expect(gate.canPublish).toBe(true);
    expect(gate.blockingErrors).toEqual([]);
    expect(gate.warnings.map(issue => [issue.code, issue.target.section])).toEqual([
      ["DWG_NAME_EXTENSION_FORBIDDEN", "dwgNaming"],
    ]);
  });

  it("passes the duplicated source name to the {source} message placeholder", () => {
    const document = documentWith([], {
      properties: [
        {property_id: "prop-major", name: "专业", scope: "sheetset", kind: "enum", default_value: "燃气", enum_items: [{item_id: "enum-gas", value: "燃气"}]},
        {property_id: "prop-code", name: "专业代码", scope: "sheetset", kind: "mapping", source_property_id: "prop-major", mapping: [{item_id: "enum-gas", value: "RQ"}]},
        {property_id: "prop-dup", name: "重复映射", scope: "sheetset", kind: "mapping", source_property_id: "prop-major", mapping: [{item_id: "enum-gas", value: "RQ2"}]},
      ],
    });
    const gate = buildPublishGate({document, assets: []});
    const issue = gate.blockingErrors.find(item => item.code === "STANDARD_MAPPING_SOURCE_DUPLICATE");
    expect(issue?.params.source).toBe("专业");
    expect(issue?.params.field).toBe("专业");
  });

  it("keeps a failed inspection separate from standard errors", () => {
    const gate = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A3"])]),
      assets: [],
      inspectionFailures: [{assetId: "layouts", message: "AUTO_CAD_NOT_READY"}],
    });
    expect(gate.canPublish).toBe(false);
    expect(gate.blockingErrors).toEqual([]);
    expect(gate.inspectionFailures).toEqual([{assetId: "layouts", message: "AUTO_CAD_NOT_READY"}]);
    expect(gate.counts).toEqual({errors: 0, warnings: 0, failures: 1});
  });

  it("skips backend paper-layout diagnostics and derives the diff locally with layout targeting", () => {
    // 后端聚合诊断不带 layout 定位：前端跳过它，按勾选与实际布局本地推导，避免重复
    const mismatch = {
      document: documentWith([layoutAsset("layouts", ["A3"])]),
      assets: [inspection("layouts", ["Model"], [{code: PAPER_LAYOUT_MISSING_CODE, severity: "error" as const, message: "启用图幅 'A3' 不在文件实际布局中"}])],
    };
    const gate = buildPublishGate(mismatch);
    expect(gate.blockingErrors).toHaveLength(1);
    expect(gate.blockingErrors[0].code).toBe(PAPER_LAYOUT_MISSING_CODE);
    expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "layouts", layout: "A3"});
    expect(gate.blockingErrors[0].params).toEqual({assetId: "layouts", layout: "A3"});
  });

  it("reports asset file missing and CAD capability missing as blocking asset errors", () => {
    const gate = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A3"])]),
      assets: [inspection("layouts", [], [
        {code: "STANDARD_ASSET_FILE_MISSING", severity: "error", message: "文件不在草稿中"},
        {code: "STANDARD_CAD_CAPABILITY_MISSING", severity: "error", message: "AutoCAD 未配置"},
      ])],
    });
    expect(gate.blockingErrors.map(issue => [issue.code, issue.target.section, issue.target.assetId])).toEqual([
      ["STANDARD_ASSET_FILE_MISSING", "assets", "layouts"],
      ["STANDARD_CAD_CAPABILITY_MISSING", "assets", "layouts"],
      [PAPER_LAYOUT_MISSING_CODE, "assets", "layouts"],
    ]);
  });
});

describe("检查结果绑定已保存草稿（PLAN-DM-040 Task 4，F06/F07）", () => {
  const SNAPSHOT = '{"standard_id":"szmedi.gas","assets":[]}';

  function record(overrides: Partial<InspectionRecord> = {}): InspectionRecord {
    return {
      draftId: "draft-1",
      documentSnapshot: SNAPSHOT,
      inspectedAt: "2026-09-24 10:00",
      inspections: [inspection("layouts", ["Model", "A2"])],
      failures: [{assetId: "broken", message: "CAD 未就绪"}],
      ...overrides,
    };
  }

  it("只在草稿身份与已保存快照都匹配时把结果当作当前结果", () => {
    expect(inspectionRecordMatches(record(), "draft-1", SNAPSHOT)).toBe(true);
    // 切换草稿：旧草稿的结果不得当作新草稿的结果
    expect(inspectionRecordMatches(record(), "draft-2", SNAPSHOT)).toBe(false);
    // 编辑后过期：缓冲变化后的结果不再对应当前文档
    expect(inspectionRecordMatches(record(), "draft-1", `${SNAPSHOT} `)).toBe(false);
    expect(inspectionRecordMatches(null, "draft-1", SNAPSHOT)).toBe(false);
  });

  it("未收到检查结果时是「未检查」，不是「未发现问题」", () => {
    expect(recordInspectionState(null, "layouts")).toBe("unchecked");
    expect(recordInspectionState(record({inspections: []}), "layouts")).toBe("unchecked");
    expect(recordInspectionState(record(), "layouts")).toBe("passed");
    expect(recordInspectionState(record(), "broken")).toBe("error");
    expect(
      recordInspectionState(
        record({
          inspections: [
            inspection("layouts", [], [
              {code: "STANDARD_ASSET_FILE_MISSING", severity: "error", message: "文件不在草稿中"},
            ]),
          ],
        }),
        "layouts",
      ),
    ).toBe("failed");
    expect(recordInspection(record(), "missing-asset")).toBeUndefined();
    expect(recordInspectedAt(null)).toBe("");
  });

  it("检查运行只有代次、草稿身份与快照都匹配才允许提交", () => {
    const current = {generation: 2, draftId: "draft-1", documentSnapshot: SNAPSHOT};
    expect(inspectionRunIsCurrent({...current}, current)).toBe(true);
    // 乱序返回：旧代次的结果不覆盖新状态
    expect(inspectionRunIsCurrent({...current, generation: 1}, current)).toBe(false);
    // 检查期间继续编辑：快照已变，结果不得提交
    expect(inspectionRunIsCurrent({...current, documentSnapshot: `${SNAPSHOT} `}, current)).toBe(false);
    // 检查期间切换草稿：身份已变，结果不得提交
    expect(inspectionRunIsCurrent({...current, draftId: "draft-2"}, current)).toBe(false);
  });

  it("过期记录不得作为当前结果参与发布门禁", () => {
    // 组件把过期记录折算为 null 后再建门禁：勾选图幅的资产回到“未检查 → 勾选全部缺失”阻断
    const stale = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A2"])]),
      assets: [],
    });
    expect(stale.blockingErrors.map(issue => issue.code)).toEqual([PAPER_LAYOUT_MISSING_CODE]);
    // 同一份文档带当前结果时不再阻断
    const fresh = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A2"])]),
      assets: [inspection("layouts", ["Model", "A2"])],
    });
    expect(fresh.canPublish).toBe(true);
  });
});

describe("assetReferences", () => {
  it("finds every place an enabled paper layout is used by the standard", () => {
    const asset = layoutAsset("layouts", ["A3"]);
    const document = documentWith([asset], {
      properties: [
        {
          property_id: "prop-frame",
          name: "图幅",
          scope: "sheetset",
          kind: "enum",
          enum_items: [{item_id: "enum-a3", value: "A3"}, {item_id: "enum-a4", value: "A4"}],
        },
        {
          property_id: "prop-code",
          name: "专业代码",
          scope: "sheetset",
          kind: "mapping",
          source_property_id: "prop-frame",
          mapping: [{item_id: "enum-a3", value: "A3"}, {item_id: "enum-a4", value: "RQ"}],
          confirmed_source_items: [["enum-a3", "A3"], ["enum-a4", "A4"]],
        },
        {
          property_id: "prop-label",
          name: "图签",
          scope: "sheetset",
          kind: "composition",
          segments: [{literal: "A3"}, {property_id: "prop-code"}],
        },
      ],
      dwg_naming: {segments: [{literal: "A3"}, {system_field: "subset.scope"}]},
    });
    expect(assetReferences(document, asset).map(reference => reference.kind)).toEqual([
      "property-enum",
      "mapping-target",
      "segment-literal",
      "segment-literal",
    ]);
    expect(assetReferences(document, layoutAsset("other", ["A9"]))).toEqual([]);
  });

  it("keeps the unreferenced warning off when the standard has nothing to reference from", () => {
    const gate = buildPublishGate({
      document: documentWith([layoutAsset("layouts", ["A5"])], {
        properties: [{property_id: "prop-code", name: "专业代码", scope: "sheetset", kind: "text", default_value: "RQ"}],
        dwg_naming: {segments: [{property_id: "prop-code"}, {system_field: "subset.scope"}]},
      }),
      assets: [inspection("layouts", ["A5"])],
    });
    expect(gate.canPublish).toBe(true);
    expect(gate.warnings).toEqual([]);
  });
});
