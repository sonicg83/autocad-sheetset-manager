<script setup lang="ts">
// 派生属性表（PLAN-DM-038 Task 7 / SPEC-DM-017 §5.1）。
//
// 契约：
// - 七列固定「属性名/作用域/源属性摘要/类型/说明/编辑/删除」；
// - 类型只允许映射与组合；点击「编辑」按类型打开映射模态框（组合由共享令牌编辑器负责）；
// - 源属性摘要显示当前源属性名（映射）或令牌字段名（组合），并在枚举变化后显示「待确认」；
// - 删除同样受引用保护：被组合或 DWG 命名引用时不修改数组并向上抛出引用列表；
// - 缓冲由 `StandardEditor` 持有：本组件直接就地修改 `props.document`。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UiInput from "../ui/UiInput.vue";
import {nextInstanceId} from "../ui/instanceId";
import MappingPropertyDialog from "./MappingPropertyDialog.vue";
import CompositionPropertyDialog from "./CompositionPropertyDialog.vue";
import {
  DERIVED_PROPERTY_KINDS,
  blankDerivedProperty,
  mappingConfirmationRequired,
  propertyIndexById,
  referencesTo,
  type DerivedPropertyKind,
  type DraftCompositionProperty,
  type DraftDiagnostic,
  type DraftDocument,
  type DraftMappingProperty,
  type DraftSegment,
  type DraftMappingRow,
  type DraftProperty,
  type DraftPropertyScope,
  type PropertyReference,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  diagnostics?: DraftDiagnostic[];
  /** 发布检查跳转请求：聚焦属性行；`openEditor` 为真时同时打开编辑模态框并定位映射行。 */
  focusRequest?: {propertyId?: string; itemId?: string; openEditor?: boolean} | null;
}>();
const emit = defineEmits<{
  deleteBlocked: [{propertyId: string; references: PropertyReference[]}];
}>();
const {t} = useI18n();
const derivedTableId = nextInstanceId("derived-properties");
const derivedNameHeaderId = `${derivedTableId}-name`;
const derivedDescriptionHeaderId = `${derivedTableId}-description`;

const root = ref<HTMLElement | null>(null);
const dialogPropertyId = ref<string | null>(null);
const compositionDialogId = ref<string | null>(null);
const blocked = ref<{propertyId: string; owners: string[]} | null>(null);
/** 本次会话新建的属性：只有它们允许在创建时选择作用域（SPEC-DM-017 §3.2）。 */
const createdIds = ref<string[]>([]);

const derivedProperties = computed(() =>
  props.document.properties.filter(
    property => property.kind === "mapping" || property.kind === "composition",
  ),
);
const dialogProperty = computed<DraftMappingProperty | null>(() => {
  const property = props.document.properties.find(item => item.property_id === dialogPropertyId.value);
  return property !== undefined && property.kind === "mapping" ? property : null;
});
const compositionDialogProperty = computed<DraftCompositionProperty | null>(() => {
  const property = props.document.properties.find(item => item.property_id === compositionDialogId.value);
  return property !== undefined && property.kind === "composition" ? property : null;
});

watch(
  () => props.focusRequest,
  async request => {
    if (request?.propertyId === undefined) return;
    if (request.openEditor === true) openEditor(request.propertyId);
    await nextTick();
    root.value
      ?.querySelector<HTMLElement>(`[data-testid="edit-derived-${request.propertyId}"]`)
      ?.focus();
  },
  {immediate: true},
);

function issuesOf(property: DraftProperty): DraftDiagnostic[] {
  return (props.diagnostics ?? []).filter(diagnostic => diagnostic.propertyId === property.property_id);
}

function issueText(property: DraftProperty): string {
  return issuesOf(property)
    .map(diagnostic =>
      t(`standards.diagnostic.${diagnostic.code}`, {
        segment: diagnostic.segmentIndex === undefined ? "" : diagnostic.segmentIndex + 1,
        // `{field}` 占位符使用出错值；多余参数对无占位符的文案无副作用
        field: diagnostic.detail ?? "",
      }),
    )
    .join(t("standards.enumDialog.nameSeparator"));
}

function sourceOf(property: DraftProperty) {
  return props.document.properties.find(item => item.property_id === sourceIdOf(property));
}

function sourceIdOf(property: DraftProperty): string {
  return property.kind === "mapping" ? property.source_property_id : "";
}

/** 源属性摘要：映射显示源属性名，组合显示令牌字段数；枚举变化后附「待确认」。 */
function sourceSummary(property: DraftProperty): string {
  if (property.kind === "mapping") {
    const source = sourceOf(property);
    const name = source === undefined ? t("standards.derived.sourceMissing") : source.name || source.property_id;
    const pending = mappingConfirmationRequired(property, source?.kind === "enum" ? source : undefined)
      ? t("standards.derived.pendingSuffix")
      : "";
    return `${t("standards.derived.sourceEnum")}${name}${pending}`;
  }
  if (property.kind === "composition") {
    const fields = property.segments
      .filter(segment => segment.property_id !== undefined)
      .map(segment => {
        const owner = props.document.properties.find(item => item.property_id === segment.property_id);
        return owner?.name ?? segment.property_id ?? "";
      });
    if (fields.length === 0) return t("standards.derived.sourceUnset");
    return fields.join(t("standards.enumDialog.nameSeparator"));
  }
  return "";
}

function addProperty(): void {
  const property = blankDerivedProperty(props.document, "composition");
  props.document.properties.push(property);
  createdIds.value = [...createdIds.value, property.property_id];
}

function isCreated(property: DraftProperty): boolean {
  return createdIds.value.includes(property.property_id);
}

/** 作用域只在创建时可选；既有属性改作用域必须删除后重建。 */
function setScope(property: DraftProperty, scope: string): void {
  if (!isCreated(property)) return;
  property.scope = scope as DraftPropertyScope;
}

/** 映射 ↔ 组合在派生属性内部允许切换；切换时清空载荷，避免留下无主映射行或令牌。 */
function setKind(property: DraftProperty, kind: string): void {
  if (kind !== "mapping" && kind !== "composition") return;
  if (kind === property.kind) return;
  const index = propertyIndexById(props.document, property.property_id);
  if (index < 0) return;
  const base = {
    property_id: property.property_id,
    name: property.name,
    previous_names: [...property.previous_names],
    scope: property.scope,
    required: property.required,
    default_value: property.default_value,
    description: property.description,
  };
  const next: DraftProperty = kind === "mapping"
    ? {...base, kind, source_property_id: "", mapping: [], confirmed_source_items: []}
    : {...base, kind, segments: []};
  props.document.properties.splice(index, 1, next);
}

function openEditor(propertyId: string): void {
  const property = props.document.properties.find(item => item.property_id === propertyId);
  if (property === undefined) return;
  blocked.value = null;
  if (property.kind === "mapping") {
    dialogPropertyId.value = propertyId;
    return;
  }
  if (property.kind === "composition") compositionDialogId.value = propertyId;
}

function saveMapping(payload: {
  sourcePropertyId: string;
  rows: DraftMappingRow[];
  confirmed: Array<[string, string]>;
}): void {
  const property = dialogProperty.value;
  if (property !== null) {
    property.source_property_id = payload.sourcePropertyId;
    property.mapping = payload.rows;
    property.confirmed_source_items = payload.confirmed;
  }
  dialogPropertyId.value = null;
}

function saveComposition(segments: DraftSegment[]): void {
  const property = compositionDialogProperty.value;
  if (property !== null) property.segments = segments;
  compositionDialogId.value = null;
}

function referenceOwner(reference: PropertyReference): string {
  if (reference.kind === "dwgNaming") return t("standards.ordinary.namingOwner");
  const owner = props.document.properties.find(item => item.property_id === reference.ownerId);
  return owner === undefined ? reference.ownerId : owner.name || reference.ownerId;
}

function removeProperty(property: DraftProperty): void {
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
</script>
<template>
  <section ref="root" class="derived-editor" role="region" :aria-label="$t('standards.derived.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.derived.title") }}</h3>
        <p class="section-hint">{{ $t("standards.derived.hint") }}</p>
      </div>
      <UiButton variant="secondary" data-testid="add-derived" @click="addProperty">
        {{ $t("standards.derived.add") }}
      </UiButton>
    </header>
    <p class="flow-note" role="note">{{ $t("standards.derived.flow") }}</p>
    <p v-if="blocked" class="delete-error" role="alert" data-testid="derived-delete-blocked">
      {{ $t("standards.ordinary.deleteBlocked", {count: blocked.owners.length, owners: blocked.owners.join(t("standards.enumDialog.nameSeparator"))}) }}
    </p>
    <p v-if="derivedProperties.length === 0" class="section-empty">{{ $t("standards.derived.empty") }}</p>
    <div v-else class="derived-list" role="table" data-ui-table-contract="derived-properties" data-testid="derived-table">
      <div class="derived-row derived-head" role="row">
        <span :id="derivedNameHeaderId" role="columnheader">{{ $t("standards.derived.name") }}</span>
        <span role="columnheader">{{ $t("standards.derived.scope") }}</span>
        <span role="columnheader">{{ $t("standards.derived.sourceSummary") }}</span>
        <span role="columnheader">{{ $t("standards.derived.kind") }}</span>
        <span :id="derivedDescriptionHeaderId" role="columnheader">{{ $t("standards.derived.description") }}</span>
        <span role="columnheader">{{ $t("standards.derived.edit") }}</span>
        <span role="columnheader">{{ $t("standards.derived.remove") }}</span>
      </div>
      <div v-for="property in derivedProperties" :key="property.property_id" class="derived-row" role="row">
        <div class="derived-cell" role="cell">
          <UiInput
            v-model="property.name"
            :aria-labelledby="derivedNameHeaderId"
            :data-testid="`derived-name-${property.property_id}`"
          />
        </div>
        <div class="derived-cell" role="cell">
          <select
            v-if="isCreated(property)"
            class="cell-select"
            :value="property.scope"
            :aria-label="$t('standards.derived.scope')"
            :data-testid="`derived-scope-${property.property_id}`"
            @change="setScope(property, ($event.target as HTMLSelectElement).value)"
          >
            <option value="sheetset">{{ $t("standards.derived.scopeValue.sheetset") }}</option>
            <option value="sheet">{{ $t("standards.derived.scopeValue.sheet") }}</option>
          </select>
          <span
            v-else
            class="scope-locked"
            :title="$t('standards.derived.scopeLocked')"
            :data-testid="`derived-scope-badge-${property.property_id}`"
          >{{ property.scope }}</span>
        </div>
        <div class="derived-cell cell-source-summary" role="cell">
          <span class="source-summary" :data-testid="`derived-source-${property.property_id}`">
            {{ sourceSummary(property) }}
          </span>
        </div>
        <div class="derived-cell" role="cell">
          <select
            class="cell-select"
            :value="property.kind"
            :aria-label="$t('standards.derived.kind')"
            :data-testid="`derived-kind-${property.property_id}`"
            @change="setKind(property, ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="kind in DERIVED_PROPERTY_KINDS" :key="kind" :value="kind">
              {{ kind === "mapping" ? $t("standards.derived.kindMapping") : $t("standards.derived.kindComposition") }}
            </option>
          </select>
        </div>
        <!-- 说明列网格项必须可由父组件整体隐藏；UiInput 的 class/data-testid 只落在内部 input。 -->
        <div class="derived-cell cell-description" role="cell">
          <UiInput
            v-model="property.description"
            :aria-labelledby="derivedDescriptionHeaderId"
            :data-testid="`derived-description-${property.property_id}`"
          />
        </div>
        <div class="derived-cell" role="cell">
          <UiButton
            variant="secondary"
            size="compact"
            :data-testid="`edit-derived-${property.property_id}`"
            @click="openEditor(property.property_id)"
          >{{ $t("standards.derived.edit") }}</UiButton>
        </div>
        <div class="derived-cell" role="cell">
          <UiIconButton
            icon="close"
            :label="$t('standards.derived.remove')"
            :data-testid="`derived-remove-${property.property_id}`"
            @click="removeProperty(property)"
          />
        </div>
        <p v-if="issuesOf(property).length > 0" class="row-issue" role="cell" :data-testid="`derived-issue-${property.property_id}`">
          {{ issueText(property) }}
        </p>
      </div>
    </div>
    <MappingPropertyDialog
      :open="dialogProperty !== null"
      :property="dialogProperty"
      :document="document"
      :focus-item-id="focusRequest?.itemId"
      @save="saveMapping"
      @cancel="dialogPropertyId = null"
    />
    <CompositionPropertyDialog
      :open="compositionDialogProperty !== null"
      :property="compositionDialogProperty"
      :document="document"
      @save="saveComposition"
      @cancel="compositionDialogId = null"
    />
  </section>
</template>
<style scoped>
.derived-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.flow-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.delete-error{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);font-size:var(--font-label)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.derived-list{display:grid;gap:var(--space-2)}
.derived-row{display:grid;grid-template-columns:minmax(0,1.1fr) 9% minmax(0,1.2fr) 12% minmax(0,1.2fr) auto auto;gap:var(--space-2)}
.derived-row,.derived-head{min-height:var(--sheet-table-row-height);padding:var(--space-2);align-items:start}
.derived-cell{display:flex;align-items:center;min-width:0;min-height:var(--sheet-table-row-height)}
.derived-head{font-size:var(--font-label);color:var(--color-text-secondary)}
/* 分级响应式（PLAN-DM-039 Task 3，对照 SPEC-DM-017 编辑器 Demo）：
   1050px 以下隐藏纯说明列，780px 以下再隐藏可由编辑模态框读取的源摘要列；
   属性名、作用域、类型、编辑与删除动作任何档位都不得隐藏。
   注意：隐藏说明列必须作用于整个网格项（`.cell-description` 包裹元素），
   不能只隐藏 UiInput 内部元素——`UiInput` 为 `inheritAttrs:false`，`data-testid` 经
   `v-bind="$attrs"` 只落到内层 `input`，外层仍占一列，会把最后的删除动作挤到第二行（F1）。 */
@media (max-width: 1050px){
  .derived-row{grid-template-columns:minmax(0,1.2fr) 9% minmax(0,1.1fr) 12% auto auto}
  .derived-row > .cell-description,.derived-row.derived-head :nth-child(5){display:none}
}
@media (max-width: 780px){
  .derived-row{grid-template-columns:minmax(0,1.2fr) 9% 12% auto auto}
  .derived-row > .cell-source-summary,.derived-row.derived-head :nth-child(3){display:none}
}
.scope-locked{display:inline-block;padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-label)}
.cell-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.source-summary{padding-top:var(--space-3);font-size:var(--font-label);color:var(--color-text-secondary);overflow-wrap:anywhere}
.row-issue{grid-column:1/-1;margin:0;font-size:var(--font-label);color:var(--color-danger)}
</style>
