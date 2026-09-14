import {toValue, watch, type MaybeRefOrGetter} from "vue";

// 对话框焦点管理（PLAN-DM-029 Task 3 Step 3；ARCH-DM-007 §5）。
//
// 只做四件可判定的事：打开时把焦点送进对话框、Tab/Shift+Tab 在对话框内圈闭、
// Escape 回调、关闭时把焦点归还给打开前的元素。它**不**决定对话框是否可关闭、
// 不处理点击遮罩、不写 `aria-modal`；这些都留在调用方。
//
// 因此 Escape 只回调、不 `preventDefault`：调用方可能配置「不可 Escape 关闭」，
// 是否阻止默认行为属于调用方的判断。唯一会阻止默认行为的是 Tab 圈闭，因为回绕
// 必须挡住浏览器的默认焦点移动才生效。
//
// `FOCUSABLE_SELECTOR` 与 `layout/TaskOverlay.vue:77` 那份副本同源，但这里是 Task 4/8/9/10
// 共用的工具，所以在本文件补全：隐藏元素不过滤会让端点错位（把焦点 `focus()` 到不可聚焦
// 元素，或漏判端点后让 Tab 把焦点推出容器，而处理函数绑在容器上、焦点一出容器圈闭就失效）。
// Task 4 会把 `TaskOverlay.vue` 那份副本整体换成这个工具。
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

/** 无需 `tabindex` 就默认可聚焦的分支；用于判断 `tabindex` 取非法值时的真实可聚焦性。 */
const DEFAULT_FOCUSABLE_SELECTOR =
  "button,a[href],input,select,textarea,summary,[contenteditable]:not([contenteditable='false'])";
/** 被这些属性（或带这些属性的祖先）命中的元素不参与 Tab 循环。 */
const HIDDEN_SELECTOR = "[hidden],[inert],[aria-hidden='true' i]";

export interface DialogFocusOptions {
  open: MaybeRefOrGetter<boolean>;
  container: MaybeRefOrGetter<HTMLElement | null | undefined>;
  initialFocus?: MaybeRefOrGetter<HTMLElement | null | undefined>;
  onEscape?: () => void;
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
   * 没有 `tabindex` 属性时按规范可聚焦，但部分实现（含 happy-dom）的 `tabIndex` 返回 -1。 */
  function isTabStop(element: HTMLElement) {
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
      options.onEscape?.();
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
