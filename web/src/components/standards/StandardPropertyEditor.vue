<script setup lang="ts">
// 属性定义编辑器（PLAN-DM-035 Task 9 / SPEC-DM-016 §6.3）：可编辑表格 + CSV 批量导入。
// 表格显示字段键、作用域、类型（文本/枚举/派生）、必填、默认值、枚举值与说明。
// 子集作用域只显示“预留，首版不可配置”的说明行，不提供伪编辑入口。
// 缓冲由 StandardEditor 持有：本组件直接就地修改 props.document.properties。
import {computed, ref} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import {
  FIELD_SCOPES,
  fieldReference,
  isReservedScope,
  parsePropertyCsv,
  type DraftDocument,
  type DraftProperty,
} from "../../features/standards/draftModel";

const props = defineProps<{document: DraftDocument}>();
const csvOpen = ref(false);
const csvText = ref("");

/** 首版可配置作用域（预留作用域不进入选择器）。 */
const editableScopes = computed(() => FIELD_SCOPES.filter(scope => !isReservedScope(scope)));

function isDerived(property: DraftProperty): boolean {
  return props.document.rules.some(rule => rule.target === fieldReference(property));
}

function typeLabel(property: DraftProperty): string {
  if (isDerived(property)) return "standards.properties.typeDerived";
  return property.enum_values.length > 0 ? "standards.properties.typeEnum" : "standards.properties.typeText";
}

function enumText(property: DraftProperty): string {
  return property.enum_values.join(", ");
}

function setEnumText(property: DraftProperty, value: unknown): void {
  property.enum_values = String(value).split(",").map(item => item.trim()).filter(Boolean);
}

function addProperty(): void {
  props.document.properties.push({
    name: `property_${props.document.properties.length + 1}`,
    scope: "sheetset",
    required: false,
    default_value: "",
    enum_values: [],
    description: "",
  });
}

function removeProperty(index: number): void {
  props.document.properties.splice(index, 1);
}

const csvRows = computed(() => parsePropertyCsv(csvText.value));

function applyCsv(): void {
  if (csvRows.value.length === 0) return;
  props.document.properties.push(...csvRows.value.map(row => ({...row})));
  csvText.value = "";
  csvOpen.value = false;
}
</script>
<template>
  <section class="property-editor" role="region" :aria-label="$t('standards.properties.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.properties.title") }}</h3>
        <p class="section-hint">{{ $t("standards.properties.hint") }}</p>
      </div>
      <div class="section-actions">
        <UiButton variant="secondary" @click="csvOpen = true">{{ $t("standards.properties.csv.title") }}</UiButton>
        <UiButton variant="secondary" @click="addProperty">{{ $t("standards.properties.add") }}</UiButton>
      </div>
    </header>
    <p v-if="document.properties.length === 0" class="section-empty">{{ $t("standards.properties.empty") }}</p>
    <table v-else class="property-table">
      <thead>
        <tr>
          <th scope="col">{{ $t("standards.properties.key") }}</th>
          <th scope="col">{{ $t("standards.properties.scope") }}</th>
          <th scope="col">{{ $t("standards.properties.type") }}</th>
          <th scope="col">{{ $t("standards.properties.required") }}</th>
          <th scope="col">{{ $t("standards.properties.defaultValue") }}</th>
          <th scope="col">{{ $t("standards.properties.enumValues") }}</th>
          <th scope="col">{{ $t("standards.properties.description") }}</th>
          <th scope="col"><span class="sr-only-label">{{ $t("standards.properties.remove") }}</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(property, index) in document.properties" :key="index">
          <td colspan="7" v-if="isReservedScope(property.scope)" class="reserved-cell">
            {{ fieldReference(property) }} · {{ $t("standards.properties.reservedNote") }}
          </td>
          <template v-else>
            <td><UiInput v-model="property.name" :label="$t('standards.properties.key')" /></td>
            <td>
              <select v-model="property.scope" class="cell-select" :aria-label="$t('standards.properties.scope')">
                <option v-for="scope in editableScopes" :key="scope" :value="scope">{{ scope }}</option>
              </select>
            </td>
            <td><span class="type-label">{{ $t(typeLabel(property)) }}</span></td>
            <td>
              <label class="required-cell">
                <input v-model="property.required" type="checkbox">
                <span>{{ $t("standards.properties.required") }}</span>
              </label>
            </td>
            <td><UiInput v-model="property.default_value" :label="$t('standards.properties.defaultValue')" /></td>
            <td>
              <UiInput
                :model-value="enumText(property)"
                :label="$t('standards.properties.enumValues')"
                @update:model-value="setEnumText(property, $event)"
              />
            </td>
            <td><UiInput v-model="property.description" :label="$t('standards.properties.description')" /></td>
            <td>
              <UiIconButton
                icon="close"
                :label="$t('standards.properties.remove')"
                @click="removeProperty(index)"
              />
            </td>
          </template>
        </tr>
      </tbody>
    </table>
    <div v-if="csvOpen" class="csv-backdrop" @click.self="csvOpen = false">
      <section class="csv-dialog" role="dialog" aria-modal="true" :aria-label="$t('standards.properties.csv.title')">
        <h4 class="csv-title">{{ $t("standards.properties.csv.title") }}</h4>
        <p class="csv-hint">{{ $t("standards.properties.csv.hint") }}</p>
        <label class="csv-label" for="property-csv-input">{{ $t("standards.properties.csv.content") }}</label>
        <textarea id="property-csv-input" v-model="csvText" class="csv-input" rows="6" />
        <div class="csv-actions">
          <UiButton variant="secondary" @click="csvOpen = false">{{ $t("standards.create.cancel") }}</UiButton>
          <UiButton
            variant="secondary"
            :disabled="csvRows.length === 0"
            @click="applyCsv"
          >{{ csvRows.length === 0 ? $t("standards.properties.csv.empty") : $t("standards.properties.csv.apply", {count: csvRows.length}) }}</UiButton>
        </div>
      </section>
    </div>
  </section>
</template>
<style scoped>
.property-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.property-table{width:100%;border-collapse:collapse;table-layout:fixed}
.property-table th,.property-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;vertical-align:top}
.property-table th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500}
.cell-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.type-label{display:inline-block;padding-top:var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.required-cell{display:inline-flex;align-items:center;gap:var(--space-1);padding-top:var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.reserved-cell{font-size:var(--font-label);color:var(--color-text-secondary);background:var(--color-bg-muted)}
.sr-only-label{font-size:var(--font-label)}
.csv-backdrop{position:fixed;inset:0;background:rgb(0 0 0 / 0.4);display:grid;place-items:center;z-index:60}
.csv-dialog{width:min(560px,calc(100vw - 32px));display:grid;gap:var(--space-2);padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.csv-title{margin:0;font-size:var(--font-label);color:var(--color-text-primary)}
.csv-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.csv-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.csv-input{width:100%;box-sizing:border-box;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:var(--space-2);font-family:var(--font-mono);font-size:var(--input-font-size);background:var(--color-bg-surface);color:var(--color-text-primary)}
.csv-actions{display:flex;gap:var(--space-2);justify-content:flex-end}
</style>
