<script setup lang="ts">
import {computed} from "vue";

// 选择器原语（PLAN-DM-029 Task 3 Step 5；ARCH-DM-007 §5）：只负责字体、盒模型、焦点、
// 禁用与错误态透传；`<option>` 由调用方经默认插槽提供，选项数据来自调用方的业务状态。
//
// 默认高度固定消费 `--input-height`（38px，SPEC-DM-010 生产输入密度），与 `UiInput`
// 同一档；可见 label 的提供方式与 `UiInput` 一致（自带 `label` 或由 `FormField` 提供）。
const props = defineProps<{
  modelValue?: string;
  label?: string;
  id?: string;
  describedBy?: string;
  invalid?: boolean;
  disabled?: boolean;
}>();
const emit = defineEmits<{"update:modelValue": [value: string]}>();

// 属性透传落到真正的 `<select>` 上，根元素只承载布局类。
defineOptions({inheritAttrs: false});

let idSequence = 0;
const fallbackId = `ui-select-${(idSequence += 1)}`;
const controlId = computed(() => props.id ?? fallbackId);

function onChange(event: Event) {
  emit("update:modelValue", (event.target as HTMLSelectElement).value);
}
</script>
<template>
  <span class="ui-select" :class="{'ui-select--invalid': invalid, 'ui-select--disabled': disabled}">
    <label v-if="label" class="ui-select__label" :for="controlId">{{ label }}</label>
    <select
      v-bind="$attrs" class="ui-select__control" :id="controlId"
      :value="modelValue" :disabled="disabled"
      :aria-describedby="describedBy" :aria-invalid="invalid ? 'true' : undefined"
      @change="onChange"
    >
      <slot />
    </select>
  </span>
</template>
<style scoped>
.ui-select{display:flex;flex-direction:column;gap:var(--space-1);min-width:0}
.ui-select__label{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-secondary)}
.ui-select__control{
  box-sizing:border-box;width:100%;height:var(--input-height);
  padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);
  background:var(--color-bg-surface);color:var(--color-text-primary);
  font-family:var(--font-ui);font-size:var(--input-font-size);
}
.ui-select__control:disabled{color:var(--color-text-muted);cursor:not-allowed}
.ui-select--invalid .ui-select__control{border-color:var(--color-danger)}
</style>
