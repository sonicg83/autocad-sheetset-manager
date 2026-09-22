// @vitest-environment happy-dom
// 普通属性表与枚举模态（PLAN-DM-038 Task 6 / SPEC-DM-017 §4）：
// 文本/枚举控件联动、枚举稳定 ID 保留、取消不落盘、排序、内部 ID 不外显、
// 必填复选框紧凑尺寸、行级发布诊断标记、引用删除保护与 CSV 只建普通属性。
//
// 组件直接就地修改 `props.document`（缓冲由 StandardEditor 持有），因此断言一律读
// `wrapper.props("document")`，不使用模块级共享状态。
import {afterEach, describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import {readFileSync} from "node:fs";
import {nextTick} from "vue";
import {createI18n} from "vue-i18n";
import OrdinaryPropertyEditor from "./OrdinaryPropertyEditor.vue";
import zhCNStandards from "../../i18n/locales/zh-CN/standards";
import {
  publishIssues,
  toDraftDocument,
  type DraftDiagnostic,
  type DraftDocument,
} from "../../features/standards/draftModel";

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {"zh-CN": {standards: zhCNStandards}},
});

function documentWithEnum(): DraftDocument {
  return toDraftDocument({
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "0.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [
      {property_id: "prop-text", name: "项目名称", scope: "sheetset", kind: "text"},
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        enum_items: [
          {item_id: "enum-gas", value: "燃气"},
          {item_id: "enum-water", value: "给水"},
        ],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-gas", value: "RQ"},
          {item_id: "enum-water", value: "GS"},
        ],
        confirmed_source_items: [["enum-gas", "燃气"], ["enum-water", "给水"]],
      },
    ],
    dwg_naming: {segments: [{property_id: "prop-code"}, {literal: "-"}, {system_field: "subset.scope"}]},
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2},
  });
}

function mountEditor(draft: DraftDocument, diagnostics?: DraftDiagnostic[]) {
  const host = window.document.createElement("div");
  window.document.body.appendChild(host);
  return mount(OrdinaryPropertyEditor, {
    props: {document: draft, diagnostics},
    global: {plugins: [i18n]},
    attachTo: host,
  });
}

function propertyOf(draft: DraftDocument, propertyId: string) {
  return draft.properties.find(item => item.property_id === propertyId);
}

/** 读取组件源码的 scoped 样式块；路径相对 web/ 工作目录（vitest 的 cwd）。 */
function scopedStyle(file: string): string {
  const source = readFileSync(file, "utf8");
  const match = /<style scoped>([\s\S]*?)<\/style>/.exec(source);
  if (match === null) throw new Error("组件缺少 scoped 样式块");
  return match[1];
}

afterEach(() => {
  window.document.body.innerHTML = "";
});

describe("OrdinaryPropertyEditor", () => {
  it("disables enum input for text and preserves enum item ids on rename", async () => {
    const wrapper = mountEditor(documentWithEnum());
    expect(wrapper.get("[data-testid=enum-summary-prop-text]").attributes("aria-disabled")).toBe("true");
    expect(wrapper.find("[data-testid=edit-enum-prop-text]").exists()).toBe(false);
    await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
    await wrapper.get("[data-testid=enum-value-enum-gas]").setValue("城镇燃气");
    await wrapper.get("[data-testid=save-enum]").trigger("click");
    const major = wrapper.props("document").properties.find(item => item.property_id === "prop-major");
    expect(major?.kind === "enum" && major.enum_items[0]).toEqual({item_id: "enum-gas", value: "城镇燃气"});
  });

  it("keeps the table columns and the ordinary/derived split", () => {
    const wrapper = mountEditor(documentWithEnum());
    const headers = wrapper.get("[data-testid=ordinary-table]").findAll("th").map(cell => cell.text());
    expect(headers).toEqual(["属性名", "作用域", "类型", "必填", "默认值", "枚举值", "说明", "删除"]);
    // 派生属性不在普通属性表中出现
    expect(wrapper.find("[data-testid=ordinary-name-prop-code]").exists()).toBe(false);
  });

  it("discards add, rename, delete and reorder on cancel", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
    await wrapper.get("[data-testid=add-enum]").trigger("click");
    await wrapper.get("[data-testid=enum-value-enum-gas]").setValue("城镇燃气");
    await wrapper.get("[data-testid=enum-delete-enum-water]").trigger("click");
    await wrapper.get("[data-testid=enum-down-enum-gas]").trigger("click");
    await wrapper.get("[data-testid=cancel-enum]").trigger("click");
    const major = propertyOf(draft, "prop-major");
    expect(major?.kind === "enum" && major.enum_items).toEqual([
      {item_id: "enum-gas", value: "燃气"},
      {item_id: "enum-water", value: "给水"},
    ]);
    expect(wrapper.find("[data-testid=enum-dialog]").exists()).toBe(false);
  });

  it("reorders enum rows while keeping item ids", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
    await wrapper.get("[data-testid=enum-down-enum-gas]").trigger("click");
    await wrapper.get("[data-testid=save-enum]").trigger("click");
    const major = propertyOf(draft, "prop-major");
    expect(major?.kind === "enum" && major.enum_items.map(item => item.item_id)).toEqual([
      "enum-water",
      "enum-gas",
    ]);
  });

  it("never renders internal enum item ids", async () => {
    const wrapper = mountEditor(documentWithEnum());
    await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
    expect(wrapper.get("[data-testid=enum-dialog]").text()).not.toContain("enum-gas");
    // 顺序列只显示序号
    expect(wrapper.get("[data-testid=enum-dialog]").text()).toContain("01");
  });

  it("warns about the mapping properties that must be reconfirmed", async () => {
    const wrapper = mountEditor(documentWithEnum());
    await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
    expect(wrapper.get("[data-testid=enum-impact]").text()).toContain("专业代码");
  });

  it("switches kind inside the ordinary table without keeping orphan enum items", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=ordinary-kind-prop-major]").setValue("text");
    expect(propertyOf(draft, "prop-major")?.kind).toBe("text");
    await wrapper.get("[data-testid=ordinary-kind-prop-major]").setValue("enum");
    const back = propertyOf(draft, "prop-major");
    expect(back?.kind === "enum" && back.enum_items).toEqual([{item_id: "enum-new", value: ""}]);
  });

  it("keeps the required checkbox compact with a larger hit area", () => {
    const style = scopedStyle("src/components/standards/OrdinaryPropertyEditor.vue");
    expect(style).toMatch(/\.required-check\{[^}]*width:var\(--checkbox-size\)[^}]*height:var\(--checkbox-size\)/);
    expect(style).toMatch(/\.required-hit\{[^}]*width:var\(--tap-target-min\)[^}]*height:var\(--tap-target-min\)/);
    // 复选框本体不得继承输入框的统一高度
    expect(style).not.toMatch(/\.required-check\{[^}]*height:var\(--input-height\)/);
    // 令牌链最终值：16×16 本体 / 32×32 点击区域（happy-dom 不算布局，只能断言令牌链）
    const tokens = readFileSync("src/styles/tokens.css", "utf8");
    expect(tokens).toContain("--checkbox-size:16px");
    expect(tokens).toContain("--tap-target-min:32px");
  });

  it("marks rows with publish level issues and keeps them out of the save gate", () => {
    const draft = documentWithEnum();
    const major = propertyOf(draft, "prop-major");
    if (major !== undefined) major.default_value = "蒸汽";
    const wrapper = mountEditor(draft, publishIssues(draft));
    expect(wrapper.get("[data-testid=ordinary-issue-prop-major]").text()).toContain("枚举默认值");
    expect(wrapper.get("[data-testid=ordinary-name-prop-major]").attributes("aria-invalid")).toBe("true");
  });

  it("marks a cross scope name conflict on the offending row", () => {
    const draft = documentWithEnum();
    const appended = toDraftDocument({
      properties: [{property_id: "prop-sheet", name: " 专业 ", scope: "sheet", kind: "text"}],
    }).properties[0]!;
    draft.properties.push(appended);
    const wrapper = mountEditor(draft, publishIssues(draft));
    expect(wrapper.get("[data-testid=ordinary-issue-prop-sheet]").text()).toContain("命名空间");
  });

  it("blocks deleting a referenced property and reports the referencing side", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=ordinary-remove-prop-major]").trigger("click");
    expect(propertyOf(draft, "prop-major")).toBeDefined();
    expect(wrapper.get("[data-testid=ordinary-delete-blocked]").text()).toContain("专业代码");
    expect(wrapper.emitted("deleteBlocked")?.[0]?.[0]).toMatchObject({propertyId: "prop-major"});
  });

  it("removes an unreferenced property", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=ordinary-remove-prop-text]").trigger("click");
    expect(propertyOf(draft, "prop-text")).toBeUndefined();
  });

  it("creates only ordinary properties from CSV", async () => {
    const draft = documentWithEnum();
    const wrapper = mountEditor(draft);
    await wrapper.get("[data-testid=ordinary-csv]").trigger("click");
    await wrapper.get("textarea").setValue("图幅,sheet,true,A2,A2|A3,备注\n");
    await wrapper.get("[data-testid=apply-csv]").trigger("click");
    const created = draft.properties.at(-1);
    expect(created?.kind).toBe("enum");
    expect(created?.scope).toBe("sheet");
    expect(draft.properties.filter(item => item.kind === "mapping")).toHaveLength(1);
  });

  it("focuses the requested property row", async () => {
    const wrapper = mountEditor(documentWithEnum());
    await wrapper.setProps({focusRequest: {propertyId: "prop-major"}});
    await nextTick();
    expect(window.document.activeElement?.getAttribute("data-testid")).toBe("ordinary-name-prop-major");
  });
});
