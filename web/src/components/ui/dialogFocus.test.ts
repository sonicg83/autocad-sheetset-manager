// @vitest-environment happy-dom
// 对话框焦点工具契约（PLAN-DM-029 Task 3 Step 3）：初始焦点、Tab/Shift+Tab 圈闭、Escape
// 回调、关闭后焦点归还、无可聚焦元素时不拦截。工具只管理焦点，不决定是否可关闭。
import {afterEach,describe,expect,it,vi} from "vitest";
import {mount} from "@vue/test-utils";
import {defineComponent,h,nextTick,ref,type VNode} from "vue";
import {useDialogFocus} from "./dialogFocus";

/** 子节点渲染函数；不传时用默认的三个按钮布局。 */
type HarnessChildren = () => VNode[];

/** 把一段原始标记放进容器：隐藏、`tabindex`、`contenteditable`、单选组等属性必须落到真实
 * 属性上（部分环境把属性当属性值属性反射得不完整，直接用夹具标记最可靠）。 */
function markupChildren(markup: string): HarnessChildren {
  return () => [h("div", {innerHTML: markup})];
}

/** 测试宿主：容器（tabindex=-1）+ 子节点。默认子节点是三个按钮，DOM 顺序为 first、initial、
 * last；「初始焦点」按钮刻意夹在中间，才能区分「聚焦 initialFocus」与「回退到容器内第一个
 * 可聚焦元素」两种行为。 */
function createHarness(onEscape: () => void, renderChildren?: HarnessChildren) {
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
        renderChildren
          ? renderChildren()
          : props.withActions
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
async function openHarness(options: {withInitial?: boolean; withActions?: boolean} = {}, onEscape = vi.fn(), renderChildren?: HarnessChildren) {
  const opener = document.createElement("button");
  document.body.appendChild(opener);
  opener.focus();
  const wrapper = mount(createHarness(onEscape, renderChildren), {props: {open: false, ...options}, attachTo: document.body});
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

// 以下四条覆盖可聚焦元素集合的三类缺口：隐藏元素、非默认可聚焦元素、单选组。
// 注：happy-dom 允许 `focus()` 落到隐藏元素上（真实浏览器不会，真实浏览器也不能把焦点停在
// `[hidden]`/`inert` 子树上），因此这里验证的是**端点过滤结果**（回绕点与落点），
// 而不是「浏览器拒焦」；真实布局可见性（0×0、离屏、`visibility` 叠加）留 Task 4 的 e2e。
describe("useDialogFocus 的可聚焦元素集合", () => {
  it("隐藏候选不参与端点：Tab 从真实最后一个可聚焦元素回绕到第一个", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="last">三</button>',
      '<button class="hidden-attribute" hidden>隐藏属性</button>',
      '<button class="hidden-aria" aria-hidden="true">对读屏隐藏</button>',
      '<button class="hidden-inert" inert="true">惰性</button>',
      '<button class="hidden-style" style="display:none">不显示</button>',
    ].join("")));
    (wrapper.find(".last").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("contenteditable 与任意非负 tabindex 参与端点，tabindex=-1 不参与", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<div class="editable" contenteditable="true">可编辑</div>',
      '<div class="indexed" tabindex="3">正索引</div>',
      '<div class="negative" tabindex="-1">负索引</div>',
    ].join("")));
    (wrapper.find(".indexed").element as HTMLElement).focus();
    const forward = pressKey(wrapper.element, {key: "Tab"});
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);

    const backward = pressKey(wrapper.element, {key: "Tab", shiftKey: true});
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".indexed").element);
  });

  it("单选组只在选中的那个上停靠：尾部未选中的 radio 不成为端点", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<input class="radio-checked" type="radio" name="group" checked>',
      '<input class="radio-tail" type="radio" name="group">',
    ].join("")));
    (wrapper.find(".radio-checked").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("单选组都没选中时按第一个停靠", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<input class="radio-a" type="radio" name="group">',
      '<input class="radio-b" type="radio" name="group">',
    ].join("")));
    (wrapper.find(".radio-a").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });
});
