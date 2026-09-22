<script setup lang="ts">
// 字段映射编辑器（PLAN-DM-035 Task 9 / SPEC-DM-016 §7.2）：一条映射规则 = 一个源字段 +
// 一个目标字段 + 一张两列表；源值唯一且非空，目标值必须满足目标字段自身约束，
// 未匹配值策略首版固定为“阻止继续并指出缺少映射”。
// 支持逐行编辑、制表符/CSV 批量粘贴；诊断行可点击跳转并聚焦到该行首个可编辑单元格。
import {computed, nextTick, ref, watch} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import {
  buildMappingRows,
  fieldReference,
  mappingRowsToTable,
  nextRuleId,
  tableToMappingRows,
  validateMapping,
  type DraftDocument,
  type DraftRule,
  type EditorSectionId,
  type MappingDiagnostic,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  /** 来自壳层错误摘要的跳转请求：切到本分区后聚焦指定映射行。 */
  focusRequest?: {section: EditorSectionId; ruleId?: string; row?: number} | null;
}>();
const pasteRule = ref<DraftRule | null>(null);
const pasteText = ref("");

const mappingRules = computed(() => props.document.rules.filter(rule => rule.kind === "mapping"));
const fieldOptions = computed(() => {
  const options = props.document.properties.map(property => fieldReference(property));
  options.push(props.document.numbering.sequence_field);
  options.push(...props.document.rules.map(rule => rule.target));
  return [...new Set(options.filter(Boolean))];
});
const pasteRows = computed(() => buildMappingRows(pasteText.value));

/** 逐行 DOM 引用：跳转需要把焦点交给真实控件，而不是只滚动。 */
const sourceInputs = new Map<string, HTMLInputElement>();

function bindRowInput(ruleIndex: number, rowIndex: number) {
  const key = `${ruleIndex}:${rowIndex}`;
  return (element: unknown): void => {
    if (element instanceof HTMLInputElement) sourceInputs.set(key, element);
    else sourceInputs.delete(key);
  };
}

function focusRow(ruleIndex: number, rowIndex: number): void {
  sourceInputs.get(`${ruleIndex}:${rowIndex}`)?.focus();
}

function propertyByReference(reference: string | undefined) {
  return props.document.properties.find(property => fieldReference(property) === reference);
}

/** 源域的受控枚举（用于“未覆盖源值”检查）；非枚举字段不做覆盖检查。 */
function sourceDomainOf(rule: DraftRule): string[] {
  return propertyByReference(rule.source)?.enum_values ?? [];
}

/** 目标字段自身约束：非空枚举时目标值必须落在集合内。 */
function targetRuleOf(rule: DraftRule): {allowed: string[]} {
  return {allowed: propertyByReference(rule.target)?.enum_values ?? []};
}

function rowDiagnostics(rule: DraftRule): MappingDiagnostic[] {
  return validateMapping(tableToMappingRows(rule.table), sourceDomainOf(rule), targetRuleOf(rule));
}

function addRule(): void {
  props.document.rules.push({
    rule_id: nextRuleId(props.document, "mapping"),
    kind: "mapping",
    target: "sheetset.field",
    source: fieldOptions.value[0],
    allowed: [],
    table: [],
    segments: [],
  });
}

function removeRule(rule: DraftRule): void {
  const index = props.document.rules.indexOf(rule);
  if (index >= 0) props.document.rules.splice(index, 1);
}

function addRow(rule: DraftRule): void {
  rule.table.push(["", ""]);
}

function removeRow(rule: DraftRule, rowIndex: number): void {
  rule.table.splice(rowIndex, 1);
}

function openPaste(rule: DraftRule): void {
  pasteRule.value = rule;
  pasteText.value = "";
}

function applyPaste(): void {
  const rule = pasteRule.value;
  if (rule === null || pasteRows.value.length === 0) return;
  // 批量粘贴是整表设置：直接替换该规则的映射表，避免重复粘贴叠加出重复源值
  rule.table = mappingRowsToTable(pasteRows.value);
  pasteRule.value = null;
  pasteText.value = "";
}

function jumpToDiagnostic(ruleIndex: number, item: MappingDiagnostic): void {
  if (item.row === null) return;
  focusRow(ruleIndex, item.row - 1);
}

watch(
  () => props.focusRequest,
  async (request) => {
    if (!request || request.section !== "mapping" || request.row === undefined) return;
    const index = mappingRules.value.findIndex(rule => rule.rule_id === request.ruleId);
    if (index < 0) return;
    await nextTick();
    focusRow(index, request.row - 1);
  },
  {immediate: true},
);
</script>
<template>
  <section class="mapping-editor" role="region" :aria-label="$t('standards.mapping.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.mapping.title") }}</h3>
        <p class="section-hint">{{ $t("standards.mapping.hint") }}</p>
      </div>
      <UiButton variant="secondary" @click="addRule">{{ $t("standards.mapping.add") }}</UiButton>
    </header>
    <p v-if="mappingRules.length === 0" class="section-empty">{{ $t("standards.mapping.empty") }}</p>
    <template v-else>
      <p class="rule-count" role="status" data-testid="mapping-rule-count">
        {{ $t("standards.mapping.ruleCount", {count: mappingRules.length}) }}
      </p>
      <article
        v-for="(rule, ruleIndex) in mappingRules"
        :key="rule.rule_id"
        class="mapping-rule"
        :data-testid="`mapping-rule-${ruleIndex}`"
      >
        <div class="rule-fields">
          <label class="field-label" :for="`mapping-source-${ruleIndex}`">{{ $t("standards.mapping.source") }}</label>
          <select :id="`mapping-source-${ruleIndex}`" v-model="rule.source" class="field-select">
            <option v-for="option in fieldOptions" :key="option" :value="option">{{ option }}</option>
          </select>
          <UiInput v-model="rule.target" :label="$t('standards.mapping.target')" :placeholder="$t('standards.mapping.targetHint')" />
        </div>
        <p class="policy">
          <span class="policy-label">{{ $t("standards.mapping.unmatchedPolicy") }}</span>
          <span>{{ $t("standards.mapping.unmatchedPolicyFixed") }}</span>
        </p>
        <div class="table-header">
          <h4 class="list-title">{{ $t("standards.mapping.tableTitle") }}</h4>
          <div class="table-actions">
            <UiButton variant="secondary" @click="openPaste(rule)">{{ $t("standards.mapping.bulkPaste") }}</UiButton>
            <UiButton variant="secondary" @click="addRow(rule)">{{ $t("standards.mapping.addRow") }}</UiButton>
          </div>
        </div>
        <table class="mapping-table">
          <thead>
            <tr>
              <th scope="col">{{ $t("standards.mapping.sourceColumn") }}</th>
              <th scope="col">{{ $t("standards.mapping.targetColumn") }}</th>
              <th scope="col">{{ $t("standards.properties.remove") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rule.table" :key="rowIndex" :data-testid="`mapping-row-${ruleIndex}-${rowIndex}`">
              <td>
                <label class="cell-label">
                  <span class="cell-label-text">{{ $t("standards.mapping.sourceColumn") }}</span>
                  <input
                    :ref="bindRowInput(ruleIndex, rowIndex)"
                    v-model="row[0]"
                    class="cell-input"
                    :data-testid="`mapping-source-${ruleIndex}-${rowIndex}`"
                  >
                </label>
              </td>
              <td>
                <label class="cell-label">
                  <span class="cell-label-text">{{ $t("standards.mapping.targetColumn") }}</span>
                  <input v-model="row[1]" class="cell-input">
                </label>
              </td>
              <td>
                <UiIconButton
                  icon="close"
                  :label="$t('standards.mapping.removeRow', {row: rowIndex + 1})"
                  @click="removeRow(rule, rowIndex)"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <ul v-if="rowDiagnostics(rule).length > 0" class="diagnostics" role="alert">
          <li v-for="(item, index) in rowDiagnostics(rule)" :key="index">
            <button
              type="button"
              class="diagnostic-button"
              :data-testid="`mapping-diagnostic-${index}`"
              @click="jumpToDiagnostic(ruleIndex, item)"
            >
              <span>{{ $t(`standards.diagnostic.${item.code}`, {source: item.source, value: item.value ?? "", row: item.row ?? ""}) }}</span>
              <span class="diagnostic-location">
                {{ item.row === null ? $t("standards.diagnostic.noRow") : $t("standards.diagnostic.row", {row: item.row}) }}
              </span>
            </button>
          </li>
        </ul>
        <UiButton variant="secondary" @click="removeRule(rule)">{{ $t("standards.mapping.remove") }}</UiButton>
      </article>
    </template>
    <div v-if="pasteRule !== null" class="paste-backdrop" @click.self="pasteRule = null">
      <section class="paste-dialog" role="dialog" aria-modal="true" :aria-label="$t('standards.mapping.bulkTitle')">
        <h4 class="list-title">{{ $t("standards.mapping.bulkTitle") }}</h4>
        <p class="section-hint">{{ $t("standards.mapping.bulkHint") }}</p>
        <label class="field-label" for="mapping-paste-input">{{ $t("standards.mapping.bulkContent") }}</label>
        <textarea id="mapping-paste-input" v-model="pasteText" class="paste-input" rows="6" />
        <div class="paste-actions">
          <UiButton variant="secondary" @click="pasteRule = null">{{ $t("standards.create.cancel") }}</UiButton>
          <UiButton
            variant="secondary"
            :disabled="pasteRows.length === 0"
            @click="applyPaste"
          >{{ $t("standards.mapping.bulkApply", {count: pasteRows.length}) }}</UiButton>
        </div>
      </section>
    </div>
  </section>
</template>
<style scoped>
.mapping-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.rule-count{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.mapping-rule{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.rule-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-2);align-items:end}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.field-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.policy{display:flex;gap:var(--space-2);margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.policy-label{color:var(--color-text-muted)}
.table-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);flex-wrap:wrap}
.list-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.table-actions{display:flex;gap:var(--space-2)}
.mapping-table{width:100%;border-collapse:collapse;table-layout:fixed}
.mapping-table th,.mapping-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left}
.mapping-table th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500}
.cell-label{display:block}
.cell-label-text{display:block;font-size:var(--font-caption);color:var(--color-text-muted)}
.cell-input{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.diagnostics{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.diagnostic-button{width:100%;display:flex;justify-content:space-between;gap:var(--space-2);text-align:left;min-height:var(--min-tap-height);padding:var(--space-2);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);cursor:pointer;font-size:var(--font-label)}
.diagnostic-location{color:var(--color-text-secondary)}
.paste-backdrop{position:fixed;inset:0;background:rgb(0 0 0 / 0.4);display:grid;place-items:center;z-index:60}
.paste-dialog{width:min(560px,calc(100vw - 32px));display:grid;gap:var(--space-2);padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.paste-input{width:100%;box-sizing:border-box;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:var(--space-2);font-family:var(--font-mono);font-size:var(--input-font-size);background:var(--color-bg-surface);color:var(--color-text-primary)}
.paste-actions{display:flex;gap:var(--space-2);justify-content:flex-end}
</style>
