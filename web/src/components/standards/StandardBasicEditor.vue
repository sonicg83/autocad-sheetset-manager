<script setup lang="ts">
// 基本信息共享编辑器缓冲；编号位数沿用草稿结构诊断与保存门禁。
import {computed} from "vue";
import UiInput from "../ui/UiInput.vue";
import {nextInstanceId} from "../ui/instanceId";
import type {DraftDiagnostic, DraftDocument} from "../../features/standards/draftModel";

const props = defineProps<{document: DraftDocument; diagnostics: DraftDiagnostic[]}>();
const helpId = nextInstanceId("numbering-digits-help");
const errorId = `${helpId}-error`;
const numberingInvalid = computed(() => props.diagnostics.some(item => item.code === "STANDARD_NUMBERING_INVALID"));
const cadVersionsText = computed({
  get: () => props.document.supported_cad_versions.join(", "),
  set: (value: string) => {
    props.document.supported_cad_versions = value.split(",").map(item => item.trim()).filter(Boolean);
  },
});
const numberingDigitsText = computed({
  get: () => Number.isFinite(props.document.numbering.digits) ? String(props.document.numbering.digits) : "",
  set: (value: string) => {
    const digits = value.trim() === "" ? Number.NaN : Number(value);
    // 空值保留为未完成输入，由既有诊断阻止保存，不能自动恢复默认值。
    props.document.numbering.digits = Number.isFinite(digits) ? digits : Number.NaN;
  },
});
</script>

<template>
  <section class="basic-section" role="region" :aria-label="$t('standards.sections.basic')">
    <h3 class="section-title">{{ $t("standards.sections.basic") }}</h3>
    <UiInput :model-value="document.standard_id" :label="$t('standards.detail.standardId')" readonly />
    <p class="field-note" role="note" data-testid="identity-readonly-note">{{ $t("standards.editor.identityReadonlyHint") }}</p>
    <UiInput v-model="cadVersionsText" :label="$t('standards.editor.cadVersionsLabel')" />
    <div class="numbering-field">
      <UiInput
        v-model="numberingDigitsText"
        :label="$t('standards.editor.numberingDigitsLabel')"
        type="number" min="1" step="1"
        :invalid="numberingInvalid"
        :described-by="numberingInvalid ? `${helpId} ${errorId}` : helpId"
      />
      <p :id="helpId" class="field-note">{{ $t("standards.editor.numberingDigitsHelp") }}</p>
      <p v-if="numberingInvalid" :id="errorId" class="field-error" role="alert" data-testid="numbering-digits-error">
        {{ $t("standards.diagnostic.STANDARD_NUMBERING_INVALID") }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.basic-section{display:grid;gap:var(--space-2);max-width:var(--card-max-width)}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.numbering-field{display:grid;gap:var(--space-1)}
.field-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.field-error{margin:0;font-size:var(--font-label);color:var(--color-danger)}
</style>
