// @vitest-environment happy-dom
// 派生属性表与映射模态框（PLAN-DM-038 Task 7 / SPEC-DM-017 §5.1–§5.2）：
// 源属性唯一占用过滤、固定映射行（跟随源枚举身份）、只读源值、无行增删、
// 内部 ID 不外显、待确认状态、删除引用保护与类型切换。
import {afterEach, describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import {createI18n} from "vue-i18n";
import DerivedPropertyEditor from "./DerivedPropertyEditor.vue";
import zhCNStandards from "../../i18n/locales/zh-CN/standards";
import {
  toDraftDocument,
  type DraftDocument,
  type DraftMappingProperty,
} from "../../features/standards/draftModel";

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {"zh-CN": {standards: zhCNStandards}},
});

/**
 * `prop-major` 已被 `prop-claimed` 占用，`prop-code` 当前也指向它（重复占用），
 * 因此编辑 `prop-code` 时唯一可选的源是未被占用的 `prop-other-enum`。
 */
function documentWithClaimedSource(): DraftDocument {
  return toDraftDocument({
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "0.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        enum_items: [
          {item_id: "enum-a", value: "燃气"},
          {item_id: "enum-b", value: "给水"},
        ],
      },
      {
        property_id: "prop-other-enum",
        name: "阶段",
        scope: "sheetset",
        kind: "enum",
        enum_items: [{item_id: "enum-x", value: "施工图"}],
      },
      {
        property_id: "prop-claimed",
        name: "已占用代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-a", value: "RQ"},
          {item_id: "enum-b", value: "GS"},
        ],
        confirmed_source_items: [["enum-a", "燃气"], ["enum-b", "给水"]],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-a", value: "RQ"},
          {item_id: "enum-b", value: ""},
        ],
        confirmed_source_items: [["enum-a", "燃气"], ["enum-b", "给水"]],
      },
      {
        property_id: "prop-label",
        name: "图签",
        scope: "sheetset",
        kind: "composition",
        segments: [{property_id: "prop-code"}, {literal: "-"}, {system_field: "subset.scope"}],
      },
    ],
    dwg_naming: {segments: [{property_id: "prop-code"}, {literal: "-"}, {system_field: "subset.scope"}]},
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2},
  });
}

function mountDerivedEditor(draft: DraftDocument) {
  const host = window.document.createElement("div");
  window.document.body.appendChild(host);
  return mount(DerivedPropertyEditor, {
    props: {document: draft},
    global: {plugins: [i18n]},
    attachTo: host,
  });
}

/** 源属性选择器中**可选**（未被占用）的源属性 ID 列表。 */
function sourceOptions(wrapper: ReturnType<typeof mountDerivedEditor>): string[] {
  return wrapper
    .get("[data-testid=mapping-source]")
    .findAll("option")
    .filter(option => option.attributes("disabled") === undefined)
    .map(option => option.attributes("value") ?? "")
    .filter(value => value !== "");
}

/** 映射行身份：固定行集合按源枚举项 ID 定位（界面只显示源枚举显示值）。 */
function mappingRows(wrapper: ReturnType<typeof mountDerivedEditor>): string[] {
  return wrapper
    .findAll("[data-testid^=mapping-target-]")
    .map(element => (element.attributes("data-testid") ?? "").replace("mapping-target-", ""));
}

function mappingProperty(draft: DraftDocument): DraftMappingProperty {
  const property = draft.properties.find(item => item.property_id === "prop-code");
  if (property === undefined || property.kind !== "mapping") throw new Error("missing mapping fixture");
  return property;
}

afterEach(() => {
  window.document.body.innerHTML = "";
});

describe("DerivedPropertyEditor", () => {
  it("offers only unclaimed ordinary enum sources and fixes rows to enum ids", async () => {
    const wrapper = mountDerivedEditor(documentWithClaimedSource());
    await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
    expect(sourceOptions(wrapper)).toEqual(["prop-other-enum"]);
    expect(mappingRows(wrapper)).toEqual(["enum-a", "enum-b"]);
    expect(wrapper.find("[data-testid=add-mapping-row]").exists()).toBe(false);
  });

  it("keeps the derived table columns and hides ordinary properties", () => {
    const wrapper = mountDerivedEditor(documentWithClaimedSource());
    const headers = wrapper
      .get("[data-testid=derived-table]")
      .findAll(".derived-head span")
      .map(cell => cell.text());
    expect(headers).toEqual(["属性名", "作用域", "源属性摘要", "类型", "说明", "编辑", "删除"]);
    expect(wrapper.find("[data-testid=derived-name-prop-major]").exists()).toBe(false);
  });

  it("shows read only source values without exposing internal ids", async () => {
    const wrapper = mountDerivedEditor(documentWithClaimedSource());
    await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
    expect(wrapper.get("[data-testid=mapping-source-value-enum-a]").text()).toBe("燃气");
    expect(wrapper.get("[data-testid=mapping-dialog]").text()).not.toContain("enum-a");
    // 当前被占用的源仍以禁用项保留，避免控件显示错误的源
    const occupiedOption = wrapper
      .get("[data-testid=mapping-source]")
      .findAll("option")
      .find(option => option.attributes("value") === "prop-major");
    expect(occupiedOption?.attributes("disabled")).toBeDefined();
  });

  it("confirms the mapping snapshot and clears the pending state", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
    expect(wrapper.get("[data-testid=mapping-status]").text()).toContain("映射完整");
    await wrapper.get("[data-testid=mapping-target-enum-b]").setValue("GS");
    await wrapper.get("[data-testid=confirm-mapping]").trigger("click");
    const property = mappingProperty(draft);
    expect(property.mapping).toEqual([
      {item_id: "enum-a", value: "RQ"},
      {item_id: "enum-b", value: "GS"},
    ]);
    expect(property.confirmed_source_items).toEqual([["enum-a", "燃气"], ["enum-b", "给水"]]);
  });

  it("discards edits on cancel", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
    await wrapper.get("[data-testid=mapping-target-enum-b]").setValue("GS");
    await wrapper.get("[data-testid=cancel-mapping]").trigger("click");
    expect(mappingProperty(draft).mapping).toEqual([
      {item_id: "enum-a", value: "RQ"},
      {item_id: "enum-b", value: ""},
    ]);
    expect(wrapper.find("[data-testid=mapping-dialog]").exists()).toBe(false);
  });

  it("rebuilds rows when the source changes and keeps enum identity on rename", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
    await wrapper.get("[data-testid=mapping-source]").setValue("prop-other-enum");
    expect(mappingRows(wrapper)).toEqual(["enum-x"]);
    await wrapper.get("[data-testid=confirm-mapping]").trigger("click");
    expect(mappingProperty(draft).source_property_id).toBe("prop-other-enum");
    expect(mappingProperty(draft).mapping).toEqual([{item_id: "enum-x", value: ""}]);
  });

  it("marks a pending mapping after the enum list changed", () => {
    const draft = documentWithClaimedSource();
    const major = draft.properties.find(item => item.property_id === "prop-major");
    if (major !== undefined && major.kind === "enum") {
      major.enum_items = [...major.enum_items, {item_id: "enum-c", value: "热力"}];
    }
    const wrapper = mountDerivedEditor(draft);
    expect(wrapper.get("[data-testid=derived-source-prop-code]").text()).toContain("待确认");
  });

  it("switches derived kind and clears the payload", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=derived-kind-prop-code]").setValue("composition");
    const property = draft.properties.find(item => item.property_id === "prop-code");
    expect(property?.kind).toBe("composition");
    expect(property !== undefined && "mapping" in property).toBe(false);
  });

  it("keeps the scope of an existing derived property read-only", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    expect(wrapper.find("[data-testid=derived-scope-prop-code]").exists()).toBe(false);
    expect(wrapper.get("[data-testid=derived-scope-badge-prop-code]").text()).toBe("sheetset");
    await wrapper.get("[data-testid=add-derived]").trigger("click");
    const created = draft.properties.at(-1)!;
    await wrapper.get(`[data-testid=derived-scope-${created.property_id}]`).setValue("sheet");
    expect(draft.properties.at(-1)?.scope).toBe("sheet");
  });

  it("blocks deleting a derived property that the dwg naming template uses", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=derived-remove-prop-code]").trigger("click");
    expect(mappingProperty(draft)).toBeDefined();
    expect(wrapper.get("[data-testid=derived-delete-blocked]").text()).toContain("图签");
    expect(wrapper.emitted("deleteBlocked")?.[0]?.[0]).toMatchObject({propertyId: "prop-code"});
  });

  it("removes an unreferenced derived property", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=derived-remove-prop-claimed]").trigger("click");
    expect(draft.properties.some(item => item.property_id === "prop-claimed")).toBe(false);
  });

  it("opens the composition dialog from the derived table", async () => {
    const wrapper = mountDerivedEditor(documentWithClaimedSource());
    await wrapper.get("[data-testid=edit-derived-prop-label]").trigger("click");
    expect(wrapper.find("[data-testid=composition-dialog]").exists()).toBe(true);
  });

  it("saves composition segments from the dialog and discards them on cancel", async () => {
    const draft = documentWithClaimedSource();
    const wrapper = mountDerivedEditor(draft);
    await wrapper.get("[data-testid=edit-derived-prop-label]").trigger("click");
    await wrapper.get("[data-testid=token-field-prop-code]").trigger("click");
    await wrapper.get("[data-testid=cancel-composition]").trigger("click");
    const label = draft.properties.find(item => item.property_id === "prop-label");
    expect(label?.kind === "composition" && label.segments).toEqual([
      {property_id: "prop-code"},
      {literal: "-"},
      {system_field: "subset.scope"},
    ]);

    await wrapper.get("[data-testid=edit-derived-prop-label]").trigger("click");
    await wrapper.get("[data-testid=token-clear]").trigger("click");
    await wrapper.get("[data-testid=save-composition]").trigger("click");
    expect(label?.kind === "composition" && label.segments).toEqual([]);
  });

  it("opens the editor for the requested publish issue", async () => {
    const wrapper = mountDerivedEditor(documentWithClaimedSource());
    await wrapper.setProps({focusRequest: {propertyId: "prop-code", openEditor: true}});
    expect(wrapper.find("[data-testid=mapping-dialog]").exists()).toBe(true);
  });
});
