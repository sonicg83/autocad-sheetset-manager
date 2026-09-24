<script setup lang="ts">
// 批量修改对话框（SPEC-DM-018 §4.2；PLAN-DM-036 Task 8）。
// 先选多个图纸组，再选字段与新值，一次应用到选中组：只作用选中组，当前值不一致时显示
// 「值不相同」；清空必须是明确操作——未填写的输入框不会被当作清空。字段列表只含张数、
// 基础模板、布局模板、图幅与标准的可输入 sheet 属性，不含图名或任何派生字段。
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import FormField from "../ui/FormField.vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {
  BASE_TEMPLATE_KIND,
  LAYOUT_TEMPLATE_KIND,
  creationAssetOptions,
  creationBatchValues,
  creationPaperLayouts,
} from "../../features/creation/inputModel";
import {
  CREATION_BATCH_BASE,
  CREATION_BATCH_COUNT,
  CREATION_BATCH_LAYOUT,
  CREATION_BATCH_PAPER,
  type CreationBatchFieldKind,
} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{store: CreationStore; open: boolean}>();
const emit = defineEmits<{close: []}>();
const {t} = useI18n();

const card = ref<HTMLElement | null>(null);
const fieldId = ref<string>(CREATION_BATCH_COUNT);
const value = ref("");

const fields = computed<Array<{id: string; kind: CreationBatchFieldKind; label: string}>>(() => [
  {id: CREATION_BATCH_COUNT, kind: "count", label: t("creation.groups.columnCount")},
  {id: CREATION_BATCH_BASE, kind: "base-template", label: t("creation.groups.columnBase")},
  {id: CREATION_BATCH_LAYOUT, kind: "layout-template", label: t("creation.groups.columnLayout")},
  {id: CREATION_BATCH_PAPER, kind: "paper-layout", label: t("creation.groups.columnPaper")},
  ...(props.store.standard?.sheet_properties ?? []).map(property => ({
    id: property.property_id,
    kind: property.kind as CreationBatchFieldKind,
    label: property.name,
  })),
]);
const kind = computed(
  () => fields.value.find(field => field.id === fieldId.value)?.kind ?? "text",
);
const values = computed(() => creationBatchValues(props.store.selectedGroups(), fieldId.value));
const mixed = computed(() => new Set(values.value).size > 1);
const currentText = computed(() => {
  if (values.value.length === 0) return t("creation.groups.batchNone");
  if (mixed.value) return t("creation.groups.batchMixed");
  const first = values.value[0] ?? "";
  return first === ""
    ? t("creation.groups.batchCurrentEmpty")
    : t("creation.groups.batchCurrent", {value: first});
});
const baseOptions = computed(() => creationAssetOptions(props.store.standard, BASE_TEMPLATE_KIND));
const layoutOptions = computed(() => creationAssetOptions(props.store.standard, LAYOUT_TEMPLATE_KIND));
/** 图幅候选取第一个选中组的布局模板：混合选择由后端预览判定组合关系。 */
const paperOptions = computed(() =>
  creationPaperLayouts(props.store.standard, props.store.selectedGroups()[0]?.layout_asset_id ?? ""),
);
const enumOptions = computed(
  () =>
    props.store.standard?.sheet_properties.find(item => item.property_id === fieldId.value)?.options ??
    [],
);
const canApply = computed(() => props.store.selectedGroupIds.length > 0 && value.value !== "");
const canClear = computed(
  () => props.store.selectedGroupIds.length > 0 && fieldId.value !== CREATION_BATCH_COUNT,
);

// 每次打开复位新值：上一次的输入不得跨次泄漏为“清空”以外的隐式操作
watch(
  () => props.open,
  open => {
    if (open) value.value = "";
  },
);

function changeField(next: string): void {
  fieldId.value = next;
  value.value = "";
}

function changeValue(next: string): void {
  value.value = next;
}

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("close");
  },
});

function apply(): void {
  if (!canApply.value) return;
  props.store.batchUpdate([...props.store.selectedGroupIds], fieldId.value, {
    kind: "set",
    value: value.value,
  });
  emit("close");
}

function clear(): void {
  if (!canClear.value) return;
  props.store.batchUpdate([...props.store.selectedGroupIds], fieldId.value, {kind: "clear"});
  emit("close");
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card" class="modal-card batch-card" role="dialog" aria-modal="true"
      :aria-label="t('creation.groups.batchTitle')" tabindex="-1"
    >
      <h2>{{ t("creation.groups.batchTitle") }}</h2>
      <p class="batch-lead">{{ t("creation.groups.batchLead") }}</p>
      <p class="batch-state" data-testid="creation-batch-state">
        {{ t("creation.groups.batchSelected", {count: store.selectedGroupIds.length}) }} · {{ currentText }}
      </p>
      <div class="batch-grid">
        <FormField :label="t('creation.groups.batchField')">
          <template #default="{id, describedBy}">
            <UiSelect
              :id="id" :described-by="describedBy" :model-value="fieldId"
              @update:model-value="changeField"
            >
              <option v-for="field in fields" :key="field.id" :value="field.id">{{ field.label }}</option>
            </UiSelect>
          </template>
        </FormField>
        <FormField :label="t('creation.groups.batchValue')">
          <template #default="{id, describedBy}">
            <UiSelect
              v-if="kind === 'base-template' || kind === 'layout-template' || kind === 'paper-layout' || kind === 'enum'"
              :id="id" :described-by="describedBy" :model-value="value"
              @update:model-value="changeValue"
            >
              <option value="" disabled>{{ t("creation.groups.batchNoValue") }}</option>
              <template v-if="kind === 'base-template'">
                <option v-for="option in baseOptions" :key="option.asset_id" :value="option.asset_id">{{ option.label }}</option>
              </template>
              <template v-else-if="kind === 'layout-template'">
                <option v-for="option in layoutOptions" :key="option.asset_id" :value="option.asset_id">{{ option.label }}</option>
              </template>
              <template v-else-if="kind === 'paper-layout'">
                <option v-for="layout in paperOptions" :key="layout" :value="layout">{{ layout }}</option>
              </template>
              <template v-else>
                <option v-for="option in enumOptions" :key="option.item_id" :value="option.value">{{ option.value }}</option>
              </template>
            </UiSelect>
            <UiInput
              v-else-if="kind === 'count'"
              :id="id" :described-by="describedBy" type="number" min="1" step="1"
              :model-value="value" @update:model-value="changeValue"
            />
            <UiInput
              v-else
              :id="id" :described-by="describedBy"
              :model-value="value" @update:model-value="changeValue"
            />
          </template>
        </FormField>
      </div>
      <p class="batch-boundary">{{ t("creation.groups.batchBoundary") }}</p>
      <div class="modal-actions">
        <UiButton variant="secondary" :disabled="!canClear" @click="clear">
          {{ t("creation.groups.batchClear") }}
        </UiButton>
        <span class="spacer"></span>
        <UiButton variant="secondary" @click="emit('close')">{{ t("creation.groups.batchClose") }}</UiButton>
        <UiButton variant="primary" :disabled="!canApply" @click="apply">
          {{ t("creation.groups.batchApply") }}
        </UiButton>
      </div>
    </div>
  </div>
</template>
<style scoped>
.batch-card{display:grid;gap:var(--space-3)}
.batch-lead{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.batch-state{margin:0;color:var(--color-text-primary);font-size:var(--font-label)}
.batch-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-3)}
.batch-boundary{margin:0;color:var(--color-text-muted);font-size:var(--font-caption);line-height:1.6}
.spacer{flex:1}
@media (max-width: 720px){
  .batch-grid{grid-template-columns:minmax(0,1fr)}
}
</style>
