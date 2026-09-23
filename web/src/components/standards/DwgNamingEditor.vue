<script setup lang="ts">
// DWG 命名分区（PLAN-DM-038 Task 8 / SPEC-DM-017 §6）。
//
// 契约：
// - 每个标准必须且只能有一条全局模板；允许字段只有 `subset.scope/name/sequence` 与全部
//   sheetset 属性（sheet 属性令牌在选择器里根本不出现）；
// - 与组合属性共用 `TokenExpressionEditor`；`.dwg` 由系统固定追加，显示在编辑框之外；
// - 示例预览明确标注为「示例」，并列出取样值；模板缺少 `subset.scope` 与 `subset.sequence`
//   时给出重名风险 warning（前端只提示，发布仍以后端码为准）；
// - 缓冲由 `StandardEditor` 持有：本组件直接就地修改 `props.document.dwg_naming`。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import TokenExpressionEditor from "./TokenExpressionEditor.vue";
import {
  DWG_EXTENSION,
  defaultDwgNamingSegments,
  dwgNamingSkeleton,
  renderDwgNamingPreview,
  type DraftDocument,
  type DraftSegment,
} from "../../features/standards/draftModel";
import {dwgNamingTokenFields, type TokenFieldTexts} from "../../features/standards/tokenFields";

const props = defineProps<{
  document: DraftDocument;
  /** 发布诊断（只读）：命名相关的 error/warning 在分区内就地提示。 */
  diagnostics?: Array<{code: string; severity: string; segmentIndex?: number}>;
  /** 发布检查跳转请求：聚焦对应令牌（无片段定位时聚焦固定文字输入框）。 */
  focusRequest?: {segmentIndex?: number} | null;
}>();
const {t} = useI18n();
const root = ref<HTMLElement | null>(null);

watch(
  () => props.focusRequest,
  async request => {
    if (request === null || request === undefined) return;
    await nextTick();
    const selector = request.segmentIndex === undefined
      ? "[data-testid=token-literal]"
      : `[data-testid="token-${request.segmentIndex}"]`;
    root.value?.querySelector<HTMLElement>(selector)?.focus();
  },
  {immediate: true},
);

const texts = computed<TokenFieldTexts>(() => ({
  systemLabels: {
    "subset.scope": t("standards.token.system.subsetScope"),
    "subset.name": t("standards.token.system.subsetName"),
    "subset.sequence": t("standards.token.system.subsetSequence"),
  },
  placeholder: t("standards.token.samplePlaceholder"),
  sequenceFormat: "02",
}));

const fields = computed(() => dwgNamingTokenFields(props.document, texts.value));

const samples = computed(() => ({
  subsetName: t("standards.token.sample.subsetName"),
  sheetNumber: t("standards.token.sample.sheetNumber"),
  sheetTitle: t("standards.token.sample.sheetTitle"),
  placeholder: t("standards.token.samplePlaceholder"),
}));

const preview = computed(() => renderDwgNamingPreview(props.document, samples.value));

const sampleRows = computed(() => {
  const width = Math.max(props.document.numbering.digits, 1);
  const scope = `${String(1).padStart(width, "0")}-${String(3).padStart(width, "0")}`;
  const rows = [
    {label: t("standards.token.system.subsetScope"), value: scope},
    {label: t("standards.token.system.subsetName"), value: samples.value.subsetName},
    {label: t("standards.token.system.subsetSequence"), value: "1"},
  ];
  for (const field of fields.value.filter(item => !item.system)) {
    rows.push({label: field.label, value: field.sample});
  }
  return rows;
});

const issues = computed(() => props.diagnostics ?? []);
const namingError = computed(() => issues.value.some(item => item.severity === "error"));
const uniquenessWarning = computed(() => issues.value.some(item => item.code === "DWG_NAMING_UNIQUENESS_UNPROVEN"));
// 文件名模板风险只提示不阻断（取值层面的非法文件名由后端在发布/渲染阶段逐项目校验）
const namingRiskWarning = computed(() =>
  issues.value.some(item => item.code.startsWith("DWG_NAME_") && item.severity === "warning"),
);
const skeleton = computed(() => dwgNamingSkeleton(props.document));

function setSegments(segments: DraftSegment[]): void {
  props.document.dwg_naming.segments = segments;
}

function resetTemplate(): void {
  props.document.dwg_naming.segments = defaultDwgNamingSegments();
}
</script>
<template>
  <section ref="root" class="naming-editor" role="region" :aria-label="$t('standards.naming.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.naming.title") }}</h3>
        <p class="section-hint">{{ $t("standards.naming.hint") }}</p>
      </div>
      <UiButton variant="secondary" data-testid="reset-naming" @click="resetTemplate">
        {{ $t("standards.naming.reset") }}
      </UiButton>
    </header>
    <p v-if="uniquenessWarning" class="warning-note" role="note" data-testid="naming-uniqueness-warning">
      {{ $t("standards.naming.uniquenessWarning") }}
    </p>
    <p v-if="namingRiskWarning" class="warning-note" role="note" data-testid="naming-risk-warning">
      {{ $t("standards.naming.invalidHint") }}
    </p>
    <p v-if="namingError" class="error-note" role="alert" data-testid="naming-error">
      {{ $t("standards.naming.invalidHint") }}
    </p>
    <TokenExpressionEditor
      :segments="document.dwg_naming.segments"
      :fields="fields"
      :label="$t('standards.naming.template')"
      :hint="$t('standards.naming.templateHint')"
      :preview-label="$t('standards.naming.preview')"
      :preview="`${preview.text}${DWG_EXTENSION}`"
      :sample-rows="sampleRows"
      :preview-invalid="preview.diagnostics.length > 0"
      @update:segments="setSegments"
    />
    <p class="extension-note" role="note" data-testid="naming-extension-note">
      {{ $t("standards.naming.extensionNote", {extension: DWG_EXTENSION}) }}
    </p>
    <p class="skeleton-note" data-testid="naming-skeleton">{{ skeleton }}</p>
  </section>
</template>
<style scoped>
.naming-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.warning-note{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-warning);border-radius:var(--radius-md);background:var(--color-warning-bg);color:var(--color-warning);font-size:var(--font-label)}
.error-note{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);font-size:var(--font-label)}
.extension-note,.skeleton-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.skeleton-note{font-family:var(--font-mono);color:var(--color-text-muted)}
</style>
