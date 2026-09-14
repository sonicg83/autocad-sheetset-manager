// @vitest-environment happy-dom
// 对话框焦点工具契约（PLAN-DM-029 Task 3 Step 3）：初始焦点、Tab/Shift+Tab 圈闭、Escape
// 回调、关闭后焦点归还、无可聚焦元素时不拦截。工具只管理焦点，不决定是否可关闭。
import {afterEach,describe,expect,it,vi} from "vitest";
import {mount} from "@vue/test-utils";
import {defineComponent,h,nextTick,ref} from "vue";
import {useDialogFocus} from "./dialogFocus";

/** 测试宿主：容器（tabindex=-1）+ 三个动作按钮，DOM 顺序为 first、initial、last。
 * 「初始焦点」按钮刻意夹在中间，才能区分「聚焦 initialFocus」与「回退到容器内第一个
 * 可聚焦元素」两种行为。 */
function createHarness(onEscape: () => void) {
  return defineComponent({
    props: {
      open: {type: Boolean, required: true},
      withInitial: {type: Boolean, default: false},
      withActions: {type: Boolean, default: true},
    },
    setup(props) {
      const container = ref<HTMLElement | null>(null);
      const initial = ref<HTMLElement | null>(null);
      const first = ref<HTMLElement | null>(null);
      const last = ref<HTMLElement | null>(null);
      const {onDialogKeydown} = useDialogFocus({
        open: () => props.open,
        container,
        initialFocus: () => (props.withInitial ? initial.value : null),
        onEscape,
      });
      return () => h(
        "div",
        {ref: container, class: "dialog", tabindex: -1, onKeydown: onDialogKeydown},
        props.withActions
          ? [
            h("button", {class: "first", ref: (el: unknown) => { first.value = el as HTMLElement; }}, "一"),
            h("button", {class: "initial", ref: (el: unknown) => { initial.value = el as HTMLElement; }}, "二"),
            h("button", {class: "last", ref: (el: unknown) => { last.value = el as HTMLElement; }}, "三"),
          ]
          : [],
      );
    },
  });
}

function pressKey(target: Element, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", {bubbles: true, cancelable: true, ...init});
  target.dispatchEvent(event);
  return event;
}

/** 以「先聚焦外部触发元素、再打开对话框」的方式铺开场景，覆盖打开前焦点捕获。 */
async function openHarness(options: {withInitial?: boolean; withActions?: boolean} = {}, onEscape = vi.fn()) {
  const opener = document.createElement("button");
  document.body.appendChild(opener);
  opener.focus();
  const wrapper = mount(createHarness(onEscape), {props: {open: false, ...options}, attachTo: document.body});
  await wrapper.setProps({open: true});
  await nextTick();
  return {wrapper, opener, onEscape};
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("useDialogFocus", () => {
  it("打开时聚焦 initialFocus", async () => {
    const {wrapper} = await openHarness({withInitial: true});
    expect(document.activeElement).toBe(wrapper.find(".initial").element);
  });

  it("未提供 initialFocus 时回退到容器内第一个可聚焦元素", async () => {
    const {wrapper} = await openHarness();
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("Tab 在最后一个可聚焦元素上回绕到第一个", async () => {
    const {wrapper} = await openHarness();
    (wrapper.find(".last").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("Shift+Tab 在第一个可聚焦元素上回绕到最后一个", async () => {
    const {wrapper} = await openHarness();
    (wrapper.find(".first").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab", shiftKey: true});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".last").element);
  });

  it("Escape 只回调，不阻止默认行为（是否可关闭由调用方决定）", async () => {
    const {wrapper, onEscape} = await openHarness();
    const event = pressKey(wrapper.element, {key: "Escape"});
    expect(onEscape).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(false);
  });

  it("关闭时把焦点归还给打开前的元素", async () => {
    const {wrapper, opener} = await openHarness();
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(opener);
  });

  it("容器内没有可聚焦元素时聚焦容器本身，且不拦截 Tab", async () => {
    const {wrapper} = await openHarness({withActions: false});
    expect(document.activeElement).toBe(wrapper.element);
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(false);
  });
});
