<!-- 第 2 步 配置规则（SPEC-DB-001 §2）：AutoCAD 2016/2020、图号前缀/起始序号/位数、
     示例图号预览。派生值展示为只读输出，不引入后端之外的校验规则。 -->
<script setup lang="ts">
import FieldDiagnostics from "../components/FieldDiagnostics.vue";
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed} from "vue";
import {injectWizardStore, sheetNumber} from "../composables/useWizardStore";

const store = injectWizardStore();

const preview = computed(() =>
  sheetNumber(store.draft.numbering.prefix, store.draft.numbering.start, store.draft.numbering.width),
);

function onStartInput(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  store.draft.numbering.start = Number.isFinite(value) ? Math.trunc(value) : 0;
}

function onWidthInput(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  store.draft.numbering.width = Number.isFinite(value) ? Math.trunc(value) : 1;
}
</script>

<template>
  <section aria-labelledby="rules-title">
    <GuidancePanel
      title="第2步 配置规则"
      goal="选择 AutoCAD 2016/2020，填写图号前缀、起始序号和位数。"
      :hints="['示例图号 = 前缀 + 按位数补零的起始序号。']"
    />
    <FieldDiagnostics />

    <fieldset class="field">
      <legend class="field-label">AutoCAD 版本</legend>
      <label class="radio"><input v-model="store.draft.cad_version" data-field="cad_version" type="radio" value="2016" name="cad_version" /> AutoCAD 2016</label> :disabled="store.buildRunning.value"
      <label class="radio"><input v-model="store.draft.cad_version" data-field="cad_version" type="radio" value="2020" name="cad_version" /> AutoCAD 2020</label> :disabled="store.buildRunning.value"
    </fieldset>
    <p class="field">
      <label class="field-label" for="r-prefix">图号前缀</label>
      <input id="r-prefix" v-model="store.draft.numbering.prefix" data-field="numbering.prefix" type="text" /> :disabled="store.buildRunning.value"
    </p>
    <p class="field">
      <label class="field-label" for="r-start">起始序号</label>
      <input
        id="r-start"
        :value="store.draft.numbering.start"
        data-field="numbering.start"
        type="number"
        min="0"
        max="999999"
        @input="onStartInput"
      />
    </p>
    <p class="field">
      <label class="field-label" for="r-width">位数</label>
      <input
        id="r-width"
        :value="store.draft.numbering.width"
        data-field="numbering.width"
        type="number"
        min="1"
        max="6"
        @input="onWidthInput"
      />
    </p>
    <p class="field">
      <span class="field-label">示例图号</span>
      <output v-if="preview !== null" data-testid="sheet-number-preview" class="preview">{{ preview }}</output>
      <output v-else data-testid="sheet-number-preview" class="preview invalid">规则尚未生效</output>
    </p>
  </section>
</template>

<style scoped>
fieldset.field {
  border: none;
  padding: 0;
  margin: 0 0 var(--space-4);
}

.radio {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-right: var(--space-5);
}

.radio input {
  width: auto;
  min-height: auto;
}

.preview {
  display: inline-block;
  min-height: 38px;
  padding: 0 var(--space-3);
  line-height: 38px;
  border: var(--border-width-1) dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-bg-muted);
  font-family: inherit;
}

.preview.invalid {
  color: var(--color-warning);
}
</style>
