import {toValue, watch, type MaybeRefOrGetter} from "vue";

// 对话框焦点管理（PLAN-DM-029 Task 3 Step 3；ARCH-DM-007 §5）。
//
// 只做四件可判定的事：打开时把焦点送进对话框、Tab/Shift+Tab 在对话框内圈闭、
// Escape 回调、关闭时把焦点归还给打开前的元素。它**不**决定对话框是否可关闭、
// 不处理点击遮罩、不写 `aria-modal`；这些都留在调用方。
//
// 因此 Escape 只回调、不 `preventDefault`也不 `stopPropagation`：调用方可能配置「不可 Escape
// 关闭」，也可能像现网模态那样依赖 `stopPropagation` 挡住文档级 Escape 处理器（`ActionDock`/
// `SheetsView`/`FieldBrowser` 都有文档级 Escape 监听）。是否阻止行为、是否停止传播都属于调用方
// 的判断，所以工具把原始的 `KeyboardEvent` 交给回调，由调用方表达原有传播语义。唯一会阻止
// 默认行为的是 Tab 圈闭，因为回绕必须挡住浏览器的默认焦点移动才生效。
//
// 圈闭生效的前提：
// ① 模态/浮层**内部不得对 Tab 做 `stopPropagation`**，否则事件到不了容器，圈闭静默失效；
// ② 打开时的初始焦点必须落在容器内的真实停靠点上（见 `isTabStop` 的禁用过滤）。
//
// `FOCUSABLE_SELECTOR` 是**候选**集合，不等于 Tab 停靠点集合：候选还要再过 `isTabStop`
// （禁用、负 `tabindex`、非法 `tabindex`）与 `isHidden`（隐藏态）两道过滤，且单选组会折叠为
// 一个停靠点。它由 `layout/TaskOverlay.vue:77` 那份副本同源扩写而来，**只在本模块内部消费**
// （外部不要拿它当停靠点列表；计划 Task 4 Step 3 会把那份副本整体换成这个工具）。
export const FOCUSABLE_SELECTOR = [
  "button:not(:disabled)",
  "a[href]",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "summary",
  "[contenteditable]:not([contenteditable='false'])",
  "[tabindex]",
].join(",");

/** 无需 `tabindex` 就默认可聚焦的分支；用于判断 `tabindex` 取非法值时（按 HTML 规范等同
 * 缺省）元素是否真的可聚焦。这里同样排除禁用元素，与 `isTabStop` 的快速路径保持一致。 */
const DEFAULT_FOCUSABLE_SELECTOR =
  "button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[contenteditable]:not([contenteditable='false'])";
/** 被这些属性（或带这些属性的祖先）命中的元素不参与 Tab 循环。
 *
 * 排除 `aria-hidden="true"` 是**对浏览器焦点可达性的有意偏离**：浏览器仍允许聚焦这类元素，
 * 但「对读屏隐藏却又可聚焦」在界面里几乎总是模板缺陷。取舍理由是 under-filter 更常见也更
 * 隐蔽（漏掉一个隐藏元素会让端点错位、圈闭静默失效），宁可多排除。已知代价：极端模板
 * （对话框内只有 `aria-hidden="true"` 的可聚焦元素）会得到空集合，此时圈闭静默关闭；
 * 真实浏览器的可见性叠加（`0×0`、离屏、`visibility` 叠加）留 Task 4 的 e2e。 */
const HIDDEN_SELECTOR = "[hidden],[inert],[aria-hidden='true' i]";

export interface DialogFocusOptions {
  open: MaybeRefOrGetter<boolean>;
  container: MaybeRefOrGetter<HTMLElement | null | undefined>;
  initialFocus?: MaybeRefOrGetter<HTMLElement | null | undefined>;
  /** Escape 回调；收到原始的 `KeyboardEvent`。工具自己不 `preventDefault`、不 `stopPropagation`，
   * 是否需要阻止行为/停止传播由调用方在那个事件上表达。 */
  onEscape?: (event: KeyboardEvent) => void;
}

/** 具名 `radio` 才成组（无名 radio 各自独立停靠）；用 `tagName` 判定而不是 `instanceof`，
 * 避免跨 realm（iframe、测试环境的 DOM 实现）时判定失败。 */
function isNamedRadio(element: HTMLElement): element is HTMLInputElement {
  return element.tagName === "INPUT" && (element as HTMLInputElement).type === "radio" && (element as HTMLInputElement).name !== "";
}

export function useDialogFocus(options: DialogFocusOptions) {
  const documentRef = typeof document === "undefined" ? null : document;
  let opener: HTMLElement | null = null;

  /** `tabindex` 为显式负值（含 `-1`）→ 不参与 Tab 循环；非法值按 HTML 规范等同缺省，
   * 此时退回「元素本身是否默认可聚焦」。不用 `element.tabIndex` 判定：`contenteditable`
   * 没有 `tabindex` 属性时按规范可聚焦，但部分实现（含 happy-dom）的 `tabIndex` 返回 -1。
   *
   * 禁用元素一律排除：候选集合的 `[tabindex]` 分支会把 `<button disabled tabindex="0">`
   * 变成候选，若放行，它出现在序列首位时 `focusInitial()` 会把焦点留在对话框外，之后键盘事件
   * 不再进入容器，圈闭静默失效——比「Tab 无响应」严重得多。判定用 `[disabled]` 属性而不是
   * `:disabled`：选择器实现对禁用继承的建模不一致（happy-dom 的 `:disabled` 只看元素自身是否
   * 带该属性）。已知缺口：`fieldset[disabled]` 的后代控件不自带该属性，本实现仍把它算作
   * 停靠点（真实浏览器里它不可聚焦），留 Task 4 的 e2e 覆盖。 */
  function isTabStop(element: HTMLElement) {
    if (element.matches("[disabled]")) return false;
    const attribute = element.getAttribute("tabindex");
    if (attribute === null) return true;
    const parsed = Number.parseInt(attribute, 10);
    return Number.isNaN(parsed) ? element.matches(DEFAULT_FOCUSABLE_SELECTOR) : parsed >= 0;
  }

  /** 隐藏判定：属性（含祖先）优先，不受 UA 样式表的实现差异影响（happy-dom 就不把
   * `[hidden]` 算成 `display:none`）；再查计算样式——`display` 不继承，必须逐级向上；
   * `visibility` 继承但允许后代用 `visibility:visible` 覆盖，所以只看元素自身。 */
  function isHidden(element: HTMLElement) {
    if (element.closest(HIDDEN_SELECTOR) !== null) return true;
    const view = element.ownerDocument?.defaultView;
    if (view === null || view === undefined || typeof view.getComputedStyle !== "function") return false;
    for (let node: HTMLElement | null = element; node !== null; node = node.parentElement) {
      if (view.getComputedStyle(node).display === "none") return true;
    }
    const own = view.getComputedStyle(element).visibility;
    return own === "hidden" || own === "collapse";
  }

  /** 单选组在 Tab 序列里只有一个停靠点：组内已选中的那个，都没选中时算第一个。
   * 组内最后一个 radio 未选中时，按 DOM 顺序取「最后一个候选」会得到浏览器不会停留的
   * 元素，端点判定随之错位，Tab 会把焦点推出容器。 */
  function radioStopPoints(elements: HTMLElement[]) {
    const groups = new Map<HTMLFormElement | null, Map<string, HTMLInputElement[]>>();
    for (const element of elements) {
      if (!isNamedRadio(element)) continue;
      const byName = groups.get(element.form) ?? new Map<string, HTMLInputElement[]>();
      const members = byName.get(element.name) ?? [];
      members.push(element);
      byName.set(element.name, members);
      groups.set(element.form, byName);
    }
    const stops = new Set<HTMLElement>();
    for (const byName of groups.values()) {
      for (const members of byName.values()) stops.add(members.find((member) => member.checked) ?? members[0]);
    }
    return stops;
  }

  function focusables(): HTMLElement[] {
    const container = toValue(options.container);
    if (!container) return [];
    const candidates = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter((element) => isTabStop(element) && !isHidden(element));
    const radioStops = radioStopPoints(candidates);
    return candidates.filter((element) => !isNamedRadio(element) || radioStops.has(element));
  }

  function focusInitial() {
    const target = toValue(options.initialFocus) ?? focusables()[0] ?? toValue(options.container);
    target?.focus();
  }

  /** 关闭时是否把焦点交还给打开前的元素。
   *
   * 焦点已被移到对话框外（例如调用方关闭后主动聚焦了别处）时不抢焦点；容器用
   * `v-if` 随 `open` 卸载时读到的容器为 `null`，此时焦点已无处停留，按建议交还。
   */
  function shouldReturnFocus(container: HTMLElement | null | undefined) {
    const active = documentRef?.activeElement ?? null;
    if (active === null || active === documentRef?.body) return true;
    if (!container) return true;
    return container.contains(active);
  }

  watch(
    () => toValue(options.open),
    (open) => {
      const container = toValue(options.container);
      if (open) {
        const active = documentRef?.activeElement ?? null;
        opener = active instanceof HTMLElement ? active : null;
        focusInitial();
        return;
      }
      if (opener && opener.isConnected && shouldReturnFocus(container)) opener.focus();
      opener = null;
    },
    {immediate: true, flush: "post"},
  );

  /** 绑定在对话框外层元素的 `keydown` 上。 */
  function onDialogKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      options.onEscape?.(event);
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusables();
    if (items.length === 0) return;
    const active = documentRef?.activeElement ?? null;
    const first = items[0];
    const last = items[items.length - 1];
    const atEdge = event.shiftKey
      ? active === first || active === toValue(options.container)
      : active === last;
    if (!atEdge) return;
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  }

  return {onDialogKeydown};
}
