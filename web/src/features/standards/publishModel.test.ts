// 发布门禁模型单测（PLAN-DM-038 Task 5 / SPEC-DM-017 §7–§8）：
// 布局严格匹配、资产引用与未引用警告、发布诊断到六分区/定位目标的映射、
// 检查失败与标准错误分离、门禁判定。全部纯函数。
import {describe, expect, it} from "vitest";
import {
  assetReferences,
  buildPublishGate,
  compareLayouts,
  declaredRoles,
  nonModelLayouts,
  type PublishReport,
} from "./publishModel";
import {toDraftDocument, type DraftAsset} from "./draftModel";
import type {AssetInspection} from "./types";

function layoutAsset(assetId: string, roles: string[], kind = "layout-template"): DraftAsset {
  return {
    asset_id: assetId,
    kind,
    files: roles.map((role, index) => ({path: `assets/${assetId}-${index}.dwg`, role})),
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

/** 声明 A2/A3，实际布局与声明严格不一致（`A3 ` 多了一个空格）。 */
function reportWithLayouts({declared, actual}: {declared: string[]; actual: string[]}): PublishReport {
  return {
    document: documentWith([layoutAsset("layouts", declared)]),
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

describe("compareLayouts", () => {
  it("matches paper layouts strictly without trimming or case folding", () => {
    expect(compareLayouts(["A2", "A3"], ["A2", "A3"])).toEqual({missing: [], extra: []});
    expect(compareLayouts(["A3"], ["A3 "])).toEqual({missing: ["A3"], extra: ["A3 "]});
    expect(compareLayouts(["A3"], ["a3"])).toEqual({missing: ["A3"], extra: ["a3"]});
  });

  it("excludes the Model layout from paper matching", () => {
    expect(nonModelLayouts(["Model", "A2", "A3"])).toEqual(["A2", "A3"]);
    expect(declaredRoles(layoutAsset("layouts", ["A2", "A2", ""]))).toEqual(["A2"]);
  });
});

describe("buildPublishGate", () => {
  it("blocks publish for a missing exact paper layout", () => {
    const gate = buildPublishGate(reportWithLayouts({declared: ["A2", "A3"], actual: ["A2", "A3 "]}));
    expect(gate.canPublish).toBe(false);
    expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "layouts", layout: "A3"});
    expect(gate.blockingErrors[0].code).toBe("STANDARD_LAYOUT_NAME_MISMATCH");
    // 未声明的实际布局同样阻断（歧义布局），并带精确名称
    expect(gate.blockingErrors[1].target).toEqual({section: "assets", assetId: "layouts", layout: "A3 "});
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

  it("keeps backend diagnostics but does not duplicate a derived layout diff", () => {
    const mismatch = {
      document: documentWith([layoutAsset("layouts", ["A3"])]),
      assets: [inspection("layouts", ["A3 "], [{code: "STANDARD_LAYOUT_NAME_MISMATCH", severity: "error" as const, message: "声明图幅 'A3' 与实际布局不一致"}])],
    };
    expect(buildPublishGate(mismatch).blockingErrors.map(issue => issue.code)).toEqual([
      "STANDARD_LAYOUT_NAME_MISMATCH",
      "STANDARD_LAYOUT_NAME_MISMATCH",
    ]);

    // 前端无法从聚合布局推出差异（同一资产多文件、某文件读取为空）时保留后端诊断
    const opaque = {
      document: documentWith([layoutAsset("layouts", ["A3"])]),
      assets: [inspection("layouts", ["A3"], [{code: "STANDARD_LAYOUT_NAME_MISMATCH", severity: "error" as const, message: "读取结果为空"}])],
    };
    const gate = buildPublishGate(opaque);
    expect(gate.blockingErrors).toHaveLength(1);
    expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "layouts"});
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
      ["STANDARD_LAYOUT_NAME_MISMATCH", "assets", "layouts"],
    ]);
  });
});

describe("assetReferences", () => {
  it("finds every place a declared paper layout is used by the standard", () => {
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
