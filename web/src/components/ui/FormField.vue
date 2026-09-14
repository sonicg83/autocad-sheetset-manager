<script setup lang="ts">
import {computed} from "vue";

// 字段包装原语（PLAN-DM-029 Task 3 Step 5；ARCH-DM-007 §5）：负责可见 label、hint/error
// 元素及其 id、以及 `aria-describedby` 的关联；`invalid` 由 `error` 派生，不需要调用方
// 重复声明。插槽属性（`id`/`describedBy`/`invalid`）下发给插槽内的控件。
//
// `label` 是必填 props：可见标签是字段的可访问名称来源，缺省不渲染等价于字段无法访问。
// `hint`/`error` 只是文案，组件不判断错误内容是否合法，也不决定何时显示。
const props = defineProps<{
  label: string;
  id?: string;
  hint?: string;
  error?: string;
}>();

let idSequence = 0;
const fallbackId = `form-field-${(idSequence += 1)}`;
const controlId = computed(() => props.id ?? fallbackId);
const hintId = computed(() => `${controlId.value}-hint`);
const errorId = computed(() => `${controlId.value}-error`);
const invalid = computed(() => Boolean(props.error));
const describedBy = computed(() => {
  const ids: string[] = [];
  if (props.hint) ids.push(hintId.value);
  if (props.error) ids.push(errorId.value);
  return ids.length === 0 ? undefined : ids.join(" ");
});
</script>
<template>
  <div class="form-field" :class="{'form-field--invalid': invalid}">
    <label class="form-field__label" :for="controlId">{{ label }}</label>
    <slot :id="controlId" :describedBy="describedBy" :invalid="invalid" />
    <p v-if="hint" :id="hintId" class="form-field__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="form-field__error">{{ error }}</p>
  </div>
</template>
<style scoped>
.form-field{display:flex;flex-direction:column;gap:var(--space-1);min-width:0}
.form-field__label{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-secondary)}
.form-field__hint{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-muted)}
.form-field__error{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-danger)}
</style>
