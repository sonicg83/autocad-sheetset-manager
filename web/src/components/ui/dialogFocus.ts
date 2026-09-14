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
export const FOCUSABLE_SELECTOR =
  'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]';

export interface DialogFocusOptions {
  open: MaybeRefOrGetter<boolean>;
  container: MaybeRefOrGetter<HTMLElement | null | undefined>;
  initialFocus?: MaybeRefOrGetter<HTMLElement | null | undefined>;
  onEscape?: () => void;
}

export function useDialogFocus(options: DialogFocusOptions) {
  const documentRef = typeof document === "undefined" ? null : document;
  let opener: HTMLElement | null = null;

  function focusables(): HTMLElement[] {
    const container = toValue(options.container);
    if (!container) return [];
    return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
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
