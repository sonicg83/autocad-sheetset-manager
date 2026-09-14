// @vitest-environment happy-dom
// 对话框焦点工具契约（PLAN-DM-029 Task 3 Step 3）：初始焦点、Tab/Shift+Tab 圈闭、Escape
// 回调（含事件透传）、关闭后焦点归还、无可聚焦元素时不拦截；以及可聚焦元素集合的边界：
// 隐藏态（自身/祖先/visibility）、`tabindex` 缺省与非法值、`contenteditable`、禁用、单选组、
// `fieldset` 禁用继承缺口（本仓库当前不可达，计划 Task 12 收口责任 F）。工具只管理焦点，
// 不决定是否可关闭，也不阻止 Escape 的传播。
import {afterEach,describe,expect,it,vi} from "vitest";
import {mount} from "@vue/test-utils";
import {defineComponent,h,nextTick,ref,type VNode} from "vue";
import {useDialogFocus} from "./dialogFocus";

/** 子节点渲染函数；不传时用默认的三个按钮布局。 */
type HarnessChildren = () => VNode[];

/** Escape 回调；工具把原始的 `KeyboardEvent` 交给它，是否 `preventDefault`/`stopPropagation`
 * 由调用方决定（现网多个模态依赖 `stopPropagation` 挡住文档级 Escape 处理器）。 */
type EscapeHandler = (event: KeyboardEvent) => void;

/** 把一段原始标记放进容器：隐藏、`tabindex`、`contenteditable`、单选组等属性必须落到真实
 * 属性上（部分环境把属性当属性值属性反射得不完整，直接用夹具标记最可靠）。 */
function markupChildren(markup: string): HarnessChildren {
  return () => [h("div", {innerHTML: markup})];
}

/** 测试宿主：容器（tabindex=-1）+ 子节点。默认子节点是三个按钮，DOM 顺序为 first、initial、
 * last；「初始焦点」按钮刻意夹在中间，才能区分「聚焦 initialFocus」与「回退到容器内第一个
 * 可聚焦元素」两种行为。 */
function createHarness(onEscape: EscapeHandler, renderChildren?: HarnessChildren) {
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
async function openHarness(options: {withInitial?: boolean; withActions?: boolean} = {}, onEscape: EscapeHandler = vi.fn(), renderChildren?: HarnessChildren) {
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

  it("Escape 回调收到该 KeyboardEvent，且工具既不阻止默认行为也不停止传播", async () => {
    const received: KeyboardEvent[] = [];
    const {wrapper} = await openHarness({}, (event) => { received.push(event); });
    let bubbledToBody = false;
    const onBodyKeydown = () => { bubbledToBody = true; };
    document.body.addEventListener("keydown", onBodyKeydown);
    const event = pressKey(wrapper.element, {key: "Escape"});
    document.body.removeEventListener("keydown", onBodyKeydown);
    expect(received).toEqual([event]);
    expect(event.defaultPrevented).toBe(false);
    expect(bubbledToBody).toBe(true);
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

// 以下覆盖可聚焦元素集合的边界：隐藏元素（自身属性、祖先、`visibility`）、非默认可聚焦元素
// （含 `tabindex` 缺省/非法值）、禁用元素、单选组，以及 `fieldset` 禁用继承的已知缺口
// （缺口只能从 `[tabindex]` 分支漏入，而本仓库没有「禁用 `fieldset` + 非负 `tabindex`」的写法，
// 属计划 Task 12 收口责任 F）。
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

  it("单选组按选中的那个停靠：选中项在中间时不退回组内首位", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<input class="radio-a" type="radio" name="group">',
      '<input class="radio-checked" type="radio" name="group" checked>',
      '<input class="radio-c" type="radio" name="group">',
    ].join("")));
    (wrapper.find(".radio-checked").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("祖先内联 display:none 的后代不参与端点（隐藏判定要沿祖先链上溯）", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="last">三</button>',
      '<div style="display:none"><button class="descendant-display">祖先不显示</button></div>',
    ].join("")));
    (wrapper.find(".last").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("祖先带 aria-hidden/inert 的后代不参与端点（属性判定要走 closest）", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="last">三</button>',
      '<div aria-hidden="true"><button class="descendant-aria">祖先对读屏隐藏</button></div>',
      '<div inert><button class="descendant-inert">祖先惰性</button></div>',
    ].join("")));
    (wrapper.find(".last").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("visibility:hidden 的候选不参与端点（可见性只看元素自身）", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="last">三</button>',
      '<button class="invisible" style="visibility:hidden">不可见</button>',
    ].join("")));
    (wrapper.find(".last").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("tabindex 取非法值时：非默认可聚焦元素不作停靠点，按钮按规范仍作停靠点", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="invalid-index" tabindex="abc">非法 tabindex 的按钮</button>',
      '<div class="invalid-div" tabindex="abc">非法 tabindex 的 div</div>',
    ].join("")));
    (wrapper.find(".invalid-index").element as HTMLElement).focus();
    const atLastStop = pressKey(wrapper.element, {key: "Tab"});
    expect(atLastStop.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);

    (wrapper.find(".invalid-div").element as HTMLElement).focus();
    const atNonStop = pressKey(wrapper.element, {key: "Tab"});
    expect(atNonStop.defaultPrevented).toBe(false);
  });

  it("contenteditable 不带 tabindex 时仍作端点（属性缺省分支）", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<div class="editable" contenteditable="true">可编辑</div>',
    ].join("")));
    (wrapper.find(".editable").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });

  it("禁用元素不作停靠点：带 tabindex 的禁用按钮与禁用输入都被排除", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<button class="last">三</button>',
      '<button class="own-disabled" disabled tabindex="0">禁用按钮</button>',
      '<input class="own-disabled-input" disabled tabindex="3">',
    ].join("")));
    (wrapper.find(".last").element as HTMLElement).focus();
    const forward = pressKey(wrapper.element, {key: "Tab"});
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);

    (wrapper.find(".first").element as HTMLElement).focus();
    const backward = pressKey(wrapper.element, {key: "Tab", shiftKey: true});
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".last").element);
  });

  it("打开时初始焦点跳过位于首位的禁用元素（否则焦点留在对话框外，圈闭等于没开）", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="own-disabled" disabled tabindex="0">禁用按钮</button>',
      '<button class="real-first">真正第一个</button>',
    ].join("")));
    expect(document.activeElement).toBe(wrapper.find(".real-first").element);
  });

  // 已知缺口（记录当前行为，不是期望行为，**本仓库当前不可达**）：`fieldset[disabled]` 的后代
  // 控件在真实浏览器里不可聚焦，但本实现按元素自身的 `[disabled]` 属性判定（happy-dom 也不建模
  // 禁用继承），因此该子控件仍算停靠点。缺口只能从候选集合的 `[tabindex]` 分支漏入（`button`/
  // `input` 分支由真实浏览器的 `:disabled` 继承挡住）；仓库唯一的 `<fieldset disabled>`
  // （`SheetCatalogSettingsPanel.vue:84-85` 只读态）内没有非负 `tabindex`，所以不可达。
  // 登记为计划 Task 12 收口责任 F（含不能用朴素 `closest("fieldset[disabled]")` 的原因）；
  // 修好本缺口时本条需同步更新。
  it("已知缺口：fieldset 禁用继承未建模，其子控件仍算停靠点", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<fieldset disabled><button class="in-fieldset" tabindex="0">字段集内</button></fieldset>',
    ].join("")));
    (wrapper.find(".in-fieldset").element as HTMLElement).focus();
    const event = pressKey(wrapper.element, {key: "Tab"});
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(wrapper.find(".first").element);
  });
});
