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
const props = defineProps<{
  variant?: "primary" | "secondary" | "danger" | "link";
  size?: "default" | "compact";
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  loading?: boolean;
  label?: string;
}>();

const variantClass = computed(() => `ui-button--${props.variant ?? "secondary"}`);
const sizeClass = computed(() => `ui-button--${props.size ?? "default"}`);
const buttonType = computed(() => props.type ?? "button");
const busy = computed(() => (props.loading === true ? "true" : undefined));
</script>
<template>
  <button
    class="ui-button" :class="[variantClass, sizeClass, {'ui-button--loading': loading}]"
    :type="buttonType" :disabled="disabled || loading" :aria-busy="busy" :aria-label="label"
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
.ui-button--primary:hover:not(:disabled){background:var(--color-accent-hover);border-color:var(--color-accent-hover)}
.ui-button--primary:active:not(:disabled){background:var(--color-accent-active);border-color:var(--color-accent-active)}
.ui-button--secondary:hover:not(:disabled){background:var(--color-bg-muted)}
.ui-button--danger{background:var(--color-danger);border-color:var(--color-danger);color:var(--color-on-accent)}
.ui-button--link{height:auto;justify-content:flex-start;padding:0;border:0;background:none;color:var(--color-accent)}
.ui-button--link:hover:not(:disabled){color:var(--color-accent-hover);text-decoration:underline}
.ui-button:disabled{cursor:not-allowed}
.ui-button__spinner{
  flex:none;width:var(--icon-size-sm);height:var(--icon-size-sm);
  border:2px solid currentColor;border-right-color:transparent;border-bottom-color:transparent;
  border-radius:var(--radius-full);animation:ui-button-spin .7s linear infinite;
}
@keyframes ui-button-spin{to{transform:rotate(360deg)}}
</style>
