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
  /** 发布检查跳转请求：聚焦属性行；`openEditor` 为真时同时打开编辑模态框。 */
  focusRequest?: {propertyId?: string; openEditor?: boolean} | null;
}>();
const emit = defineEmits<{
  deleteBlocked: [{propertyId: string; references: PropertyReference[]}];
}>();
const {t} = useI18n();

const root = ref<HTMLElement | null>(null);
const dialogPropertyId = ref<string | null>(null);
const compositionDialogId = ref<string | null>(null);
const blocked = ref<{propertyId: string; owners: string[]} | null>(null);

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
);

function issuesOf(property: DraftProperty): DraftDiagnostic[] {
  return (props.diagnostics ?? []).filter(diagnostic => diagnostic.propertyId === property.property_id);
}

function issueText(property: DraftProperty): string {
  return issuesOf(property)
    .map(diagnostic =>
      t(`standards.diagnostic.${diagnostic.code}`, {
        segment: diagnostic.segmentIndex === undefined ? "" : diagnostic.segmentIndex + 1,
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
  props.document.properties.push(blankDerivedProperty(props.document, "composition"));
}

function setScope(property: DraftProperty, scope: string): void {
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
    <div v-else class="derived-list" data-testid="derived-table">
      <div class="derived-row derived-head" aria-hidden="true">
        <span>{{ $t("standards.derived.name") }}</span>
        <span>{{ $t("standards.derived.scope") }}</span>
        <span>{{ $t("standards.derived.sourceSummary") }}</span>
        <span>{{ $t("standards.derived.kind") }}</span>
        <span>{{ $t("standards.derived.description") }}</span>
        <span>{{ $t("standards.derived.edit") }}</span>
        <span>{{ $t("standards.derived.remove") }}</span>
      </div>
      <div v-for="property in derivedProperties" :key="property.property_id" class="derived-row">
        <UiInput
          v-model="property.name"
          :label="$t('standards.derived.name')"
          :data-testid="`derived-name-${property.property_id}`"
        />
        <select
          class="cell-select"
          :value="property.scope"
          :aria-label="$t('standards.derived.scope')"
          :data-testid="`derived-scope-${property.property_id}`"
          @change="setScope(property, ($event.target as HTMLSelectElement).value)"
        >
          <option value="sheetset">{{ $t("standards.derived.scopeValue.sheetset") }}</option>
          <option value="sheet">{{ $t("standards.derived.scopeValue.sheet") }}</option>
        </select>
        <span class="source-summary" :data-testid="`derived-source-${property.property_id}`">
          {{ sourceSummary(property) }}
        </span>
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
        <UiInput
          v-model="property.description"
          :label="$t('standards.derived.description')"
          :data-testid="`derived-description-${property.property_id}`"
        />
        <UiButton
          variant="secondary"
          size="compact"
          :data-testid="`edit-derived-${property.property_id}`"
          @click="openEditor(property.property_id)"
        >{{ $t("standards.derived.edit") }}</UiButton>
        <UiIconButton
          icon="close"
          :label="$t('standards.derived.remove')"
          :data-testid="`derived-remove-${property.property_id}`"
          @click="removeProperty(property)"
        />
        <p v-if="issuesOf(property).length > 0" class="row-issue" :data-testid="`derived-issue-${property.property_id}`">
          {{ issueText(property) }}
        </p>
      </div>
    </div>
    <MappingPropertyDialog
      :open="dialogProperty !== null"
      :property="dialogProperty"
      :document="document"
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
.derived-row{display:grid;grid-template-columns:minmax(0,1.1fr) 9% minmax(0,1.2fr) 12% minmax(0,1.2fr) auto auto;gap:var(--space-2);align-items:start}
.derived-head{font-size:var(--font-label);color:var(--color-text-secondary)}
.cell-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.source-summary{padding-top:var(--space-3);font-size:var(--font-label);color:var(--color-text-secondary);overflow-wrap:anywhere}
.row-issue{grid-column:1/-1;margin:0;font-size:var(--font-label);color:var(--color-danger)}
</style>
