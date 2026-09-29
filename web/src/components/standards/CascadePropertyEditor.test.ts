// @vitest-environment happy-dom
import {afterEach, describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import {nextTick, reactive} from "vue";
import {createI18n} from "vue-i18n";
import CascadePropertyEditor from "./CascadePropertyEditor.vue";
import zhCNStandards from "../../i18n/locales/zh-CN/standards";
import {toDraftDocument, type DraftDocument} from "../../features/standards/draftModel";

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {"zh-CN": {standards: zhCNStandards}},
});

function documentWithCascade(): DraftDocument {
  return reactive(toDraftDocument({
    schema_version: 4,
    standard_id: "00000000-0000-4000-8000-000000000047",
    name: "测试标准",
    description: "",
    published_at: null,
    supported_cad_versions: ["2020"],
    properties: [
      {
        property_id: "enum-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        enum_items: [
          {item_id: "item-shared", value: "燃气"},
          {item_id: "item-water", value: "给水"},
        ],
      },
      {
        property_id: "enum-other",
        name: "阶段",
        scope: "sheetset",
        kind: "enum",
        enum_items: [{item_id: "item-shared", value: "施工"}],
      },
      {
        property_id: "enum-sheet",
        name: "图纸类别",
        scope: "sheet",
        kind: "enum",
        enum_items: [{item_id: "item-sheet", value: "总图"}],
      },
      {
        property_id: "cascade-subdivision",
        name: "分区",
        scope: "sheetset",
        kind: "cascade",
        source_property_id: "enum-major",
        cascade_options: [
          {source_item_id: "item-shared", values: ["市政", "庭院"]},
          {source_item_id: "item-water", values: ["给水"]},
        ],
      },
    ],
    dwg_naming: {segments: [{system_field: "subset.scope"}, {system_field: "subset.name"}]},
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2},
  }));
}

function mountCascadeEditor(document: DraftDocument) {
  const host = window.document.createElement("div");
  window.document.body.appendChild(host);
  return mount(CascadePropertyEditor, {
    props: {document},
    global: {plugins: [i18n]},
    attachTo: host,
  });
}

function sourceOptions(wrapper: ReturnType<typeof mountCascadeEditor>): string[] {
  return wrapper.get("[data-testid=cascade-source]")
    .findAll("option")
    .filter(option => option.attributes("disabled") === undefined)
    .map(option => option.attributes("value") ?? "")
    .filter(value => value !== "");
}

afterEach(() => {
  window.document.body.innerHTML = "";
});

describe("CascadePropertyEditor", () => {
  it("creates and edits cascade properties in either scope with same-scope enum candidates", async () => {
    const document = documentWithCascade();
    const wrapper = mountCascadeEditor(document);
    await wrapper.get("[data-testid=add-cascade]").trigger("click");
    const created = document.properties.find(property => property.kind === "cascade" && property.name === "");
    expect(created?.kind).toBe("cascade");
    if (created?.kind !== "cascade") throw new Error("missing new cascade");

    await wrapper.get(`[data-testid=edit-cascade-${created.property_id}]`).trigger("click");
    await wrapper.get("[data-testid=cascade-scope]").setValue("sheet");
    expect(sourceOptions(wrapper)).toEqual(["enum-sheet"]);
    await wrapper.get("[data-testid=cascade-source]").setValue("enum-sheet");
    expect(wrapper.find("[data-testid=cascade-values-item-sheet]").exists()).toBe(true);
    await wrapper.get("[data-testid=cascade-values-item-sheet]").setValue("总图，剖面图");
    await wrapper.get("[data-testid=confirm-cascade]").trigger("click");

    expect(created.scope).toBe("sheet");
    expect(created.source_property_id).toBe("enum-sheet");
    expect(created.cascade_options).toEqual([{source_item_id: "item-sheet", values: ["总图", "剖面图"]}]);
  });

  it("preserves values by stable enum id across rename and synchronizes added or removed source items", async () => {
    const document = documentWithCascade();
    const wrapper = mountCascadeEditor(document);
    await wrapper.get("[data-testid=edit-cascade-cascade-subdivision]").trigger("click");
    expect(sourceOptions(wrapper)).toEqual(["enum-major", "enum-other"]);
    expect((wrapper.get("[data-testid=cascade-values-item-shared]").element as HTMLInputElement).value)
      .toBe("市政, 庭院");

    const source = document.properties.find(property => property.property_id === "enum-major");
    if (source?.kind !== "enum") throw new Error("missing source enum");
    source.enum_items[0]!.value = "燃气专业";
    source.enum_items.push({item_id: "item-road", value: "道路"});
    source.enum_items.splice(1, 1);
    await nextTick();

    expect(wrapper.get("[data-testid=cascade-source-value-item-shared]").text()).toBe("燃气专业");
    expect(wrapper.find("[data-testid=cascade-values-item-water]").exists()).toBe(false);
    expect(wrapper.find("[data-testid=cascade-values-item-road]").exists()).toBe(true);
    await wrapper.get("[data-testid=cascade-values-item-road]").setValue("主路");
    await wrapper.get("[data-testid=confirm-cascade]").trigger("click");
    const cascade = document.properties.find(property => property.property_id === "cascade-subdivision");
    expect(cascade?.kind === "cascade" && cascade.cascade_options).toEqual([
      {source_item_id: "item-shared", values: ["市政", "庭院"]},
      {source_item_id: "item-road", values: ["主路"]},
    ]);
  });

  it("does not carry old rows when the source or scope changes and disables invalid values", async () => {
    const document = documentWithCascade();
    const wrapper = mountCascadeEditor(document);
    await wrapper.get("[data-testid=edit-cascade-cascade-subdivision]").trigger("click");
    await wrapper.get("[data-testid=cascade-source]").setValue("enum-other");
    expect(wrapper.find("[data-testid=cascade-values-item-shared]").exists()).toBe(true);
    expect((wrapper.get("[data-testid=cascade-values-item-shared]").element as HTMLInputElement).value).toBe("");

    await wrapper.get("[data-testid=cascade-scope]").setValue("sheet");
    expect(sourceOptions(wrapper)).toEqual(["enum-sheet"]);
    expect((wrapper.get("[data-testid=cascade-source]").element as HTMLSelectElement).value).toBe("");
    await wrapper.get("[data-testid=cascade-source]").setValue("enum-sheet");

    const input = wrapper.get("[data-testid=cascade-values-item-sheet]");
    await input.setValue("总图,,剖面");
    expect(wrapper.get("[data-testid=confirm-cascade]").attributes("disabled")).toBeDefined();
    await input.setValue("Alpha, alpha");
    expect(wrapper.get("[data-testid=confirm-cascade]").attributes("disabled")).toBeDefined();
    await input.setValue("总图, 剖面");
    expect(wrapper.get("[data-testid=confirm-cascade]").attributes("disabled")).toBeUndefined();
  });

  it("supports keyboard dismissal and keeps source controls reachable in a narrow layout", async () => {
    const wrapper = mountCascadeEditor(documentWithCascade());
    await wrapper.get("[data-testid=edit-cascade-cascade-subdivision]").trigger("click");
    expect(wrapper.get("[data-testid=cascade-dialog]").attributes("role")).toBe("dialog");
    await wrapper.get("[data-testid=cascade-dialog]").trigger("keydown", {key: "Escape"});
    expect(wrapper.find("[data-testid=cascade-dialog]").exists()).toBe(false);
    expect(wrapper.get("[data-testid=edit-cascade-cascade-subdivision]").element.tagName).toBe("BUTTON");
  });
});
