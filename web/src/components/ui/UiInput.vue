<script setup lang="ts">
import {computed} from "vue";
import {nextInstanceId} from "./instanceId";

// 文本输入原语（PLAN-DM-029 Task 3 Step 5；ARCH-DM-007 §5）：只负责字体、盒模型、
// 焦点、禁用与错误态透传，不做业务校验，也不导入业务 composable 或 API 类型。
//
// 可见 label 有两种提供方式，同一字段只用其中一种：
// - 自带 `label`：控件渲染 `label[for]` 并关联到自己的 `id`，用于工具栏搜索框等独立场景；
// - 由 `FormField` 提供：`FormField` 渲染可见 label，经插槽把 `id`/`describedBy` 下发，
//   此时不要再传 `label`，否则会渲染两个可见标签。
// 控件始终有 `id`（`label[for]` 与 `aria-describedby` 都以它为锚），未传时用
// `nextInstanceId()` 生成同页唯一的兜底 id（模块级计数器，见 `instanceId.ts`）；
// 属性透传落到真正的 `<input>` 上（`type`/`placeholder`/`autocomplete`/`aria-*`）。
const props = defineProps<{
  modelValue?: string;
  label?: string;
  id?: string;
  type?: string;
  describedBy?: string;
  invalid?: boolean;
  disabled?: boolean;
  readonly?: boolean;
}>();
const emit = defineEmits<{"update:modelValue": [value: string]}>();

// 属性透传落到真正的 `<input>` 上，根元素只承载布局类。
defineOptions({inheritAttrs: false});

const fallbackId = nextInstanceId("ui-input");
const controlId = computed(() => props.id ?? fallbackId);

function onInput(event: Event) {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>
<template>
  <span class="ui-input" :class="{'ui-input--invalid': invalid, 'ui-input--disabled': disabled}">
    <label v-if="label" class="ui-input__label" :for="controlId">{{ label }}</label>
    <input
      v-bind="$attrs" class="ui-input__control" :id="controlId" :type="type ?? 'text'"
      :value="modelValue" :disabled="disabled" :readonly="readonly"
      :aria-describedby="describedBy" :aria-invalid="invalid ? 'true' : undefined"
      @input="onInput"
    >
  </span>
</template>
<style scoped>
.ui-input{display:flex;flex-direction:column;gap:var(--space-1);min-width:0}
.ui-input__label{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-secondary)}
.ui-input__control{
  box-sizing:border-box;width:100%;height:var(--input-height);
  padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);
  background:var(--color-bg-surface);color:var(--color-text-primary);
  font-family:var(--font-ui);font-size:var(--input-font-size);
}
.ui-input__control:disabled{color:var(--color-text-muted);cursor:not-allowed}
.ui-input:not(.ui-input--invalid) .ui-input__control:hover:not(:disabled){border-color:var(--color-accent)}
.ui-input--invalid .ui-input__control{border-color:var(--color-danger)}
</style>
