// @vitest-environment happy-dom
// 共享令牌编辑器与 DWG 命名分区（PLAN-DM-038 Task 8 / SPEC-DM-017 §5.3、§6）。
// 覆盖：字段可见性（组合作用域 / DWG 命名）、令牌原子性（插入、退格、方向键）、
// 不解析用户输入的 `{...}`、结构化序列化、取消不落盘、示例预览与文件名风险提示。
import {afterEach, describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import {createI18n} from "vue-i18n";
import TokenExpressionEditor from "./TokenExpressionEditor.vue";
import DwgNamingEditor from "./DwgNamingEditor.vue";
import CompositionPropertyDialog from "./CompositionPropertyDialog.vue";
import zhCNStandards from "../../i18n/locales/zh-CN/standards";
import {
  compositionFields,
  draftDiagnostics,
  dwgNamingFields,
  publishIssues,
  toDraftDocument,
  type DraftDocument,
  type DraftSegment,
} from "../../features/standards/draftModel";
import {compositionTokenFields, dwgNamingTokenFields} from "../../features/standards/tokenFields";

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {"zh-CN": {standards: zhCNStandards}},
});

function newSchemaDocument(): DraftDocument {
  return toDraftDocument({
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "0.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [
      {property_id: "prop-set", name: "集属性", scope: "sheetset", kind: "text", default_value: "SET"},
      {property_id: "prop-sheet", name: "图属性", scope: "sheet", kind: "text", default_value: "SHT"},
      {
        property_id: "prop-map",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [{item_id: "enum-gas", value: "RQ"}],
        confirmed_source_items: [["enum-gas", "燃气"]],
      },
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        enum_items: [{item_id: "enum-gas", value: "燃气"}],
      },
      {
        property_id: "prop-composed-set",
        name: "集图签",
        scope: "sheetset",
        kind: "composition",
        segments: [{property_id: "prop-map"}],
      },
    ],
    dwg_naming: {
      segments: [
        {property_id: "prop-map"},
        {literal: "-"},
        {system_field: "subset.scope"},
        {literal: " "},
        {system_field: "subset.name"},
      ],
    },
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 3},
  });
}

const TEXTS = {
  systemLabels: {
    "subset.scope": "子集图纸号范围",
    "subset.name": "子集名称",
    "subset.sequence": "子集顺序",
    "sheet.number": "图号",
    "sheet.title": "图名",
  },
  placeholder: "示例值",
  sequenceFormat: "02",
};

const SAMPLES = {
  subsetName: "示例子集",
  sheetNumber: "001",
  sheetTitle: "示例图名",
  placeholder: "示例值",
};

function mountTokenEditor(segments: DraftSegment[], fields: ReturnType<typeof compositionTokenFields>, onUpdate: (next: DraftSegment[]) => void) {
  const host = window.document.createElement("div");
  window.document.body.appendChild(host);
  return mount(TokenExpressionEditor, {
    props: {
      segments,
      fields,
      label: "组合表达式",
      previewLabel: "实时预览",
      preview: "预览",
      "onUpdate:segments": onUpdate,
    },
    global: {plugins: [i18n]},
    attachTo: host,
  });
}

/** 受控组件的测试宿主：模拟父层把新片段数组写回 props。 */
function mountWithBuffer(initial: DraftSegment[], fields: ReturnType<typeof compositionTokenFields>) {
  let segments = initial;
  let wrapper: ReturnType<typeof mountTokenEditor>;
  const update = (next: DraftSegment[]) => {
    segments = next;
    void wrapper.setProps({segments: next});
  };
  wrapper = mountTokenEditor(initial, fields, update);
  return {wrapper, current: () => segments};
}

function mountNamingEditor(draft: DraftDocument, diagnostics?: Array<{code: string; severity: string}>) {
  const host = window.document.createElement("div");
  window.document.body.appendChild(host);
  return mount(DwgNamingEditor, {
    props: {document: draft, diagnostics},
    global: {plugins: [i18n]},
    attachTo: host,
  });
}

afterEach(() => {
  window.document.body.innerHTML = "";
});

describe("field visibility", () => {
  it("limits sheet composition and dwg naming to their own field sets", () => {
    const document = newSchemaDocument();
    expect(compositionFields(document, "sheet")).toEqual([
      "prop-set", "prop-sheet", "prop-map", "prop-major", "sheet.number", "sheet.title",
    ]);
    expect(dwgNamingFields(document)).toEqual([
      "subset.scope", "subset.name", "subset.sequence", "prop-set", "prop-map", "prop-major", "prop-composed-set",
    ]);
  });

  it("never offers a composition or a sheet property to dwg naming", () => {
    const document = newSchemaDocument();
    const fields = dwgNamingTokenFields(document, TEXTS);
    expect(fields.map(field => field.id)).toEqual(dwgNamingFields(document));
    expect(fields.some(field => field.id === "prop-sheet")).toBe(false);
    expect(fields.find(field => field.id === "subset.sequence")?.format).toBe("02");
  });
});

describe("TokenExpressionEditor", () => {
  it("inserts fields as atomic tokens and keeps literal text separate", async () => {
    const fields = compositionTokenFields(newSchemaDocument(), "sheetset", TEXTS);
    const {wrapper, current} = mountWithBuffer([], fields);
    await wrapper.get("[data-testid=token-literal]").setValue("前缀");
    await wrapper.get("[data-testid=token-literal]").trigger("keydown", {key: "Enter"});
    await wrapper.get("[data-testid=token-field-prop-map]").trigger("click");
    expect(current()).toEqual([{literal: "前缀"}, {property_id: "prop-map"}]);
  });

  it("treats typed braces as literal text instead of parsing fields", async () => {
    const fields = compositionTokenFields(newSchemaDocument(), "sheetset", TEXTS);
    const {wrapper, current} = mountWithBuffer([], fields);
    await wrapper.get("[data-testid=token-literal]").setValue("{prop-map}");
    await wrapper.get("[data-testid=token-literal]").trigger("keydown", {key: "Enter"});
    expect(current()).toEqual([{literal: "{prop-map}"}]);
  });

  it("moves and deletes whole tokens with the keyboard", async () => {
    const fields = compositionTokenFields(newSchemaDocument(), "sheetset", TEXTS);
    const {wrapper, current} = mountWithBuffer([{literal: "A"}, {property_id: "prop-map"}], fields);
    const input = wrapper.get("[data-testid=token-literal]");
    await input.trigger("keydown", {key: "Backspace"});
    expect(current()).toEqual([{literal: "A"}]);
    await wrapper.get("[data-testid=token-line]").trigger("click");
    await input.trigger("keydown", {key: "Backspace"});
    expect(current()).toEqual([]);
  });

  it("keeps the caret position when inserting in the middle", async () => {
    const fields = compositionTokenFields(newSchemaDocument(), "sheetset", TEXTS);
    const {wrapper, current} = mountWithBuffer([{literal: "A"}, {literal: "B"}], fields);
    await wrapper.get("[data-testid=token-literal]").trigger("keydown", {key: "ArrowLeft"});
    await wrapper.get("[data-testid=token-field-prop-map]").trigger("click");
    expect(current()).toEqual([{literal: "A"}, {property_id: "prop-map"}, {literal: "B"}]);
  });
});

describe("CompositionPropertyDialog", () => {
  it("saves the structured segments only on save", async () => {
    const draft = newSchemaDocument();
    const property = draft.properties.find(item => item.property_id === "prop-composed-set");
    if (property === undefined || property.kind !== "composition") throw new Error("missing fixture");
    const host = window.document.createElement("div");
    window.document.body.appendChild(host);
    const wrapper = mount(CompositionPropertyDialog, {
      props: {open: true, property, document: draft},
      global: {plugins: [i18n]},
      attachTo: host,
    });
    await wrapper.get("[data-testid=token-field-prop-set]").trigger("click");
    await wrapper.get("[data-testid=cancel-composition]").trigger("click");
    expect(property.segments).toEqual([{property_id: "prop-map"}]);
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});

describe("DwgNamingEditor", () => {
  it("shows the sample file name with the appended extension outside the template", () => {
    const wrapper = mountNamingEditor(newSchemaDocument());
    expect(wrapper.get("[data-testid=token-preview]").text()).toBe("RQ-001-003 示例子集.dwg");
    expect(wrapper.get("[data-testid=naming-extension-note]").text()).toContain(".dwg");
    expect(wrapper.get("[data-testid=token-preview-state]").text()).toBe("示例");
    expect(wrapper.get("[data-testid=token-samples]").text()).toContain("RQ");
  });

  it("warns when the template can not prove uniqueness", async () => {
    const draft = newSchemaDocument();
    draft.dwg_naming.segments = [{literal: "图签"}];
    const wrapper = mountNamingEditor(draft, publishIssues(draft));
    expect(wrapper.find("[data-testid=naming-uniqueness-warning]").exists()).toBe(true);
    expect(draftDiagnostics(draft)).toEqual([]);
  });

  it("shows file name risks as a warning note instead of a blocking error", () => {
    const draft = newSchemaDocument();
    draft.dwg_naming.segments = [{literal: "图签.dwg"}];
    const wrapper = mountNamingEditor(draft, publishIssues(draft));
    expect(wrapper.find("[data-testid=naming-risk-warning]").exists()).toBe(true);
    expect(wrapper.find("[data-testid=naming-error]").exists()).toBe(false);
  });

  it("restores the default template without an implicit prefix", async () => {
    const draft = newSchemaDocument();
    const wrapper = mountNamingEditor(draft);
    await wrapper.get("[data-testid=reset-naming]").trigger("click");
    expect(draft.dwg_naming.segments).toEqual([
      {system_field: "subset.scope"},
      {literal: " "},
      {system_field: "subset.name"},
    ]);
  });

  it("flags template level file name risks as publish warnings that never block", () => {
    const cases: Array<[DraftSegment[], string]> = [
      [[{literal: "图签.dwg"}], "DWG_NAME_EXTENSION_FORBIDDEN"],
      [[{literal: "a/b"}], "DWG_NAME_CHARACTER_INVALID"],
      [[{literal: "CON"}], "DWG_NAME_RESERVED_DEVICE"],
      [[{literal: "bad."}], "DWG_NAME_TRAILING_CHARACTER"],
      [[{literal: "x".repeat(237)}], "DWG_NAME_TOO_LONG"],
    ];
    for (const [segments, code] of cases) {
      const draft = newSchemaDocument();
      draft.dwg_naming.segments = segments;
      const issue = publishIssues(draft).find(item => item.code === code);
      expect(issue?.severity).toBe("warning");
    }
    // 令牌会补上后续字符：`CON` 后面还有令牌时不再是保留设备名，也不再缺少唯一性字段
    const safe = newSchemaDocument();
    safe.dwg_naming.segments = [{literal: "CON"}, {system_field: "subset.scope"}];
    expect(publishIssues(safe).map(issue => issue.code)).toEqual([]);
  });

  it("accepts a template that proves uniqueness and stays free of risks", () => {
    const draft = newSchemaDocument();
    expect(publishIssues(draft).map(issue => issue.code)).toEqual([]);
  });
});
