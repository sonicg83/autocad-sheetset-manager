<!-- 字段错误摘要（ARCH-DB-001 §7：内联提示 + 可聚焦错误摘要）。
     后端字段诊断映射到具体控件：摘要获得焦点，条目点击跳转聚焦对应输入；
     行内错误由各步骤控件的 aria-invalid/aria-describedby 承接，Toast 只补充。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {injectWizardStore, stepOfField} from "../composables/useWizardStore";

const store = injectWizardStore();

const summary = ref<HTMLElement | null>(null);
const errors = computed(() =>
  store.fieldErrors.value.filter((error) => stepOfField(error.field) === store.step.value),
);

watch(errors, async (current) => {
  if (current.length > 0) {
    await nextTick();
    summary.value?.focus();
  }
});

function focusField(field: string): void {
  document.querySelector<HTMLElement>(`[data-field="${field}"]`)?.focus();
}
</script>

<template>
  <div
    v-if="errors.length > 0"
    ref="summary"
    data-testid="field-error-summary"
    role="alert"
    tabindex="-1"
    class="summary"
  >
    <p class="summary-title">存在需要修正的字段：</p>
    <ul>
      <li v-for="error in errors" :key="error.field">
        <button type="button" class="summary-item" @click="focusField(error.field)">
          {{ error.message }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.summary {
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: var(--border-width-1) solid var(--color-danger);
  border-radius: var(--radius-md);
  background: var(--color-danger-bg);
}

.summary-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-13);
  font-weight: 600;
  color: var(--color-danger);
}

.summary ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.summary-item {
  border: none;
  background: none;
  min-height: 28px;
  padding: 0;
  color: var(--color-danger);
  text-decoration: underline;
}
</style>
