<script setup lang="ts">
import {computed} from "vue";
import {UI_ICONS, type UiIconName} from "./icons";

// 本地 SVG 图标原语（PLAN-DM-029 Task 3 Step 4；ARCH-DM-007 §6）：几何数据只来自封闭
// 注册表，不渲染任意标记、不使用 `v-html`；尺寸消费 `--icon-size-*` 令牌，颜色随
// `currentColor` 继承承载控件的主题色。图标自身对读屏隐藏，可访问名称由承载它的按钮
// 或可见文字提供。
const props = defineProps<{
  name: UiIconName;
  size?: "sm" | "md" | "lg";
}>();

const definition = computed(() => UI_ICONS[props.name]);
const sizeClass = computed(() => `ui-icon--${props.size ?? "md"}`);
const fillColor = computed(() => (definition.value.filled === true ? "currentColor" : "none"));
const strokeColor = computed(() => (definition.value.filled === true ? "none" : "currentColor"));
</script>
<template>
  <svg
    class="ui-icon" :class="sizeClass"
    viewBox="0 0 24 24" aria-hidden="true" focusable="false"
    :fill="fillColor" :stroke="strokeColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
  >
    <template v-for="(shape, index) in definition.shapes" :key="index">
      <circle v-if="shape.kind === 'circle'" :cx="shape.cx" :cy="shape.cy" :r="shape.r" />
      <rect v-else-if="shape.kind === 'rect'" :x="shape.x" :y="shape.y" :width="shape.width" :height="shape.height" :rx="shape.rx" />
      <path v-else :d="shape.d" />
    </template>
  </svg>
</template>
<style scoped>
.ui-icon{display:block;flex:none;width:var(--icon-size-md);height:var(--icon-size-md)}
.ui-icon--sm{width:var(--icon-size-sm);height:var(--icon-size-sm)}
.ui-icon--lg{width:var(--icon-size-lg);height:var(--icon-size-lg)}
</style>
