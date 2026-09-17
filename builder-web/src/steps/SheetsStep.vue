<!-- 第 3 步 编排图纸（SPEC-DB-001 §2）：首期只允许唯一一张图纸，填图名。
     只展示本期派生值（最终图号、布局名、DWG 名），不出现推迟能力占位。 -->
<script setup lang="ts">
import FieldDiagnostics from "../components/FieldDiagnostics.vue";
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed} from "vue";
import {injectWizardStore, sheetNumber} from "../composables/useWizardStore";

const store = injectWizardStore();

const derived = computed(() => {
  const number = sheetNumber(store.draft.numbering.prefix, store.draft.numbering.start, store.draft.numbering.width);
  const title = store.draft.sheets[0]?.title ?? "";
  if (number === null || title.trim().length === 0) {
    return null;
  }
  const layoutName = `${number} ${title}`;
  return {layoutName, dwgName: `${layoutName}.dwg`};
});
</script>

<template>
  <section aria-labelledby="sheets-title">
    <GuidancePanel
      title="第3步 编排图纸"
      goal="填写唯一图纸的图名；最终图号、图名和文件名不得冲突且通过危险字符校验。"
      :hints="['首期一个项目只有一张图纸。']"
    />
    <FieldDiagnostics />

    <p class="field">
      <label class="field-label" for="s-title">图名</label>
      <input id="s-title" v-model="store.draft.sheets[0]!.title" data-field="sheets.0.title" type="text" /> :disabled="store.buildRunning.value"
    </p>
    <dl v-if="derived" class="derived">
      <div>
        <dt>布局名</dt>
        <dd>{{ derived.layoutName }}</dd>
      </div>
      <div>
        <dt>DWG 文件名</dt>
        <dd>{{ derived.dwgName }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.derived {
  margin: var(--space-4) 0 0;
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
}

.derived dt {
  font-size: var(--font-size-13);
  color: var(--color-text-secondary);
}

.derived dd {
  margin: var(--space-1) 0 0;
  font-weight: 600;
}
</style>
