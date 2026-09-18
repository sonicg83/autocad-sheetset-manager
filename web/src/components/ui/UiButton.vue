<script setup lang="ts">
import {computed} from "vue";

// 普通按钮原语（PLAN-DM-029 Task 3 Step 5；ARCH-DM-007 §5）：只负责 HTML 语义、variant、
// 尺寸档、禁用与加载状态，不承载业务确认或 API 调用。默认 `type="button"`，真正提交
// 表单必须由调用方显式声明 `type="submit"`。
//
// 尺寸档与 SPEC-DM-010 的生产密度一致：`default` 36px（`--button-height`）、
// `compact` 34px（`--control-height-compact`）；`link` 是文字按钮，不占控件高度但保留
// `--min-tap-height` 的下限。
//
// 可访问名称默认来自插槽里的可见文字；`label` 只给「插槽里没有可见文案」的用法（例如
// 只有图标或只有一个数字）提供 `aria-label`，与仓库既有按钮统一「可见文字 + aria-label」
// 的写法一致。纯图标按钮请用 `UiIconButton`（可访问名称必填）。
//
// 禁用有两种途径（PLAN-DM-034）：`disabled`/`loading` 走原生 `disabled`（不可聚焦、不进
// Tab 顺序）；`ariaDisabled` 是可聚焦的语义禁用——按钮仍可 Tab 聚焦并播报 `aria-disabled`，
// 但根按钮的内部 click 处理器会 `preventDefault` 并直接返回、不 emit `click`。原生 button
// 的 Enter/Space/程序化 `.click()` 最终都经过这一个守卫，页面无需另造键盘逻辑。
// `@click` 是显式声明的 emit：父监听器只由 `emit("click", event)` 触发，其余 class、ARIA
// 与原生属性仍按 Vue 默认 fallthrough 落到唯一根按钮。
const props = defineProps<{
  variant?: "primary" | "secondary" | "danger" | "link";
  size?: "default" | "compact";
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  loading?: boolean;
  ariaDisabled?: boolean;
  label?: string;
}>();

const emit = defineEmits<{click: [event: MouseEvent]}>();

const variantClass = computed(() => `ui-button--${props.variant ?? "secondary"}`);
const sizeClass = computed(() => `ui-button--${props.size ?? "default"}`);
const buttonType = computed(() => props.type ?? "button");
const busy = computed(() => (props.loading === true ? "true" : undefined));
const ariaDisabledState = computed(() => (props.ariaDisabled === true ? "true" : undefined));
const blocked = computed(() => props.disabled === true || props.loading === true || props.ariaDisabled === true);

function onActivate(event: MouseEvent) {
  if (blocked.value) {
    event.preventDefault();
    return;
  }
  emit("click", event);
}
</script>
<template>
  <button
    class="ui-button" :class="[variantClass, sizeClass, {'ui-button--loading': loading, 'ui-button--aria-disabled': ariaDisabled}]"
    :type="buttonType" :disabled="disabled || loading" :aria-disabled="ariaDisabledState" :aria-busy="busy" :aria-label="label"
    @click="onActivate"
  >
    <span v-if="loading" class="ui-button__spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>
<style scoped>
.ui-button{
  display:inline-flex;align-items:center;justify-content:center;gap:var(--space-2);
  box-sizing:border-box;height:var(--button-height);min-height:var(--min-tap-height);
  padding:0 var(--space-4);
  border:1px solid var(--color-border-strong);border-radius:var(--radius-md);
  background:var(--color-bg-surface);color:var(--color-text-primary);
  font-family:var(--font-ui);font-size:var(--button-font-size);
  cursor:pointer;
}
.ui-button--compact{height:var(--control-height-compact);padding:0 var(--space-3)}
.ui-button--primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.ui-button--primary:hover:not(:disabled):not(.ui-button--aria-disabled){background:var(--color-accent-hover);border-color:var(--color-accent-hover)}
.ui-button--primary:active:not(:disabled):not(.ui-button--aria-disabled){background:var(--color-accent-active);border-color:var(--color-accent-active)}
.ui-button--secondary:hover:not(:disabled):not(.ui-button--aria-disabled){background:var(--color-bg-muted)}
.ui-button--danger{background:var(--color-danger);border-color:var(--color-danger);color:var(--color-on-accent)}
.ui-button--link{height:auto;justify-content:flex-start;padding:0;border:0;background:none;color:var(--color-accent)}
.ui-button--link:hover:not(:disabled):not(.ui-button--aria-disabled){color:var(--color-accent-hover);text-decoration:underline}
.ui-button:disabled,.ui-button--aria-disabled{cursor:not-allowed}
.ui-button__spinner{
  flex:none;width:var(--icon-size-sm);height:var(--icon-size-sm);
  border:2px solid currentColor;border-right-color:transparent;border-bottom-color:transparent;
  border-radius:var(--radius-full);animation:ui-button-spin .7s linear infinite;
}
@keyframes ui-button-spin{to{transform:rotate(360deg)}}
</style>
