// 标准草稿编辑模型单测（PLAN-DM-035 Task 9 / SPEC-DM-016 §7）：
// 映射表批量粘贴与行级定位、字段组合与 DWG 命名的纯展示预览、结构诊断
// （未知引用/循环/非法格式码/重复目标）。全部为纯函数，无 Vue 与网络依赖。
import {describe, expect, it} from "vitest";
import {
  buildMappingRows,
  parsePropertyCsv,
  renderCompositionPreview,
  toDraftDocument,
  validateDraftStructure,
  validateMapping,
} from "./draftModel";
import type {DraftRule, DraftSegment} from "./draftModel";

/** 目标字段无枚举约束（allowed 为空 = 接受任意非空目标值）。 */
function codeRule() {
  return {allowed: [] as string[]};
}

function mappingRule(overrides: Partial<DraftRule> = {}): DraftRule {
  return {
    rule_id: "specialty-code",
    kind: "mapping",
    target: "sheetset.专业代码",
    source: "sheetset.专业名称",
    allowed: [],
    table: [],
    segments: [],
    ...overrides,
  };
}

function composeRule(overrides: Partial<DraftRule> = {}): DraftRule {
  return {
    rule_id: "dwg-name",
    kind: "naming",
    target: "derived.dwg_name",
    allowed: [],
    table: [],
    segments: [],
    ...overrides,
  };
}

function propertyDocument(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "3.0.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [{name: "专业名称", scope: "sheetset"}, {name: "专业代码", scope: "sheetset"}],
    rules: [],
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2},
    ...overrides,
  };
}

describe("buildMappingRows", () => {
  it("imports many specialty mappings from one tab separated clipboard block", () => {
    const rows = buildMappingRows("燃气\tRQ\n建筑\tJZ\n结构\tJG\n给排水\tGPS");
    expect(rows).toHaveLength(4);
    expect(rows[0]).toEqual({source: "燃气", target: "RQ"});
    expect(rows[3]).toEqual({source: "给排水", target: "GPS"});
  });

  it("accepts comma separated CSV, trimmed cells and skips blank lines", () => {
    expect(buildMappingRows(" 燃气 , RQ \n\n建筑,JZ\n")).toEqual([
      {source: "燃气", target: "RQ"},
      {source: "建筑", target: "JZ"},
    ]);
  });

  it("keeps partially filled rows so the editor can locate the empty cell", () => {
    expect(buildMappingRows("燃气\tRQ\n建筑\t")).toEqual([
      {source: "燃气", target: "RQ"},
      {source: "建筑", target: ""},
    ]);
  });
});

describe("validateMapping", () => {
  it("locates duplicate source values by row and uncovered source values without a row", () => {
    const diagnostics = validateMapping(
      [{source: "燃气", target: "RQ"}, {source: "燃气", target: "GAS"}],
      ["燃气", "建筑"],
      codeRule(),
    );
    expect(diagnostics.map(item => [item.code, item.row])).toEqual([
      ["STANDARD_MAPPING_SOURCE_DUPLICATE", 2],
      ["STANDARD_MAPPING_SOURCE_UNCOVERED", null],
    ]);
  });

  it("reports empty cells and target values outside the target enum", () => {
    const diagnostics = validateMapping(
      [{source: "燃气", target: "RQ"}, {source: "建筑", target: ""}, {source: "结构", target: "XX"}],
      ["燃气", "建筑", "结构"],
      {allowed: ["RQ", "JZ"]},
    );
    expect(diagnostics.map(item => [item.code, item.row])).toEqual([
      ["STANDARD_MAPPING_EMPTY_CELL", 2],
      ["STANDARD_MAPPING_TARGET_INVALID", 3],
    ]);
  });

  it("accepts a unique and complete mapping table", () => {
    expect(
      validateMapping(
        [{source: "燃气", target: "RQ"}, {source: "建筑", target: "JZ"}],
        ["燃气", "建筑"],
        {allowed: ["RQ", "JZ"]},
      ),
    ).toEqual([]);
  });
});

describe("renderCompositionPreview", () => {
  const segments: DraftSegment[] = [
    {field: "sheetset.专业代码"},
    {field: "subset.sequence", format: "3"},
    {literal: " "},
    {field: "subset.name"},
    {field: "derived.range"},
  ];

  it("renders field tokens, fixed text and zero padded sequence tokens", () => {
    const preview = renderCompositionPreview(segments, {
      "sheetset.专业代码": "RQ",
      "subset.sequence": "3",
      "subset.name": "总平面图",
      "derived.range": "01-05",
    });
    expect(preview.text).toBe("RQ003 总平面图01-05");
    expect(preview.diagnostics).toEqual([]);
    expect(preview.parts).toEqual(["RQ", "003", " ", "总平面图", "01-05"]);
  });

  it("keeps the remaining parts visible while marking a missing sample value", () => {
    const preview = renderCompositionPreview(segments, {"sheetset.专业代码": "RQ"});
    expect(preview.diagnostics.map(item => item.code)).toEqual([
      "STANDARD_RULE_SOURCE_MISSING",
      "STANDARD_RULE_SOURCE_MISSING",
      "STANDARD_RULE_SOURCE_MISSING",
    ]);
    expect(preview.parts[0]).toBe("RQ");
  });

  it("flags illegal format codes, unknown references and literal format codes", () => {
    const preview = renderCompositionPreview(
      [{field: "sheetset.专业代码", format: "99"}, {field: "sheetset.不存在"}, {literal: "x", format: "2"}],
      {"sheetset.专业代码": "RQ", "sheetset.不存在": "v"},
      {knownFields: ["sheetset.专业代码"]},
    );
    expect(preview.diagnostics.map(item => item.code)).toEqual([
      "STANDARD_RULE_FORMAT_INVALID",
      "STANDARD_RULE_FIELD_UNKNOWN",
      "STANDARD_RULE_FORMAT_INVALID",
    ]);
  });
});

describe("validateDraftStructure", () => {
  it("accepts a mapping followed by a composition that consumes its target", () => {
    const document = toDraftDocument(propertyDocument({
      rules: [
        mappingRule({table: [["燃气", "RQ"]]}),
        composeRule({segments: [{field: "sheetset.专业代码"}, {field: "subset.sequence", format: "2"}]}),
      ],
    }));
    expect(validateDraftStructure(document)).toEqual([]);
  });

  it("locates unknown references, duplicated targets and indirect cycles", () => {
    const unknown = toDraftDocument(propertyDocument({
      rules: [mappingRule({source: "sheetset.未定义", table: [["燃气", "RQ"]]})],
    }));
    expect(validateDraftStructure(unknown).map(item => [item.code, item.ruleId])).toEqual([
      ["STANDARD_RULE_FIELD_UNKNOWN", "specialty-code"],
    ]);

    const duplicated = toDraftDocument(propertyDocument({
      rules: [mappingRule({table: [["燃气", "RQ"]]}), mappingRule({rule_id: "other", table: [["建筑", "JZ"]]})],
    }));
    expect(validateDraftStructure(duplicated).map(item => [item.code, item.ruleId])).toEqual([
      ["STANDARD_RULE_TARGET_DUPLICATE", "other"],
    ]);

    const cycle = toDraftDocument(propertyDocument({
      rules: [
        composeRule({rule_id: "a", target: "derived.a", segments: [{field: "derived.b"}]}),
        composeRule({rule_id: "b", target: "derived.b", segments: [{field: "derived.a"}]}),
      ],
    }));
    const codes = validateDraftStructure(cycle).map(item => item.code);
    expect(codes).toContain("STANDARD_RULE_CYCLE");
  });

  it("flags basic identity, property and asset problems before saving", () => {
    const document = toDraftDocument(propertyDocument({
      standard_id: "Bad Id",
      version: "3.0",
      supported_cad_versions: [],
      properties: [{name: "  ", scope: "unknown"}],
      assets: [
        {asset_id: "layouts", kind: "layout-template", files: [{path: "../escape.dwg", role: "A3"}]},
        {asset_id: "layouts", kind: "wrong-kind", files: []},
      ],
    }));
    expect(validateDraftStructure(document).map(item => [item.code, item.field])).toEqual([
      ["STANDARD_ID_INVALID", "Bad Id"],
      ["STANDARD_VERSION_INVALID", "3.0"],
      ["STANDARD_CAD_VERSIONS_INVALID", undefined],
      ["STANDARD_PROPERTY_INVALID", "unknown.  "],
      ["STANDARD_SCOPE_INVALID", "unknown.  "],
      ["STANDARD_ASSET_PATH_INVALID", "layouts"],
      ["STANDARD_ASSET_DUPLICATE", "layouts"],
      ["STANDARD_ASSET_KIND_INVALID", "layouts"],
    ]);
  });

  it("flags illegal format codes and empty mapping tables", () => {
    const document = toDraftDocument(propertyDocument({
      rules: [mappingRule({table: []}), composeRule({segments: [{field: "subset.sequence", format: "003"}]})],
    }));
    expect(validateDraftStructure(document).map(item => [item.code, item.ruleId])).toEqual([
      ["STANDARD_RULE_INVALID", "specialty-code"],
      ["STANDARD_RULE_FORMAT_INVALID", "dwg-name"],
    ]);
  });
});

describe("parsePropertyCsv", () => {
  it("imports property definitions and skips rows without a field key", () => {
    expect(parsePropertyCsv("专业名称,sheetset,是,,燃气|建筑,专业名称\n,,,\n专业代码,sheetset,否,RQ,,\n")).toEqual([
      {name: "专业名称", scope: "sheetset", required: true, default_value: "", enum_values: ["燃气", "建筑"], description: "专业名称"},
      {name: "专业代码", scope: "sheetset", required: false, default_value: "RQ", enum_values: [], description: ""},
    ]);
  });

  it("falls back to the sheetset scope for unknown scopes", () => {
    expect(parsePropertyCsv("名称,unknown,no")[0].scope).toBe("sheetset");
  });
});

describe("toDraftDocument", () => {
  it("normalizes the editable arrays while preserving unknown fields", () => {
    const draft = toDraftDocument({
      schema_version: 1,
      standard_id: "szmedi.gas",
      version: "3.0.0",
      name: "市政燃气施工图",
      supported_cad_versions: ["2020"],
      properties: [{name: "专业名称", scope: "sheetset", enum_values: ["燃气", "建筑"]}],
      rules: [],
      assets: [],
      numbering: {sequence_field: "subset.sequence", digits: 2},
      future_extension: {keep: true},
    });
    expect(draft.future_extension).toEqual({keep: true});
    expect(draft.properties).toEqual([
      {name: "专业名称", scope: "sheetset", required: false, default_value: "", enum_values: ["燃气", "建筑"], description: ""},
    ]);
    expect(draft.numbering).toEqual({sequence_field: "subset.sequence", digits: 2, start: 1});
    expect(draft.assets).toEqual([]);
    expect(draft.dependencies).toEqual([]);
  });
});
