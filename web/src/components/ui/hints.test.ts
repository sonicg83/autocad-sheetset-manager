// @vitest-environment happy-dom
import {defineComponent, h, nextTick, ref} from "vue";
import {describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import {readFileSync} from "node:fs";
import FormField from "./FormField.vue";
import UiBanner from "./UiBanner.vue";
import UiHint, {type UiHintProps} from "./UiHint.vue";
import UiInput from "./UiInput.vue";
import {mergeDescriptionIds} from "./descriptionIds";

const validLead: UiHintProps = {kind: "lead"};
// @ts-expect-error Lead 使用固定中性色，不接受调用方传入语义 tone。
const invalidLead: UiHintProps = {kind: "lead", tone: "error"};
// @ts-expect-error Error 只允许 danger 对应的 error tone。
const invalidError: UiHintProps = {kind: "error", tone: "info"};
void validLead;
void invalidLead;
void invalidError;

describe("提示原语与描述关联", () => {
  it("description_error_first_and_unique", () => {
    expect(mergeDescriptionIds("field-error", "field-help", "group-help field-help  group-help"))
      .toBe("field-error field-help group-help");
    expect(mergeDescriptionIds()).toBeUndefined();
  });

  it("hint_and_error_remain_visible", () => {
    const wrapper = mount(FormField, {
      props: {label: "名称", id: "field-1", hint: "最多 255 字符", error: "名称重复"},
      slots: {default: (props: {id: string; describedBy?: string; invalid: boolean}) => h(UiInput, {...props})},
    });

    expect(wrapper.find(".form-field__hint").text()).toBe("最多 255 字符");
    expect(wrapper.find(".form-field__error").text()).toBe("名称重复");
    expect(wrapper.find("input").attributes("aria-describedby")).toBe("field-1-error field-1-hint");
    expect(wrapper.find("input").attributes("aria-invalid")).toBe("true");
  });

  it("shared_description_updates_without_dangling_id", async () => {
    const showShared = ref(true);
    const Host = defineComponent({
      setup() {
        return () => h("div", [
          showShared.value ? h("p", {id: "group-help"}, "组内共享说明") : null,
          h(FormField, {
            label: "名称",
            id: "field-2",
            hint: "字段说明",
            sharedDescribedBy: showShared.value ? "group-help field-2-hint" : undefined,
          }, {default: (props: {id: string; describedBy?: string; invalid: boolean}) => h(UiInput, {...props})}),
          h("button", {type: "button", onClick: () => { showShared.value = false; }}, "收起共享说明"),
        ]);
      },
    });
    const wrapper = mount(Host);

    expect(wrapper.find("input").attributes("aria-describedby")).toBe("field-2-hint group-help");
    expect(wrapper.find("#group-help").exists()).toBe(true);
    await wrapper.find("button").trigger("click");
    expect(wrapper.find("#group-help").exists()).toBe(false);
    expect(wrapper.find("input").attributes("aria-describedby")).toBe("field-2-hint");
  });

  it("static_banner_is_not_alert", () => {
    const wrapper = mount(UiBanner, {props: {tone: "notice"}, slots: {default: "已加载"}});
    expect(wrapper.attributes("data-hint-kind")).toBe("banner");
    expect(wrapper.attributes("role")).toBeUndefined();
    expect(wrapper.attributes("aria-live")).toBeUndefined();
    expect(wrapper.text()).toContain("已加载");
  });

  it("dynamic_hint_has_one_live_owner", async () => {
    const Host = defineComponent({
      setup() {
        const message = ref("正在加载");
        return {message};
      },
      render() {
        return h(UiHint, {id: "job-status", kind: "status", live: "polite"}, () => this.message);
      },
    });
    const wrapper = mount(Host);
    const firstNode = wrapper.get('[role="status"]').element;

    expect(wrapper.findAll('[role="status"]')).toHaveLength(1);
    expect(firstNode.textContent).toBe("正在加载");
    wrapper.vm.message = "已完成";
    await nextTick();
    expect(wrapper.findAll('[role="status"]')).toHaveLength(1);
    expect(wrapper.get('[role="status"]').element).toBe(firstNode);
    expect(firstNode.textContent).toBe("已完成");
  });

  it("lead_help_use_fixed_semantic_color", () => {
    const lead = mount(UiHint, {props: {kind: "lead"}, slots: {default: "区块说明"}});
    const help = mount(UiHint, {props: {kind: "help"}, slots: {default: "字段说明"}});
    expect(lead.attributes("data-hint-kind")).toBe("lead");
    expect(help.attributes("data-hint-kind")).toBe("help");
    expect(lead.classes()).toContain("ui-hint--lead");
    expect(help.classes()).toContain("ui-hint--help");
    const source = readFileSync("src/components/ui/UiHint.vue", "utf8");
    expect(source).toContain(".ui-hint--lead{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-secondary)}");
    expect(source).toContain(".ui-hint--help{font-family:var(--font-ui);font-size:var(--font-caption);color:var(--color-text-muted)}");
  });

  it("Banner 保留四种 tone 且 notice 使用 info 语义色", () => {
    const tones = ["notice", "success", "warning", "error"] as const;
    for (const tone of tones) {
      const wrapper = mount(UiBanner, {props: {tone}, slots: {default: "提示"}});
      expect(wrapper.attributes("data-tone")).toBe(tone);
      expect(wrapper.classes()).toContain(`ui-banner--${tone}`);
    }
    const source = readFileSync("src/components/ui/UiBanner.vue", "utf8");
    expect(source).toContain(".ui-banner--notice{color:var(--color-info);background:var(--color-info-bg)}");
  });
});
