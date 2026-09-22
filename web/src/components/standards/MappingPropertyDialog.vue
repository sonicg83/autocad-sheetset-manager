<script setup lang="ts">
// 映射属性编辑模态框（PLAN-DM-038 Task 7 / SPEC-DM-017 §5.2）。
//
// 契约：
// - 源属性选择器只列出作用域匹配、且未被其它映射占用的普通枚举属性；
//   当前已选源若被占用仍以禁用项保留，避免控件显示错误的值；
// - 映射行由源枚举列表固定生成：源值只读，不提供行增删与排序；
// - 目标值允许多个源值相同，但不得为空（空目标阻断发布，草稿仍可保存）；
// - 确认动作把当前有序 (enum_item_id, 显示值) 写入确认快照，清除「待确认」状态；
// - 界面不展示 `enum_item_id`：行以源枚举显示值标识，目标输入的 testid 携带稳定 ID 仅供定位；
// - 宽度与最大高度施加在外层对话框，正文独立滚动，底部操作栏不参与滚动。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {
  mappingConfirmationRequired,
  mappingRows,
  selectableMappingSources,
  type DraftDocument,
  type DraftEnumProperty,
  type DraftMappingProperty,
  type DraftMappingRow,
} from "../../features/standards/draftModel";

const props = defineProps<{
  open: boolean;
  property: DraftMappingProperty | null;
  document: DraftDocument;
  /** 发布检查跳转定位的映射行（源枚举项 ID）：打开后聚焦该行目标输入框。 */
  focusItemId?: string;
}>();
const emit = defineEmits<{
  save: [{sourcePropertyId: string; rows: DraftMappingRow[]; confirmed: Array<[string, string]>}];
  cancel: [];
}>();
const {t} = useI18n();

const card = ref<HTMLElement | null>(null);
const sourceId = ref("");
const targets = ref<Record<string, string>>({});

watch(
  () => props.open,
  open => {
    if (!open || props.property === null) return;
    sourceId.value = props.property.source_property_id;
    targets.value = Object.fromEntries(
      props.property.mapping.map(row => [row.item_id, row.value]),
    );
  },
  {immediate: true},
);

// 打开后把焦点交给目标输入框（发布检查跳转定位的行优先，否则第一行），
// 让「跳转到真实可编辑控件」在模态框里成立。
watch(
  () => props.open,
  async open => {
    if (!open) return;
    await nextTick();
    const target = props.focusItemId ?? rows.value[0]?.item_id;
    const selector = target === undefined
      ? "[data-testid=mapping-source]"
      : `[data-testid="mapping-target-${target}"]`;
    card.value?.querySelector<HTMLElement>(selector)?.focus();
  },
  {immediate: true},
);

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("cancel");
  },
});

const options = computed(() => {
  const selectable = selectableMappingSources(props.document, props.property as DraftMappingProperty);
  const current = props.document.properties.find(item => item.property_id === sourceId.value);
  // 当前已选源即使被占用也要保留在列表里（禁用项），否则选择器会显示错误的源。
  if (
    current !== undefined
    && current.kind === "enum"
    && !selectable.some(item => item.property_id === current.property_id)
  ) {
    return [current, ...selectable];
  }
  return selectable;
});

const source = computed<DraftEnumProperty | undefined>(() => {
  const current = props.document.properties.find(item => item.property_id === sourceId.value);
  return current !== undefined && current.kind === "enum" ? current : undefined;
});

const rows = computed<DraftMappingRow[]>(() =>
  source.value === undefined
    ? []
    : source.value.enum_items.map(item => ({item_id: item.item_id, value: targets.value[item.item_id] ?? ""})),
);

const pending = computed(() =>
  props.property !== null && mappingConfirmationRequired(props.property, source.value),
);

const occupied = computed(() => {
  const others = props.document.properties.filter(
    item => item.kind === "mapping" && item.property_id !== props.property?.property_id,
  );
  return new Set(others.map(item => (item.kind === "mapping" ? item.source_property_id : "")));
});

function optionLabel(property: DraftEnumProperty): string {
  const scope = t(`standards.derived.scopeValue.${property.scope}`);
  const suffix = occupied.value.has(property.property_id)
    ? t("standards.mapping.sourceOccupied")
    : "";
  return `${property.name || property.property_id} · ${scope}${suffix}`;
}

function setTarget(itemId: string, value: string): void {
  targets.value = {...targets.value, [itemId]: value};
}

function confirm(): void {
  if (props.property === null) return;
  emit("save", {
    sourcePropertyId: sourceId.value,
    rows: rows.value,
    confirmed: (source.value?.enum_items ?? []).map(item => [item.item_id, item.value]),
  });
}
</script>
<template>
  <div v-if="open && property" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card"
      class="mapping-dialog"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-label="$t('standards.mapping.title')"
      data-testid="mapping-dialog"
    >
      <header class="dialog-head">
        <div class="head-text">
          <h2 class="dialog-title">{{ $t("standards.mapping.dialogTitle", {name: property.name || property.property_id}) }}</h2>
          <p class="dialog-hint">{{ $t("standards.mapping.hint") }}</p>
        </div>
        <span
          class="status-badge"
          :class="{'status-badge--pending': pending}"
          data-testid="mapping-status"
        >{{ pending ? $t("standards.mapping.pending") : $t("standards.mapping.complete") }}</span>
      </header>
      <div class="dialog-body">
        <div class="source-field">
          <label class="field-label" for="mapping-source-select">{{ $t("standards.mapping.source") }}</label>
          <select
            id="mapping-source-select"
            class="cell-select"
            :value="sourceId"
            data-testid="mapping-source"
            @change="sourceId = ($event.target as HTMLSelectElement).value"
          >
            <option value="">{{ $t("standards.mapping.sourcePlaceholder") }}</option>
            <option
              v-for="option in options"
              :key="option.property_id"
              :value="option.property_id"
              :disabled="occupied.has(option.property_id)"
            >{{ optionLabel(option) }}</option>
          </select>
        </div>
        <div class="mapping-head" aria-hidden="true">
          <span>{{ $t("standards.mapping.sourceColumn") }}</span>
          <span>{{ $t("standards.mapping.targetColumn") }}</span>
        </div>
        <p v-if="rows.length === 0" class="mapping-empty" data-testid="mapping-empty">
          {{ $t("standards.mapping.empty") }}
        </p>
        <div v-for="row in rows" :key="row.item_id" class="mapping-row">
          <span class="source-value" :data-testid="`mapping-source-value-${row.item_id}`">
            {{ source?.enum_items.find(item => item.item_id === row.item_id)?.value ?? "" }}
          </span>
          <UiInput
            :model-value="row.value"
            :label="$t('standards.mapping.targetColumn')"
            :placeholder="$t('standards.mapping.targetPlaceholder')"
            :data-testid="`mapping-target-${row.item_id}`"
            @update:model-value="setTarget(row.item_id, $event)"
          />
        </div>
      </div>
      <footer class="dialog-foot">
        <UiButton variant="secondary" data-testid="cancel-mapping" @click="emit('cancel')">
          {{ $t("standards.mapping.cancel") }}
        </UiButton>
        <UiButton variant="primary" data-testid="confirm-mapping" @click="confirm">
          {{ $t("standards.mapping.confirm") }}
        </UiButton>
      </footer>
    </div>
  </div>
</template>
<style scoped>
.mapping-dialog{
  display:flex;flex-direction:column;
  width:min(720px,calc(100vw - 32px));max-height:calc(100vh - 42px);
  overflow:hidden;outline:none;
  background:var(--color-bg-surface);color:var(--color-text-primary);
  border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3);
}
.dialog-head{display:flex;flex:0 0 auto;align-items:flex-start;gap:var(--space-3);padding:var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.head-text{display:grid;gap:var(--space-1);min-width:0}
.dialog-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.dialog-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.status-badge{flex:0 0 auto;padding:0 var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);font-size:var(--font-label);color:var(--color-text-secondary)}
.status-badge--pending{border-color:var(--color-warning);color:var(--color-warning)}
.dialog-body{flex:1 1 auto;min-height:0;overflow:auto;display:grid;gap:var(--space-2);padding:var(--space-4)}
.source-field{display:grid;gap:var(--space-1)}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.cell-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.mapping-head,.mapping-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-2);align-items:end}
.mapping-head{font-size:var(--font-label);color:var(--color-text-secondary)}
.mapping-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.source-value{padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-label);overflow-wrap:anywhere}
.dialog-foot{display:flex;flex:0 0 auto;justify-content:flex-end;gap:var(--space-2);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);background:var(--color-bg-muted)}
</style>
