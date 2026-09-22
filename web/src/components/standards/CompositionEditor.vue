<script setup lang="ts">
// 字段组合派生与 DWG 命名编辑器（PLAN-DM-035 Task 9 / SPEC-DM-016 §7.3）：
// 片段只有字段令牌、固定文本和受控序号令牌（可带补零格式码）。实时展示示例结果；
// 未知字段、非法格式码与循环依赖就地显示。示例为纯展示：真实求值仍由后端
// `domain/standard_rules.evaluate_fields` 完成，前端不复制最终规则求值。
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import {
  COMPOSITION_RULE_KINDS,
  fieldReference,
  nextRuleId,
  renderCompositionPreview,
  segmentKind,
  type DraftDocument,
  type DraftRule,
  type DraftSegment,
  type SegmentKind,
  type StructureDiagnostic,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  diagnostics: StructureDiagnostic[];
}>();
const {t} = useI18n();
const selectedId = ref<string | null>(null);

const compositionRules = computed(() => props.document.rules.filter(rule => COMPOSITION_RULE_KINDS.includes(rule.kind)));
const selected = computed<DraftRule | null>(() =>
  compositionRules.value.find(rule => rule.rule_id === selectedId.value) ?? compositionRules.value[0] ?? null,
);
/** 字段浏览器：过滤掉预留作用域，只列可引用字段。 */
const fieldOptions = computed(() => {
  const options = props.document.properties
    .filter(property => property.scope !== "subset")
    .map(property => fieldReference(property));
  options.push(props.document.numbering.sequence_field);
  options.push(...props.document.rules.map(rule => rule.target));
  return [...new Set(options.filter(Boolean))];
});

/** 示例值来源：属性默认值 → 枚举首值 → 占位示例；序数字段取编号起始值。 */
const sampleValues = computed(() => {
  const values: Record<string, string> = {};
  for (const property of props.document.properties) {
    const reference = fieldReference(property);
    if (reference === props.document.numbering.sequence_field) continue;
    values[reference] = property.default_value || property.enum_values[0] || t("standards.composition.samplePlaceholder");
  }
  values[props.document.numbering.sequence_field] = String(props.document.numbering.start);
  return values;
});

function previewOf(rule: DraftRule) {
  return renderCompositionPreview(rule.segments, sampleValues.value, {
    knownFields: fieldOptions.value,
    sequenceField: props.document.numbering.sequence_field,
  });
}

function diagnosticsFor(rule: DraftRule): StructureDiagnostic[] {
  return props.diagnostics.filter(item => item.ruleId === rule.rule_id);
}

function addRule(): void {
  const rule: DraftRule = {
    rule_id: nextRuleId(props.document, "composition"),
    kind: "naming",
    target: "derived.field",
    allowed: [],
    table: [],
    segments: [],
  };
  props.document.rules.push(rule);
  selectedId.value = rule.rule_id;
}

function removeRule(rule: DraftRule): void {
  const index = props.document.rules.indexOf(rule);
  if (index >= 0) props.document.rules.splice(index, 1);
  if (selectedId.value === rule.rule_id) selectedId.value = null;
}

function addSegment(rule: DraftRule, kind: SegmentKind): void {
  const segment: DraftSegment =
    kind === "literal" ? {literal: ""}
      : kind === "sequence" ? {field: props.document.numbering.sequence_field, format: String(props.document.numbering.digits)}
        : {field: fieldOptions.value[0] ?? "sheetset.field"};
  rule.segments.push(segment);
}

function removeSegment(rule: DraftRule, index: number): void {
  rule.segments.splice(index, 1);
}

function moveSegment(rule: DraftRule, index: number, offset: number): void {
  const target = index + offset;
  if (target < 0 || target >= rule.segments.length) return;
  const [segment] = rule.segments.splice(index, 1);
  rule.segments.splice(target, 0, segment);
}

function segmentLabel(segment: DraftSegment): string {
  const kind = segmentKind(segment, props.document.numbering.sequence_field);
  const key = kind === "literal" ? "segmentLiteral" : kind === "sequence" ? "segmentSequence" : "segmentField";
  return `standards.composition.${key}`;
}
</script>
<template>
  <section class="composition-editor" role="region" :aria-label="$t('standards.composition.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.composition.title") }}</h3>
        <p class="section-hint">{{ $t("standards.composition.hint") }}</p>
      </div>
      <UiButton variant="secondary" @click="addRule">{{ $t("standards.composition.add") }}</UiButton>
    </header>
    <p v-if="compositionRules.length === 0" class="section-empty">{{ $t("standards.composition.empty") }}</p>
    <template v-else>
      <p class="rule-count" role="status">{{ $t("standards.composition.ruleCount", {count: compositionRules.length}) }}</p>
      <ul class="rule-tabs">
        <li v-for="rule in compositionRules" :key="rule.rule_id">
          <button
            type="button"
            class="rule-tab"
            :class="{active: selected?.rule_id === rule.rule_id}"
            :data-testid="`composition-tab-${rule.rule_id}`"
            @click="selectedId = rule.rule_id"
          >{{ rule.target }}</button>
        </li>
      </ul>
      <div v-if="selected" class="rule-body">
        <label class="field-label" for="composition-target">{{ $t("standards.composition.target") }}</label>
        <input id="composition-target" v-model="selected.target" class="field-input" :placeholder="$t('standards.composition.targetHint')">
        <p class="browser-hint">
          <span class="field-label">{{ $t("standards.composition.fieldBrowser") }}</span>
          <span class="browser-values">{{ fieldOptions.join("、") }}</span>
        </p>
        <div class="segment-actions">
          <UiButton variant="secondary" @click="addSegment(selected, 'field')">{{ $t("standards.composition.addField") }}</UiButton>
          <UiButton variant="secondary" @click="addSegment(selected, 'literal')">{{ $t("standards.composition.addLiteral") }}</UiButton>
          <UiButton variant="secondary" @click="addSegment(selected, 'sequence')">{{ $t("standards.composition.addSequence") }}</UiButton>
        </div>
        <ol class="segment-list">
          <li v-for="(segment, index) in selected.segments" :key="index" class="segment-row">
            <span class="segment-kind">{{ $t(segmentLabel(segment)) }}</span>
            <template v-if="segment.literal !== undefined">
              <label class="cell-label">
                <span class="cell-label-text">{{ $t("standards.composition.segmentLiteral") }}</span>
                <input
                  v-model="segment.literal"
                  class="cell-input"
                  :placeholder="$t('standards.composition.literalPlaceholder')"
                  :data-testid="`composition-segment-${index}`"
                >
              </label>
            </template>
            <template v-else>
              <label class="cell-label">
                <span class="cell-label-text">{{ $t(segmentKind(segment, document.numbering.sequence_field) === 'sequence' ? 'standards.composition.segmentSequence' : 'standards.composition.segmentField') }}</span>
                <select v-model="segment.field" class="cell-input" :data-testid="`composition-segment-${index}`">
                  <option v-for="option in fieldOptions" :key="option" :value="option">{{ option }}</option>
                </select>
              </label>
              <label class="cell-label">
                <span class="cell-label-text">{{ $t("standards.composition.formatLabel") }}</span>
                <input v-model="segment.format" class="cell-input format-input" :placeholder="String(document.numbering.digits)">
              </label>
            </template>
            <span class="segment-tools">
              <UiIconButton
                icon="chevron-up"
                :label="$t('standards.composition.moveUp', {row: index + 1})"
                :disabled="index === 0"
                @click="moveSegment(selected, index, -1)"
              />
              <UiIconButton
                icon="chevron-down"
                :label="$t('standards.composition.moveDown', {row: index + 1})"
                :disabled="index === selected.segments.length - 1"
                @click="moveSegment(selected, index, 1)"
              />
              <UiIconButton
                icon="close"
                :label="$t('standards.composition.removeSegment', {row: index + 1})"
                @click="removeSegment(selected, index)"
              />
            </span>
          </li>
        </ol>
        <div class="preview">
          <h4 class="list-title">{{ $t("standards.composition.previewTitle") }}</h4>
          <p class="preview-text" role="status" data-testid="composition-preview">
            {{ previewOf(selected).text || "—" }}
          </p>
          <p class="preview-note">{{ $t("standards.composition.previewSampleNote") }}</p>
          <p class="preview-note">{{ $t("standards.composition.formatHint") }}</p>
        </div>
        <ul v-if="previewOf(selected).diagnostics.length > 0" class="diagnostics" role="alert">
          <li v-for="(item, index) in previewOf(selected).diagnostics" :key="index" class="diagnostic-item">
            {{ $t(`standards.diagnostic.${item.code}`, {field: item.field ?? ""}) }}
          </li>
        </ul>
        <ul v-if="diagnosticsFor(selected).length > 0" class="diagnostics" role="alert">
          <li v-for="(item, index) in diagnosticsFor(selected)" :key="index" class="diagnostic-item">
            {{ $t(`standards.diagnostic.${item.code}`, {field: item.field ?? ""}) }}
          </li>
        </ul>
        <UiButton variant="secondary" @click="removeRule(selected)">{{ $t("standards.composition.remove") }}</UiButton>
      </div>
    </template>
  </section>
</template>
<style scoped>
.composition-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.rule-count{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.rule-tabs{list-style:none;margin:0;padding:0;display:flex;gap:var(--space-2);flex-wrap:wrap}
.rule-tab{min-height:var(--min-tap-height);padding:var(--space-1) var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer}
.rule-tab.active{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.rule-body{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.field-input{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.browser-hint{display:flex;gap:var(--space-2);margin:0;font-size:var(--font-label);flex-wrap:wrap}
.browser-values{color:var(--color-text-muted);word-break:break-all}
.segment-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
.segment-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2)}
.segment-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:var(--space-2);align-items:end;padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.segment-kind{grid-column:1 / -1;font-size:var(--font-caption);color:var(--color-text-muted)}
.segment-tools{display:flex;gap:var(--space-1);align-items:end}
.cell-label{display:block;min-width:0}
.cell-label-text{display:block;font-size:var(--font-caption);color:var(--color-text-muted)}
.cell-input{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.format-input{max-width:8ch}
.preview{display:grid;gap:var(--space-1);padding:var(--space-3);background:var(--color-bg-muted);border-radius:var(--radius-md)}
.list-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.preview-text{margin:0;font-family:var(--font-mono);font-size:var(--font-size-16);color:var(--color-text-primary);word-break:break-all}
.preview-note{margin:0;font-size:var(--font-caption);color:var(--color-text-muted)}
.diagnostics{list-style:none;margin:0;padding-left:var(--space-4);color:var(--color-danger);font-size:var(--font-label)}
.diagnostic-item{list-style:disc}
@media (max-width: 959px){
  .segment-row{grid-template-columns:minmax(0,1fr)}
}
</style>
