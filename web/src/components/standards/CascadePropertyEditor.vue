<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UiInput from "../ui/UiInput.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {nextInstanceId} from "../ui/instanceId";
import {
  blankCascadeProperty,
  parseCascadeValues,
  propertyIndexById,
  referencesTo,
  selectableCascadeSources,
  type DraftCascadeProperty,
  type DraftDiagnostic,
  type DraftDocument,
  type DraftEnumProperty,
  type DraftProperty,
  type DraftPropertyScope,
  type PropertyReference,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  diagnostics?: DraftDiagnostic[];
  focusRequest?: {propertyId?: string; itemId?: string; openEditor?: boolean} | null;
}>();
const emit = defineEmits<{
  deleteBlocked: [{propertyId: string; references: PropertyReference[]}];
}>();
const {t} = useI18n();
const tableId = nextInstanceId("cascade-properties");
const nameHeaderId = `${tableId}-name`;
const scopeHeaderId = `${tableId}-scope`;
const summaryHeaderId = `${tableId}-source`;
const descriptionHeaderId = `${tableId}-description`;

const root = ref<HTMLElement | null>(null);
const card = ref<HTMLElement | null>(null);
const editingPropertyId = ref<string | null>(null);
const focusItemId = ref<string | undefined>();
const scope = ref<DraftPropertyScope>("sheetset");
const sourceId = ref("");
const name = ref("");
const description = ref("");
const valuesByItem = ref<Record<string, string>>({});
const blocked = ref<{propertyId: string; owners: string[]} | null>(null);

const cascadeProperties = computed(() =>
  props.document.properties.filter((property): property is Extract<DraftProperty, {kind: "cascade"}> => property.kind === "cascade"),
);
const editingProperty = computed<DraftCascadeProperty | null>(() => {
  const property = props.document.properties.find(item => item.property_id === editingPropertyId.value);
  return property?.kind === "cascade" ? property : null;
});
const candidates = computed<DraftEnumProperty[]>(() => {
  const owner = editingProperty.value;
  if (owner === null) return [];
  return selectableCascadeSources(props.document, {...owner, scope: scope.value});
});
const source = computed<DraftEnumProperty | undefined>(() => {
  const property = props.document.properties.find(item => item.property_id === sourceId.value);
  return property?.kind === "enum" && property.scope === scope.value ? property : undefined;
});
const rows = computed(() => (source.value?.enum_items ?? []).map(item => ({
  itemId: item.item_id,
  sourceValue: item.value,
  input: valuesByItem.value[item.item_id] ?? "",
  values: parseCascadeValues(valuesByItem.value[item.item_id] ?? ""),
})));
const canConfirm = computed(() =>
  source.value !== undefined
  && rows.value.length > 0
  && rows.value.every(row => {
    const normalized = row.values.map(value => value.toLocaleLowerCase());
    return row.values.length > 0
      && row.values.every(value => value.trim() !== "")
      && new Set(normalized).size === normalized.length;
  }),
);

function issuesOf(property: DraftProperty): DraftDiagnostic[] {
  return (props.diagnostics ?? []).filter(diagnostic => diagnostic.propertyId === property.property_id);
}

function issueText(property: DraftProperty): string {
  return issuesOf(property).map(diagnostic => t(`standards.diagnostic.${diagnostic.code}`)).join(t("standards.enumDialog.nameSeparator"));
}

function sourceSummary(property: DraftCascadeProperty): string {
  const parent = props.document.properties.find(item => item.property_id === property.source_property_id);
  return `${t("standards.cascade.sourcePrefix")}${parent?.name || t("standards.cascade.sourceMissing")}`;
}

function optionLabel(property: DraftEnumProperty): string {
  return `${property.name || property.property_id} · ${t(`standards.derived.scopeValue.${property.scope}`)}`;
}

function initializeValues(property: DraftCascadeProperty): void {
  const selectedSource = props.document.properties.find(item => item.property_id === property.source_property_id);
  if (selectedSource?.kind !== "enum" || selectedSource.scope !== property.scope) {
    sourceId.value = "";
    valuesByItem.value = {};
    return;
  }
  sourceId.value = selectedSource.property_id;
  valuesByItem.value = Object.fromEntries(property.cascade_options.map(row => [row.source_item_id, row.values.join(", ")]));
}

function openEditor(propertyId: string, itemId?: string): void {
  const property = props.document.properties.find(item => item.property_id === propertyId);
  if (property?.kind !== "cascade") return;
  blocked.value = null;
  editingPropertyId.value = propertyId;
  scope.value = property.scope;
  name.value = property.name;
  description.value = property.description;
  focusItemId.value = itemId;
  initializeValues(property);
}

function setScope(value: string): void {
  scope.value = value as DraftPropertyScope;
  sourceId.value = "";
  valuesByItem.value = {};
}

function setSource(value: string): void {
  sourceId.value = value;
  valuesByItem.value = {};
}

function setValues(itemId: string, value: string): void {
  valuesByItem.value = {...valuesByItem.value, [itemId]: value};
}

function confirm(): void {
  const property = editingProperty.value;
  if (property === null || !canConfirm.value || source.value === undefined) return;
  property.scope = scope.value;
  property.name = name.value;
  property.description = description.value;
  property.default_value = "";
  property.source_property_id = source.value.property_id;
  property.cascade_options = rows.value.map(row => ({source_item_id: row.itemId, values: row.values}));
  editingPropertyId.value = null;
}

function cancel(): void {
  editingPropertyId.value = null;
}

function addProperty(): void {
  const property = blankCascadeProperty(props.document);
  props.document.properties.push(property);
  openEditor(property.property_id);
}

function referenceOwner(reference: PropertyReference): string {
  if (reference.kind === "dwgNaming") return t("standards.ordinary.namingOwner");
  const owner = props.document.properties.find(item => item.property_id === reference.ownerId);
  return owner === undefined ? reference.ownerId : owner.name || reference.ownerId;
}

function removeProperty(property: DraftCascadeProperty): void {
  const references = referencesTo(props.document, property.property_id);
  if (references.length > 0) {
    blocked.value = {
      propertyId: property.property_id,
      owners: [...new Set(references.map(referenceOwner))],
    };
    emit("deleteBlocked", {propertyId: property.property_id, references});
    return;
  }
  const index = propertyIndexById(props.document, property.property_id);
  if (index >= 0) props.document.properties.splice(index, 1);
  blocked.value = null;
}

watch(
  () => props.focusRequest,
  async request => {
    if (request?.propertyId === undefined) return;
    const property = props.document.properties.find(item => item.property_id === request.propertyId);
    if (property?.kind !== "cascade") return;
    openEditor(request.propertyId, request.itemId);
    await nextTick();
    const selector = request.itemId === undefined
      ? "[data-testid=cascade-name]"
      : `[data-testid="cascade-values-${request.itemId}"]`;
    card.value?.querySelector<HTMLElement>(selector)?.focus();
  },
  {immediate: true},
);

watch(editingPropertyId, async propertyId => {
  if (propertyId === null) return;
  await nextTick();
  const selector = focusItemId.value === undefined
    ? "[data-testid=cascade-name]"
    : `[data-testid="cascade-values-${focusItemId.value}"]`;
  card.value?.querySelector<HTMLElement>(selector)?.focus();
});

const {onDialogKeydown} = useDialogFocus({
  open: () => editingProperty.value !== null,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    cancel();
  },
});
</script>

<template>
  <section ref="root" class="cascade-editor" role="region" :aria-label="$t('standards.cascade.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.cascade.title") }}</h3>
        <p class="section-hint">{{ $t("standards.cascade.hint") }}</p>
      </div>
      <UiButton variant="secondary" data-testid="add-cascade" @click="addProperty">
        {{ $t("standards.cascade.add") }}
      </UiButton>
    </header>
    <p v-if="blocked" class="delete-error" role="alert" data-testid="cascade-delete-blocked">
      {{ $t("standards.ordinary.deleteBlocked", {count: blocked.owners.length, owners: blocked.owners.join(t("standards.enumDialog.nameSeparator"))}) }}
    </p>
    <p v-if="cascadeProperties.length === 0" class="section-empty">{{ $t("standards.cascade.empty") }}</p>
    <div v-else class="cascade-table-scroll">
      <div class="cascade-table" role="table" data-ui-table-contract="cascade-properties" data-testid="cascade-table">
        <div class="cascade-row cascade-head" role="row">
          <span :id="nameHeaderId" role="columnheader">{{ $t("standards.cascade.name") }}</span>
          <span :id="scopeHeaderId" role="columnheader">{{ $t("standards.cascade.scope") }}</span>
          <span :id="summaryHeaderId" role="columnheader">{{ $t("standards.cascade.sourceSummary") }}</span>
          <span :id="descriptionHeaderId" role="columnheader">{{ $t("standards.cascade.description") }}</span>
          <span role="columnheader">{{ $t("standards.cascade.edit") }}</span>
          <span role="columnheader">{{ $t("standards.cascade.remove") }}</span>
        </div>
        <div v-for="property in cascadeProperties" :key="property.property_id" class="cascade-row" role="row">
          <div class="cascade-cell" role="cell">
            <UiInput v-model="property.name" :aria-labelledby="nameHeaderId" :data-testid="`cascade-name-${property.property_id}`" />
          </div>
          <div class="cascade-cell" role="cell">
            <span class="scope-badge" :aria-labelledby="scopeHeaderId">{{ $t(`standards.derived.scopeValue.${property.scope}`) }}</span>
          </div>
          <div class="cascade-cell source-summary" role="cell" :aria-labelledby="summaryHeaderId" :data-testid="`cascade-source-summary-${property.property_id}`">
            {{ sourceSummary(property) }}
          </div>
          <div class="cascade-cell cell-description" role="cell">
            <UiInput v-model="property.description" :aria-labelledby="descriptionHeaderId" :data-testid="`cascade-description-${property.property_id}`" />
          </div>
          <div class="cascade-cell" role="cell">
            <UiButton variant="secondary" size="compact" :data-testid="`edit-cascade-${property.property_id}`" @click="openEditor(property.property_id)">
              {{ $t("standards.cascade.edit") }}
            </UiButton>
          </div>
          <div class="cascade-cell" role="cell">
            <UiIconButton icon="close" :label="$t('standards.cascade.remove')" :data-testid="`cascade-remove-${property.property_id}`" @click="removeProperty(property)" />
          </div>
          <p v-if="issuesOf(property).length > 0" class="row-issue" role="cell" :data-testid="`cascade-issue-${property.property_id}`">
            {{ issueText(property) }}
          </p>
        </div>
      </div>
    </div>
    <div v-if="editingProperty" class="modal-mask" @keydown="onDialogKeydown">
      <div ref="card" class="cascade-dialog" role="dialog" aria-modal="true" tabindex="-1" :aria-label="$t('standards.cascade.dialogTitle', {name: editingProperty.name || editingProperty.property_id})" data-testid="cascade-dialog">
        <header class="dialog-head">
          <div class="head-text">
            <h2 class="dialog-title">{{ $t("standards.cascade.dialogTitle", {name: editingProperty.name || editingProperty.property_id}) }}</h2>
            <p class="dialog-hint">{{ $t("standards.cascade.dialogHint") }}</p>
          </div>
        </header>
        <div class="dialog-body">
          <UiInput v-model="name" :label="$t('standards.cascade.name')" data-testid="cascade-name" />
          <div class="source-field">
            <label class="field-label" for="cascade-scope-select">{{ $t("standards.cascade.scope") }}</label>
            <select id="cascade-scope-select" class="cell-select" :value="scope" data-testid="cascade-scope" @change="setScope(($event.target as HTMLSelectElement).value)">
              <option value="sheetset">{{ $t("standards.derived.scopeValue.sheetset") }}</option>
              <option value="sheet">{{ $t("standards.derived.scopeValue.sheet") }}</option>
            </select>
          </div>
          <div class="source-field">
            <label class="field-label" for="cascade-source-select">{{ $t("standards.cascade.source") }}</label>
            <select id="cascade-source-select" class="cell-select" :value="sourceId" data-testid="cascade-source" @change="setSource(($event.target as HTMLSelectElement).value)">
              <option value="">{{ $t("standards.cascade.sourcePlaceholder") }}</option>
              <option v-for="option in candidates" :key="option.property_id" :value="option.property_id">{{ optionLabel(option) }}</option>
            </select>
          </div>
          <div v-if="rows.length > 0" class="option-list" data-testid="cascade-options">
            <h3 class="option-list-title">{{ $t("standards.cascade.optionsTitle") }}</h3>
            <div v-for="row in rows" :key="row.itemId" class="option-row">
              <div class="source-value" :data-testid="`cascade-source-value-${row.itemId}`">{{ row.sourceValue }}</div>
              <UiInput
                :model-value="row.input"
                :label="$t('standards.cascade.valuesFor', {value: row.sourceValue})"
                :placeholder="$t('standards.cascade.valuesPlaceholder')"
                :data-testid="`cascade-values-${row.itemId}`"
                @update:model-value="setValues(row.itemId, $event)"
              />
            </div>
          </div>
          <p v-else class="mapping-empty" data-testid="cascade-empty">{{ $t("standards.cascade.emptyOptions") }}</p>
          <UiInput v-model="description" :label="$t('standards.cascade.description')" data-testid="cascade-dialog-description" />
        </div>
        <footer class="dialog-foot">
          <UiButton variant="secondary" data-testid="cancel-cascade" @click="cancel">{{ $t("standards.cascade.cancel") }}</UiButton>
          <UiButton variant="primary" :disabled="!canConfirm" data-testid="confirm-cascade" @click="confirm">{{ $t("standards.cascade.confirm") }}</UiButton>
        </footer>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cascade-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-empty,.mapping-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.delete-error{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);font-size:var(--font-label)}
.cascade-table-scroll{max-width:100%;overflow-x:auto}
.cascade-table{display:grid;gap:var(--space-2);width:max-content;min-width:100%}
.cascade-row{display:grid;grid-template-columns:minmax(120px,1.1fr) minmax(90px,.7fr) minmax(120px,1fr) minmax(120px,1.1fr) auto auto;gap:var(--space-2);align-items:start;min-height:var(--sheet-table-row-height);padding:var(--space-2)}
.cascade-head{align-items:start;min-height:var(--sheet-table-row-height);padding:var(--space-2)}
.cascade-head{font-size:var(--font-label);color:var(--color-text-secondary)}
.cascade-cell{display:flex;align-items:center;min-width:0;min-height:var(--sheet-table-row-height)}
.scope-badge,.source-value{max-width:100%;padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-label);overflow-wrap:anywhere}
.source-summary{font-size:var(--font-label);color:var(--color-text-secondary);overflow-wrap:anywhere}
.row-issue{grid-column:1/-1;margin:0;font-size:var(--font-label);color:var(--color-danger)}
.cascade-dialog{display:flex;flex-direction:column;width:min(760px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:hidden;outline:none;background:var(--color-bg-surface);color:var(--color-text-primary);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3)}
.dialog-head{display:flex;flex:0 0 auto;padding:var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.head-text{display:grid;gap:var(--space-1);min-width:0}
.dialog-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.dialog-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary);line-height:1.5}
.dialog-body{flex:1 1 auto;min-height:0;overflow:auto;display:grid;gap:var(--space-3);padding:var(--space-4)}
.source-field{display:grid;gap:var(--space-1)}
.field-label,.option-list-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.cell-select{box-sizing:border-box;width:100%;min-height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.option-list{display:grid;gap:var(--space-2)}
.option-row{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:var(--space-3);align-items:center;padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.dialog-foot{display:flex;flex:0 0 auto;justify-content:flex-end;gap:var(--space-2);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);background:var(--color-bg-muted)}
@media(max-width:560px){.cascade-dialog{width:calc(100vw - 32px);max-height:calc(100vh - 32px)}.option-row{grid-template-columns:minmax(0,1fr)}.dialog-foot{padding:var(--space-2);flex-wrap:wrap}}
</style>
