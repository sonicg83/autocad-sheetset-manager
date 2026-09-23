// 标准草稿编辑模型测试（PLAN-DM-038 Task 5）：判别联合、反向引用与两段门禁诊断。
import {describe, expect, it} from "vitest";

import {
  EDITOR_SECTIONS,
  blankStandardDocument,
  defaultDwgNamingSegments,
  type DraftAsset,
  type DraftDocument,
  type PreviewSamples,
  compositionFields,
  draftDiagnostics,
  dwgNamingFields,
  parsePropertyCsv,
  publishIssues,
  referencesTo,
  renderDwgNamingPreview,
  toDraftDocument,
} from "./draftModel";

function newSchemaDocument(): Record<string, unknown> {
  return {
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "0.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2016", "2020"],
    release_notes: "初版说明",
    properties: [
      {
        property_id: "prop-major",
        name: "专业",
        previous_names: [],
        scope: "sheetset",
        kind: "enum",
        required: false,
        default_value: "",
        description: "",
        enum_items: [{item_id: "enum-gas", value: "燃气"}],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        previous_names: [],
        scope: "sheetset",
        kind: "mapping",
        required: false,
        default_value: "",
        description: "",
        source_property_id: "prop-major",
        mapping: [{item_id: "enum-gas", value: "RQ"}],
        confirmed_source_items: [["enum-gas", "燃气"]],
      },
    ],
    dwg_naming: {
      segments: [
        {property_id: "prop-code"},
        {literal: "-"},
        {system_field: "subset.scope"},
        {literal: " "},
        {system_field: "subset.name"},
      ],
    },
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2},
    dependencies: [],
  };
}

function draftDocument(): DraftDocument {
  return toDraftDocument(newSchemaDocument());
}

/** 示例取样文本由视图经语言包提供；测试直接给出固定文案。 */
const SAMPLES: PreviewSamples = {
  subsetName: "示例子集",
  sheetNumber: "001",
  sheetTitle: "示例图名",
  placeholder: "示例",
};

function codes(items: Array<{code: string}>): string[] {
  return items.map(item => item.code);
}

function withProperty(document: DraftDocument, property: Record<string, unknown>): DraftDocument {
  return {...document, properties: [...document.properties, toDraftDocument({properties: [property]}).properties[0]!]};
}

function withEnumValues(document: DraftDocument, items: Array<{item_id: string; value: string}>, confirmed: Array<[string, string]>): DraftDocument {
  return {
    ...document,
    properties: document.properties.map(property => {
      if (property.property_id === "prop-major" && property.kind === "enum") {
        return {...property, enum_items: items};
      }
      if (property.property_id === "prop-code" && property.kind === "mapping") {
        return {...property, confirmed_source_items: confirmed};
      }
      return property;
    }),
  };
}

describe("draft model", () => {
  it("keeps ids and separates ordinary from derived properties", () => {
    const draft = toDraftDocument(newSchemaDocument());
    expect(draft.properties.map(item => [item.property_id, item.kind])).toEqual([
      ["prop-major", "enum"],
      ["prop-code", "mapping"],
    ]);
    expect(referencesTo(draft, "prop-major")).toEqual([{kind: "mapping", ownerId: "prop-code"}]);
  });

  it("preserves unknown top level fields and the default dwg naming template", () => {
    const draft = draftDocument();
    expect(draft.release_notes).toBe("初版说明");
    expect(draft.dwg_naming.segments).toHaveLength(5);
    expect(EDITOR_SECTIONS.map(section => section.id)).toEqual([
      "basic", "ordinary", "derived", "dwgNaming", "assets", "publish",
    ]);
  });

  it("enumerates composition and dwg naming tokens with their segment index", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-label",
      name: "图签",
      scope: "sheet",
      kind: "composition",
      segments: [{property_id: "prop-code"}, {literal: " "}, {system_field: "sheet.number"}],
    });
    expect(referencesTo(document, "prop-code")).toEqual([
      {kind: "composition", ownerId: "prop-label", segmentIndex: 0},
      {kind: "dwgNaming", ownerId: "", segmentIndex: 0},
    ]);
    expect(referencesTo(document, "prop-label")).toEqual([]);
  });

  it("lets incomplete drafts save while the publish gate still reports them", () => {
    const document = withEnumValues(
      draftDocument(),
      [{item_id: "enum-gas", value: "燃气"}, {item_id: "enum-water", value: "给水"}],
      [["enum-gas", "燃气"]],
    );
    expect(draftDiagnostics(document)).toEqual([]);
    expect(codes(publishIssues(document))).toEqual([
      "STANDARD_MAPPING_TARGET_EMPTY",
      "STANDARD_MAPPING_CONFIRMATION_REQUIRED",
    ]);
  });

  it("reports global name conflicts across scopes and history", () => {
    const padded = withProperty(draftDocument(), {
      property_id: "prop-sheet", name: " 专业 ", scope: "sheet", kind: "text",
    });
    expect(codes(publishIssues(padded))).toEqual(["STANDARD_PROPERTY_NAME_DUPLICATE"]);

    const history = withProperty(draftDocument(), {
      property_id: "prop-renamed", name: "专业编号", scope: "sheet", kind: "text",
    });
    const withHistory: DraftDocument = {
      ...history,
      properties: history.properties.map(property =>
        property.property_id === "prop-code" ? {...property, previous_names: ["专业编号"]} : property,
      ),
    };
    expect(codes(publishIssues(withHistory))).toEqual(["STANDARD_PROPERTY_NAME_DUPLICATE"]);
  });

  it("rejects reserved property names at publish time only", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-reserved", name: "DSTManager.Standard", scope: "sheetset", kind: "text",
    });
    expect(draftDiagnostics(document)).toEqual([]);
    expect(codes(publishIssues(document))).toEqual(["STANDARD_PROPERTY_NAME_RESERVED"]);
  });

  it("blocks delete protection through reverse references", () => {
    const document = draftDocument();
    const references = referencesTo(document, "prop-code");
    expect(references.length).toBeGreaterThan(0);
    expect(referencesTo(document, "prop-major")).toEqual([{kind: "mapping", ownerId: "prop-code"}]);
  });

  it("reports mapping source duplication, target emptiness and snapshot drift", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-code-2",
      name: "专业代码二",
      scope: "sheet",
      kind: "mapping",
      source_property_id: "prop-major",
      mapping: [{item_id: "enum-gas", value: "RQ2"}],
      confirmed_source_items: [["enum-gas", "燃气"]],
    });
    expect(codes(publishIssues(document))).toContain("STANDARD_MAPPING_SOURCE_DUPLICATE");

    const drifted = withEnumValues(draftDocument(), [{item_id: "enum-gas", value: "城镇燃气"}], [["enum-gas", "燃气"]]);
    const driftedIssues = publishIssues(drifted);
    expect(codes(driftedIssues)).toEqual(["STANDARD_MAPPING_CONFIRMATION_REQUIRED"]);
    expect(driftedIssues[0]?.severity).toBe("warning");
  });

  it("creates a blank standard that satisfies the save gate and carries the default naming template", () => {
    const document = blankStandardDocument({standardId: "user.draft", name: "新标准", version: "1.0.0"});
    // 旧顶层 rules 不得再被写入（Schema v1 直接替换）
    expect(Object.keys(document)).not.toContain("rules");
    expect(document.dwg_naming).toEqual({segments: defaultDwgNamingSegments()});
    const draft = toDraftDocument(document);
    // 新建空白标准必须能直接保存，并能直接通过发布门禁
    expect(draftDiagnostics(draft)).toEqual([]);
    expect(publishIssues(draft)).toEqual([]);
  });

  it("keeps a missing mapping source out of the save gate but blocks publishing", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-new-mapping",
      name: "新映射",
      scope: "sheetset",
      kind: "mapping",
      source_property_id: "",
      mapping: [],
      confirmed_source_items: [],
    });
    expect(codes(draftDiagnostics(document))).toEqual([]);
    expect(codes(publishIssues(document))).toContain("STANDARD_MAPPING_SOURCE_INVALID");
  });

  it("keeps a dangling mapping source in the save gate", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-new-mapping",
      name: "新映射",
      scope: "sheetset",
      kind: "mapping",
      source_property_id: "prop-missing",
      mapping: [],
      confirmed_source_items: [],
    });
    expect(codes(draftDiagnostics(document))).toEqual(["STANDARD_MAPPING_SOURCE_INVALID"]);
  });

  it("classifies an unknown naming system field as a structure error like the backend", () => {
    const document = draftDocument();
    document.dwg_naming.segments = [{system_field: "foo.bar"}];
    // 后端草稿解析对未知系统字段抛结构级 STANDARD_SEGMENT_REFERENCE_UNKNOWN：
    // 前端保存门禁必须同口径，不能降级为发布期的作用域提示
    expect(codes(draftDiagnostics(document))).toContain("STANDARD_SEGMENT_REFERENCE_UNKNOWN");
    expect(codes(draftDiagnostics(document))).not.toContain("STANDARD_NAMING_FIELD_SCOPE_INVALID");
  });

  it("classifies an unknown composition system field as a structure error", () => {
    const document = withProperty(draftDocument(), {
      property_id: "prop-composed",
      name: "集图签",
      scope: "sheetset",
      kind: "composition",
      segments: [{system_field: "foo.bar"}],
    });
    expect(codes(draftDiagnostics(document))).toContain("STANDARD_SEGMENT_REFERENCE_UNKNOWN");
    expect(codes(draftDiagnostics(document))).not.toContain("STANDARD_SEGMENT_SCOPE_INVALID");
  });

  it("attaches the offending value for messages that interpolate {field} or {source}", () => {
    const asset = (asset_id: string, kind: string, path: string | null): DraftAsset => ({
      asset_id,
      kind: kind as DraftAsset["kind"],
      files: path === null ? [] : [{path, role: ""}],
    });
    const document = draftDocument();
    document.standard_id = "Illegal ID";
    document.version = "1.0";
    document.properties[0]!.scope = "bogus" as DraftDocument["properties"][number]["scope"];
    document.assets = [
      asset("a-kind", "bogus", null),
      asset("a-path", "layout-template", "../escape.dwg"),
      asset("a-dup", "layout-template", null),
      asset("a-dup", "layout-template", null),
    ];
    const detail = (code: string) => publishIssues(document).find(issue => issue.code === code)?.detail;
    expect(detail("STANDARD_ID_INVALID")).toBe("Illegal ID");
    expect(detail("STANDARD_VERSION_INVALID")).toBe("1.0");
    expect(detail("STANDARD_SCOPE_INVALID")).toBe("bogus");
    expect(detail("STANDARD_ASSET_KIND_INVALID")).toBe("bogus");
    expect(detail("STANDARD_ASSET_PATH_INVALID")).toBe("../escape.dwg");
    expect(detail("STANDARD_ASSET_DUPLICATE")).toBe("a-dup");

    const duplicated = withProperty(draftDocument(), {
      property_id: "prop-dup",
      name: "重复映射",
      scope: "sheetset",
      kind: "mapping",
      source_property_id: "prop-major",
      mapping: [{item_id: "enum-gas", value: "RQ2"}],
      confirmed_source_items: [],
    });
    expect(
      publishIssues(duplicated).find(issue => issue.code === "STANDARD_MAPPING_SOURCE_DUPLICATE")?.detail,
    ).toBe("专业");
  });

  it("measures the file name length in code points like the backend", () => {
    const overlong = draftDocument();
    overlong.dwg_naming.segments = [{literal: "图".repeat(237)}];
    expect(codes(publishIssues(overlong))).toContain("DWG_NAME_TOO_LONG");

    const fits = draftDocument();
    fits.dwg_naming.segments = [{literal: "图".repeat(236)}];
    expect(codes(publishIssues(fits))).not.toContain("DWG_NAME_TOO_LONG");

    // 星平面字符（emoji）按码点计数：与后端 len() 同口径，前端不得多算一倍
    const astral = draftDocument();
    astral.dwg_naming.segments = [{literal: "😀".repeat(120)}];
    expect(codes(publishIssues(astral))).not.toContain("DWG_NAME_TOO_LONG");
  });

  it("reports enum value and default violations", () => {
    const document = withEnumValues(
      draftDocument(),
      [{item_id: "enum-gas", value: "燃气"}, {item_id: "enum-water", value: "燃气"}],
      [["enum-gas", "燃气"], ["enum-water", "燃气"]],
    );
    const withDefault: DraftDocument = {
      ...document,
      properties: document.properties.map(property => {
        if (property.property_id === "prop-major") return {...property, default_value: "给水"};
        if (property.property_id === "prop-code" && property.kind === "mapping") {
          return {...property, mapping: [{item_id: "enum-gas", value: "RQ"}, {item_id: "enum-water", value: "RQ"}]};
        }
        return property;
      }),
    };
    expect(codes(publishIssues(withDefault))).toEqual([
      "STANDARD_ENUM_ITEM_DUPLICATE",
      "STANDARD_ENUM_DEFAULT_INVALID",
    ]);
  });

  it("keeps segment reference errors structural and scope errors publish level", () => {
    const unknown = {...draftDocument(), dwg_naming: {segments: [{property_id: "prop-missing"}]}};
    expect(codes(draftDiagnostics(unknown))).toEqual(["STANDARD_SEGMENT_REFERENCE_UNKNOWN"]);

    const sheetToken = withProperty(draftDocument(), {
      property_id: "prop-sheet", name: "图号", scope: "sheet", kind: "text", default_value: "A-001",
    });
    const scoped: DraftDocument = {
      ...sheetToken,
      dwg_naming: {segments: [{property_id: "prop-sheet"}]},
    };
    expect(codes(draftDiagnostics(scoped))).toEqual([]);
    expect(codes(publishIssues(scoped))).toEqual([
      "STANDARD_NAMING_FIELD_SCOPE_INVALID",
      "DWG_NAMING_UNIQUENESS_UNPROVEN",
    ]);
  });

  it("requires a dwg naming template as a structural gate", () => {
    const document = {...draftDocument(), dwg_naming: {segments: []}};
    expect(codes(draftDiagnostics(document))).toEqual(["STANDARD_DWG_NAMING_MISSING"]);
  });

  it("warns when the template can not prove uniqueness", () => {
    const document: DraftDocument = {
      ...draftDocument(),
      dwg_naming: {segments: [{property_id: "prop-code"}]},
    };
    expect(codes(publishIssues(document))).toEqual(["DWG_NAMING_UNIQUENESS_UNPROVEN"]);
  });

  it("limits composition and dwg naming field sets by scope", () => {
    let document = draftDocument();
    document = withProperty(document, {property_id: "prop-set", name: "集属性", scope: "sheetset", kind: "text"});
    document = withProperty(document, {property_id: "prop-sheet", name: "图属性", scope: "sheet", kind: "text"});
    document = withProperty(document, {
      property_id: "prop-composed", name: "集图签", scope: "sheetset", kind: "composition", segments: [],
    });
    expect(compositionFields(document, "sheet")).toEqual([
      "prop-major", "prop-code", "prop-set", "prop-sheet", "sheet.number", "sheet.title",
    ]);
    expect(compositionFields(document, "sheetset")).toEqual(["prop-major", "prop-code", "prop-set"]);
    expect(dwgNamingFields(document)).toEqual([
      "subset.scope", "subset.name", "subset.sequence", "prop-major", "prop-code", "prop-set", "prop-composed",
    ]);
  });

  it("renders an explicit sample preview that never pretends to be engineering output", () => {
    const preview = renderDwgNamingPreview(draftDocument(), SAMPLES);
    expect(preview.text).toBe("RQ-01-03 示例子集");
    expect(preview.filename).toBe("RQ-01-03 示例子集.dwg");
    expect(preview.diagnostics).toEqual([]);
  });

  it("creates only ordinary properties from CSV without derived relations", () => {
    const document = draftDocument();
    const created = parsePropertyCsv("图幅,sheet,true,A2,A2|A3,备注\n备注,sheetset,,,,\n", document);
    expect(created.map(item => [item.kind, item.scope, item.required])).toEqual([
      ["enum", "sheet", true],
      ["text", "sheetset", false],
    ]);
    expect(created[0]?.kind === "enum" && created[0].enum_items).toEqual([
      {item_id: "enum-csv-1", value: "A2"},
      {item_id: "enum-csv-2", value: "A3"},
    ]);
    expect(created.every(item => item.kind === "text" || item.kind === "enum")).toBe(true);
  });
});
