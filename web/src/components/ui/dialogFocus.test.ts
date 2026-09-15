// @vitest-environment happy-dom
// 对话框焦点工具契约（PLAN-DM-029 Task 3 Step 3）：初始焦点、Tab/Shift+Tab 圈闭、Escape
// 回调（含事件透传）、关闭后焦点归还（焦点已移到容器外不抢、落在 `body` 无处停留时仍归还）、
// 无可聚焦元素时不拦截；以及可聚焦元素集合的边界：
// 隐藏态（自身/祖先/visibility）、`tabindex` 缺省与非法值、`contenteditable`、禁用、单选组
// （具名成组折叠、**无名 radio 各自独立停靠**）、`fieldset` 禁用继承缺口（本仓库当前不可达，
// 计划 Task 12 收口责任 F）。工具只管理焦点，不决定是否可关闭，也不阻止 Escape 的传播。
import {afterEach,describe,expect,it,vi} from "vitest";
import {mount} from "@vue/test-utils";
import {defineComponent,h,nextTick,ref,type Component,type VNode} from "vue";
import {createI18n} from "vue-i18n";
import {useDialogFocus} from "./dialogFocus";
import ConfirmModal from "./ConfirmModal.vue";
import UnsavedInputDialog from "./UnsavedInputDialog.vue";
import PropertyValueCompareDialog from "../properties/PropertyValueCompareDialog.vue";

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

/** 关闭落点解析器（可选）；与工具同名选项，用于「打开期间容器内状态已变」的场景。 */
type ReturnFocusResolver = () => HTMLElement | null | undefined;

/** 测试宿主：容器（tabindex=-1）+ 子节点。默认子节点是三个按钮，DOM 顺序为 first、initial、
 * last；「初始焦点」按钮刻意夹在中间，才能区分「聚焦 initialFocus」与「回退到容器内第一个
 * 可聚焦元素」两种行为。 */
function createHarness(onEscape: EscapeHandler, renderChildren?: HarnessChildren, returnFocus?: ReturnFocusResolver) {
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
        returnFocus,
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
async function openHarness(options: {withInitial?: boolean; withActions?: boolean} = {}, onEscape: EscapeHandler = vi.fn(), renderChildren?: HarnessChildren, returnFocus?: ReturnFocusResolver) {
  const opener = document.createElement("button");
  document.body.appendChild(opener);
  opener.focus();
  const wrapper = mount(createHarness(onEscape, renderChildren, returnFocus), {props: {open: false, ...options}, attachTo: document.body});
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

  it("关闭时焦点已在容器外则不抢回来（调用方可能在关闭时已把焦点移到别处）", async () => {
    const {wrapper, opener} = await openHarness();
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    // 容器仍挂载，所以走到的是 `contains` 判定而不是「容器已卸载」的兜底分支。
    expect(wrapper.element.contains(document.activeElement)).toBe(false);
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(outside);
    expect(document.activeElement).not.toBe(opener);
  });

  it("关闭时焦点落在 body 则仍归还给打开前的元素（此时没有别的落点可保留）", async () => {
    const {wrapper, opener} = await openHarness();
    (document.activeElement as HTMLElement | null)?.blur();
    expect(document.activeElement).toBe(document.body);
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

// 以下覆盖关闭落点：缺省归还「打开前的元素」，可用 `returnFocus` 覆盖（任务浮层打开后
// 切换过页签时，正确落点是当前激活入口而不是打开时那个元素；见 `TaskOverlay.vue`）。
// 无论哪种落点，关闭守卫都会拦下「焦点已被移到容器外」时的抢焦：解析器总会被调用，但只有
// `target.isConnected && shouldReturnFocus(container)` 同时成立才移动焦点。
describe("useDialogFocus 的关闭落点", () => {
  it("传入 returnFocus 时优先于打开前的元素", async () => {
    const target: {el: HTMLElement | null} = {el: null};
    const {wrapper, opener} = await openHarness({}, vi.fn(), undefined, () => target.el);
    target.el = wrapper.find(".last").element as HTMLElement;
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(target.el);
    expect(document.activeElement).not.toBe(opener);
  });

  it("returnFocus 返回 null 时回退到打开前的元素", async () => {
    const {wrapper, opener} = await openHarness({}, vi.fn(), undefined, () => null);
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(opener);
  });

  it("returnFocus 返回已从文档移除的元素时回退到打开前的元素", async () => {
    const detached = document.createElement("button");
    const {wrapper, opener} = await openHarness({}, vi.fn(), undefined, () => detached);
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(opener);
  });

  it("焦点已被移到容器外时 returnFocus 的落点也不抢回来", async () => {
    const target: {el: HTMLElement | null} = {el: null};
    const {wrapper} = await openHarness({}, vi.fn(), undefined, () => target.el);
    target.el = wrapper.find(".last").element as HTMLElement;
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(outside);
    expect(document.activeElement).not.toBe(target.el);
  });

  it("不传 returnFocus 时仍归还打开前的元素（新增选项不改变既有行为）", async () => {
    const {wrapper, opener} = await openHarness();
    expect(document.activeElement).not.toBe(opener);
    await wrapper.setProps({open: false});
    await nextTick();
    expect(document.activeElement).toBe(opener);
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

  it("无名 radio 各自独立停靠：不按组折叠，最后一个仍是端点", async () => {
    const {wrapper} = await openHarness({}, vi.fn(), markupChildren([
      '<button class="first">一</button>',
      '<input class="radio-a" type="radio">',
      '<input class="radio-b" type="radio">',
      '<input class="radio-c" type="radio">',
    ].join("")));
    // 无名 radio 不构成单选组（浏览器也不会把它们的 Tab 序列折叠），因此三个各自是停靠点，
    // `.radio-c` 是容器内最后一个停靠点：Tab 从它出发必须回绕到 `.first`。若被当成一组折叠，
    // 停靠点只剩组内首个 `.radio-a`，`.radio-c` 就不是端点、Tab 不会被拦截。
    (wrapper.find(".radio-c").element as HTMLElement).focus();
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

// ── Task 10 Step 3：四个模态的**接入**契约 ─────────────────────────────────
// 上面的用例覆盖**工具自身**；这里覆盖**接入正确性**——模态是否真的把初始焦点、Tab 圈闭、
// Escape、关闭归还接到了 `dialogFocus.ts` 上。与 `uiPrimitives.test.ts` 同一形态：一个
// describe 一个组件。happy-dom 不算布局也不实现原生 `<dialog>` 的焦点移动，因此：
// · 四个模态都是 `watch(() => props.open)` 的**变迁**才送焦点 → 必须先关后开；
// · `UnsavedInputDialog` 的 Escape 归原生 `cancel` 事件（happy-dom 不派发）→ 其 Escape
//   与「只作用最上层」由 `extensions-settings.spec.ts` 在真实浏览器里钉（不在此处假测）。
const modalMessages = {
  "zh-CN": {
    shell: {modal: {cancel: "取消", confirm: "确认", reversible: "可逆", irreversible: "不可逆", checkbox: "确认{reversibility}"}},
    properties: {compare: {close: "关闭", dialogHint: "对照说明", fieldMissing: "缺值"}},
  },
};

const openedModals: Array<{unmount: () => void}> = [];
afterEach(() => {
  for (const wrapper of openedModals.splice(0)) wrapper.unmount();
});

function mountModal(component: Component, props: Record<string, unknown>) {
  const i18n = createI18n({legacy: false, locale: "zh-CN", messages: modalMessages});
  // attachTo 必需：不入文档时 happy-dom 的 `.focus()` 不改 `document.activeElement`。
  const wrapper = mount(component, {props: {open: false, ...props}, global: {plugins: [i18n]}, attachTo: document.body});
  openedModals.push(wrapper);
  return wrapper;
}

async function setOpen(wrapper: {setProps: (props: Record<string, unknown>) => Promise<void>}, open: boolean) {
  await wrapper.setProps({open});
  await nextTick();
}

const activeElement = () => document.activeElement as HTMLElement | null;
const focusablesOf = (root: Element) =>
  Array.from(root.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select, textarea, a[href]'));

/** Tab 圈闭应当把焦点从末个可聚焦元素回绕到首个，反向同理。 */
async function expectTabTrap(wrapper: {find: (selector: string) => {element: Element; trigger: (event: string, options?: Record<string, unknown>) => Promise<void>}}, root: Element) {
  const nodes = focusablesOf(root);
  expect(nodes.length, "模态内应至少有 2 个可聚焦元素").toBeGreaterThan(1);
  nodes[nodes.length - 1]!.focus();
  await wrapper.find("[role=dialog], dialog").trigger("keydown", {key: "Tab"});
  expect(document.activeElement, "Tab 从末个回绕到首个").toBe(nodes[0]);
  nodes[0]!.focus();
  await wrapper.find("[role=dialog], dialog").trigger("keydown", {key: "Tab", shiftKey: true});
  expect(document.activeElement, "Shift+Tab 从首个回绕到末个").toBe(nodes[nodes.length - 1]);
}

describe("四个模态的焦点接入", () => {
  it("ConfirmModal：打开聚焦模态卡、Tab 圈闭、Escape 取消并停止传播、关闭归还开启控件", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const wrapper = mountModal(ConfirmModal, {title: "删除模板", message: "确认删除？", confirmText: "删除"});
    await setOpen(wrapper, true);
    const card = wrapper.find('[role="dialog"]').element as HTMLElement;
    expect(activeElement(), "打开时聚焦对话框本身（保持既有落点）").toBe(card);
    await expectTabTrap(wrapper, card);

    const escape = new KeyboardEvent("keydown", {key: "Escape", bubbles: true, cancelable: true});
    card.dispatchEvent(escape);
    await nextTick();
    expect(wrapper.emitted("cancel"), "Escape 触发取消").toHaveLength(1);
    expect(escape.defaultPrevented, "工具不阻止默认行为，由调用方表达").toBe(false);

    await setOpen(wrapper, false);
    expect(activeElement(), "关闭后归还开启控件").toBe(opener);
    opener.remove();
  });

  it("PropertyValueCompareDialog：接入工具后与 ConfirmModal 契约等价", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const wrapper = mountModal(PropertyValueCompareDialog, {heading: "值对照", stages: [{label: "图纸集", value: "滨河市政工程"}]});
    await setOpen(wrapper, true);
    const card = wrapper.find('[role="dialog"]').element as HTMLElement;
    expect(activeElement(), "打开时聚焦对话框本身").toBe(card);
    // 本对话框只有一个可聚焦元素（关闭）⇒ 圈闭实际上是**空转**的。这里如实断言这一点，
    // 而不是凭空造第二个可聚焦元素去「测」圈闭。真正演练首尾回绕的是 ConfirmModal（2 个）
    // 与 UnsavedInputDialog（3 个，且禁用项不应参与）。
    expect(focusablesOf(card).map((node) => node.textContent?.trim()), "值对照对话框的可聚焦元素").toEqual(["关闭"]);

    const escape = new KeyboardEvent("keydown", {key: "Escape", bubbles: true, cancelable: true});
    card.dispatchEvent(escape);
    await nextTick();
    expect(wrapper.emitted("close"), "Escape 关闭").toHaveLength(1);
    expect(escape.defaultPrevented, "Escape 必须停止传播（叠在其他模态之上时不连带关掉下层）").toBe(false);
    expect(escape.cancelBubble, "调用方在回调里 stopPropagation").toBe(true);

    await setOpen(wrapper, false);
    expect(activeElement(), "关闭后归还开启控件").toBe(opener);
    opener.remove();
  });

  it("UnsavedInputDialog：打开聚焦对话框、Tab 圈闭跳过禁用的「加入草稿并继续」、关闭归还开启控件", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const wrapper = mountModal(UnsavedInputDialog, {summary: "图纸 001 属性编辑", canSave: false});
    await setOpen(wrapper, true);
    const dialog = wrapper.find("dialog").element as HTMLElement;
    expect(dialog.contains(activeElement()), "打开时焦点在对话框内（显式 initialFocus，不依赖平台）").toBe(true);

    const nodes = focusablesOf(dialog);
    expect(nodes.map((node) => node.textContent?.trim()), "禁用项不参与停靠").not.toContain("加入草稿并继续");
    await expectTabTrap(wrapper, dialog);

    await setOpen(wrapper, false);
    expect(activeElement(), "关闭后归还开启控件（显式 returnFocus：工具内部 opener 读得太晚）").toBe(opener);
    opener.remove();
  });

  it("嵌套：各模态自己的 keydown 处理器互不串台（Tab 只在本模态内回绕）", async () => {
    const lower = mountModal(PropertyValueCompareDialog, {heading: "下层", stages: [{label: "a", value: "1"}]});
    const upper = mountModal(ConfirmModal, {title: "上层", message: "确认？", confirmText: "确定"});
    await setOpen(lower, true);
    await setOpen(upper, true);
    const lowerCard = lower.find('[role="dialog"]').element as HTMLElement;
    const upperCard = upper.find('[role="dialog"]').element as HTMLElement;

    await expectTabTrap(upper, upperCard);
    // 上层按 Tab 不得把焦点送进下层
    expect(lowerCard.contains(activeElement()), "上层圈闭不得溢入下层").toBe(false);

    const escape = new KeyboardEvent("keydown", {key: "Escape", bubbles: true, cancelable: true});
    upperCard.dispatchEvent(escape);
    await nextTick();
    expect(upper.emitted("cancel"), "Escape 只作用于事件所在的那一层").toHaveLength(1);
    expect(lower.emitted("close"), "下层不得被连带关闭").toBeUndefined();
  });
});
