<!-- 根组件：创建向导状态（门禁 + 自动保存 + API），按当前步骤只渲染该步字段。 -->
<script setup lang="ts">
import {nextTick, onBeforeUnmount, onMounted, provide} from "vue";
import WizardShell from "./components/WizardShell.vue";
import BuildStep from "./steps/BuildStep.vue";
import HandoffStep from "./steps/HandoffStep.vue";
import ProjectStep from "./steps/ProjectStep.vue";
import ReviewStep from "./steps/ReviewStep.vue";
import RulesStep from "./steps/RulesStep.vue";
import SheetsStep from "./steps/SheetsStep.vue";
import TemplatesStep from "./steps/TemplatesStep.vue";
import {createWizardStore, WIZARD_STORE_KEY} from "./composables/useWizardStore";

const store = createWizardStore();
provide(WIZARD_STORE_KEY, store);

function onDocumentFocusIn(event: FocusEvent): void {
  const field = (event.target as HTMLElement | null)?.getAttribute?.("data-field");
  if (field) {
    store.focusedField.value = field;
  }
}

/** 恢复聚焦字段：只在该步骤实际渲染了对应控件时聚焦。 */
async function restoreFocus(): Promise<void> {
  await nextTick();
  const field = store.focusedField.value;
  if (!field) {
    return;
  }
  document.querySelector<HTMLElement>(`[data-field="${field}"]`)?.focus();
}

onMounted(async () => {
  document.addEventListener("focusin", onDocumentFocusIn);
  await store.init();
  await restoreFocus();
});

onBeforeUnmount(() => {
  document.removeEventListener("focusin", onDocumentFocusIn);
});
</script>

<template>
  <WizardShell>
    <ProjectStep v-if="store.step.value === 1" />
    <RulesStep v-else-if="store.step.value === 2" />
    <SheetsStep v-else-if="store.step.value === 3" />
    <TemplatesStep v-else-if="store.step.value === 4" />
    <ReviewStep v-else-if="store.step.value === 5" />
    <BuildStep v-else-if="store.step.value === 6" />
    <HandoffStep v-else />
  </WizardShell>
</template>
