<script setup lang="ts">
// 普通取值与联动规则编辑器（PLAN-DM-035 Task 9 / SPEC-DM-016 §7.1）：
// “规则列表 + 侧边编辑器”，只构造必填/枚举/固定值三类规则，并实时生成自然语言摘要。
// 不提供 JSON、脚本、eval 或自由公式文本框；大量一一对应关系交由字段映射分区。
// 首版所有规则都生效（标准 Schema 没有启用开关），列表的“状态”列显示结构是否可用，
// 不提供会导致“界面停用但后端仍生效”的伪开关。
import {computed, ref} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import {
  fieldReference,
  nextRuleId,
  ORDINARY_RULE_KINDS,
  ruleSummary,
  type DraftDocument,
  type DraftRule,
  type DraftRuleKind,
  type StructureDiagnostic,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  diagnostics: StructureDiagnostic[];
}>();
const selectedId = ref<string | null>(null);

const ordinaryRules = computed(() => props.document.rules.filter(rule => ORDINARY_RULE_KINDS.includes(rule.kind)));
const selected = computed<DraftRule | null>(() =>
  ordinaryRules.value.find(rule => rule.rule_id === selectedId.value) ?? ordinaryRules.value[0] ?? null,
);
/** 可作为规则来源/目标的字段：属性定义 + 受控序数字段 + 已存在的派生目标。 */
const fieldOptions = computed(() => {
  const options = props.document.properties.map(property => fieldReference(property));
  options.push(props.document.numbering.sequence_field);
  options.push(...props.document.rules.map(rule => rule.target));
  return [...new Set(options.filter(Boolean))];
});

const kindLabelKeys: Record<string, string> = {
  required: "standards.rules.kindRequired",
  enum: "standards.rules.kindEnum",
  fixed: "standards.rules.kindFixed",
};

function diagnosticsFor(rule: DraftRule): StructureDiagnostic[] {
  return props.diagnostics.filter(item => item.ruleId === rule.rule_id);
}

function addRule(): void {
  const rule: DraftRule = {
    rule_id: nextRuleId(props.document, "rule"),
    kind: "required",
    target: fieldOptions.value[0] ?? "sheetset.field",
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

function setKind(rule: DraftRule, value: unknown): void {
  rule.kind = String(value) as DraftRuleKind;
}

function setAllowedText(rule: DraftRule, value: unknown): void {
  rule.allowed = String(value).split(",").map(item => item.trim()).filter(Boolean);
}
</script>
<template>
  <section class="rules-editor" role="region" :aria-label="$t('standards.rules.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.rules.title") }}</h3>
        <p class="section-hint">{{ $t("standards.rules.hint") }}</p>
      </div>
      <UiButton variant="secondary" @click="addRule">{{ $t("standards.rules.add") }}</UiButton>
    </header>
    <p v-if="ordinaryRules.length === 0" class="section-empty">{{ $t("standards.rules.empty") }}</p>
    <div v-else class="rules-split">
      <div class="rules-list">
        <h4 class="list-title">{{ $t("standards.rules.list") }}</h4>
        <ul>
          <li v-for="rule in ordinaryRules" :key="rule.rule_id">
            <button
              type="button"
              class="rule-item"
              :class="{active: selected?.rule_id === rule.rule_id}"
              :data-testid="`rule-item-${rule.rule_id}`"
              @click="selectedId = rule.rule_id"
            >
              <span class="rule-kind">{{ $t(kindLabelKeys[rule.kind] ?? 'standards.rules.kind') }}</span>
              <span class="rule-summary">{{ $t(ruleSummary(rule).key, ruleSummary(rule).params) }}</span>
              <span class="rule-status" :class="{warning: diagnosticsFor(rule).length > 0}">
                {{ $t(diagnosticsFor(rule).length > 0 ? "standards.rules.statusDiagnostic" : "standards.rules.statusActive") }}
              </span>
            </button>
          </li>
        </ul>
      </div>
      <div v-if="selected" class="rule-editor">
        <h4 class="list-title">{{ $t("standards.rules.editorTitle") }}</h4>
        <label class="field-label" :for="`rule-kind-${selected.rule_id}`">{{ $t("standards.rules.kind") }}</label>
        <select
          :id="`rule-kind-${selected.rule_id}`"
          class="field-select"
          :value="selected.kind"
          @change="setKind(selected, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="kind in ORDINARY_RULE_KINDS" :key="kind" :value="kind">{{ $t(kindLabelKeys[kind]) }}</option>
        </select>
        <UiInput v-model="selected.target" :label="$t('standards.rules.target')" :placeholder="$t('standards.rules.targetHint')" />
        <UiInput
          v-if="selected.kind === 'fixed'"
          :model-value="selected.value ?? ''"
          :label="$t('standards.rules.value')"
          @update:model-value="selected.value = String($event)"
        />
        <UiInput
          v-if="selected.kind === 'enum'"
          :model-value="selected.allowed.join(', ')"
          :label="$t('standards.rules.allowed')"
          @update:model-value="setAllowedText(selected, $event)"
        />
        <p class="rule-preview" role="status">{{ $t(ruleSummary(selected).key, ruleSummary(selected).params) }}</p>
        <ul v-if="diagnosticsFor(selected).length > 0" class="rule-diagnostics" role="alert">
          <li v-for="(item, index) in diagnosticsFor(selected)" :key="index">
            {{ $t(`standards.diagnostic.${item.code}`, {field: item.field ?? ""}) }}
          </li>
        </ul>
        <UiButton variant="secondary" @click="removeRule(selected)">{{ $t("standards.rules.remove") }}</UiButton>
      </div>
    </div>
  </section>
</template>
<style scoped>
.rules-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.rules-split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-4);align-items:start}
.list-title{margin:0 0 var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.rules-list ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.rule-item{width:100%;display:grid;gap:var(--space-1);text-align:left;padding:var(--space-2) var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);cursor:pointer}
.rule-item.active{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.rule-kind{font-size:var(--font-label);color:var(--color-text-secondary)}
.rule-summary{color:var(--color-text-primary)}
.rule-status{font-size:var(--font-label);color:var(--color-text-secondary)}
.rule-status.warning{color:var(--color-danger)}
.rule-editor{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.field-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.rule-preview{margin:0;padding:var(--space-2);background:var(--color-bg-muted);border-radius:var(--radius-md);font-size:var(--font-label);color:var(--color-text-primary)}
.rule-diagnostics{margin:0;padding-left:var(--space-4);color:var(--color-danger);font-size:var(--font-label)}
@media (max-width: 959px){
  .rules-split{grid-template-columns:minmax(0,1fr)}
}
</style>
