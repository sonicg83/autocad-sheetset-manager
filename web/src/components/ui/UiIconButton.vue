<script setup lang="ts">
import {computed} from "vue";
import UiIcon from "./UiIcon.vue";
import type {UiIconName} from "./icons";

// 独立图标按钮原语（PLAN-DM-029 Task 3 Step 5；ARCH-DM-007 §6）：点击面积固定为
// `--icon-button-size`（36×36px，SPEC-DM-010 生产密度），可访问名称由必填 `label`
// 提供，图标本身由 `UiIcon` 标记为对读屏隐藏。
//
// `label` 为空时不静默渲染一个没有名称的按钮：调用方漏传可访问名称属于契约错误，
// 这里直接抛出而不是降级成不可访问的控件（缺失时 Vue 只告警，运行时仍是 `undefined`，
// 所以要自己判空）。`aria-expanded`/`aria-pressed` 等状态属性不是本组件的 props，
// 由调用方以属性透传补充。
const props = defineProps<{
  icon: UiIconName;
  label: string;
  title?: string;
  disabled?: boolean;
}>();

if (typeof props.label !== "string" || props.label.trim() === "") {
  throw new Error("UiIconButton requires a non-empty label (accessible name)");
}

const tooltip = computed(() => props.title ?? props.label);
</script>
<template>
  <button type="button" class="ui-icon-button" :aria-label="label" :title="tooltip" :disabled="disabled">
    <UiIcon :name="icon" />
  </button>
</template>
<style scoped>
.ui-icon-button{
  display:inline-flex;align-items:center;justify-content:center;
  box-sizing:border-box;width:var(--icon-button-size);height:var(--icon-button-size);
  padding:0;border:1px solid transparent;border-radius:var(--radius-md);
  background:none;color:var(--color-text-secondary);cursor:pointer;
}
.ui-icon-button:hover:not(:disabled){background:var(--color-bg-muted);color:var(--color-text-primary)}
.ui-icon-button:disabled{cursor:not-allowed}
</style>
