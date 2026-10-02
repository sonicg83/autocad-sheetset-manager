// @vitest-environment happy-dom
import {describe, expect, it, vi} from "vitest";
import {mount} from "@vue/test-utils";

vi.mock("vue-i18n", () => ({useI18n: () => ({t: (key: string) => key})}));
import DraftActionsPanel from "./DraftActionsPanel.vue";

const baseProps = {
  actions: [], cursor: 0, commandCount: 0, stale: true, staleReasons: ["DRAFT_VERSION_CONFLICT"],
  corrupted: false, writesDisabled: true, loading: false,
};

describe("DraftActionsPanel blocker 恢复路径", () => {
  it("过期草稿持续呈现阻断原因、重新加载恢复动作与禁用预览", () => {
    const wrapper = mount(DraftActionsPanel, {props: baseProps, global: {mocks: {$t: (key: string) => key}}});
    const blocker = wrapper.get('[data-tone="error"]');
    expect(blocker.attributes("role")).toBe("note");
    expect(blocker.text()).toContain("shell.draft.staleMessage");
    expect(wrapper.get("button").text()).toBe("shell.draft.reloadConflict");
    const preview = wrapper.findAll("button").find(button => button.text() === "shell.dock.preview");
    expect(preview?.attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-tone="warning"]').exists()).toBe(false);
  });

  it("损坏草稿保留隔离提示和可见的危险语义", () => {
    const wrapper = mount(DraftActionsPanel, {
      props: {...baseProps, stale: false, staleReasons: [], corrupted: true},
      global: {mocks: {$t: (key: string) => key}},
    });
    const warning = wrapper.get('[data-tone="warning"]');
    expect(warning.attributes("role")).toBe("note");
    expect(warning.text()).toBe("shell.draft.corrupted");
  });
});
