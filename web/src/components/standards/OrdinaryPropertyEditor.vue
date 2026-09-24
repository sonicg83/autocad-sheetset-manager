<script setup lang="ts">
// 普通属性表（PLAN-DM-038 Task 6 / SPEC-DM-017 §4）。
//
// 契约：
// - 表格固定八列「属性名/作用域/类型/必填/默认值/枚举值/说明/删除」；
// - 类型只允许文本与枚举，文本行的枚举摘要灰显且不可聚焦；
// - 「必填」复选框本体固定 16×16，点击区域由标签扩展到 32×32，不继承输入框的统一高度；
// - 枚举值经扩展模态维护（`EnumValuesDialog`），保存才写回草稿；
// - 删除被映射、组合或 DWG 命名引用的属性必须阻断：不修改数组，向上抛出引用列表；
// - 缓冲由 `StandardEditor` 持有：本组件直接就地修改 `props.document`。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UiInput from "../ui/UiInput.vue";
import EnumValuesDialog from "./EnumValuesDialog.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {
  PROPERTY_SCOPES,
  blankOrdinaryProperty,
  parsePropertyCsv,
  propertyIndexById,
  referencesTo,
  type DraftDiagnostic,
  type DraftDocument,
  type DraftEnumItem,
  type DraftEnumProperty,
  type DraftProperty,
  type DraftPropertyScope,
  type OrdinaryPropertyKind,
  type PropertyReference,
} from "../../features/standards/draftModel";

const props = defineProps<{
  document: DraftDocument;
  /** 发布诊断（只读）：行级错误在表格内就地标记，焦点仍由 `focusRequest` 驱动。 */
  diagnostics?: DraftDiagnostic[];
  /** 发布检查跳转请求：聚焦到指定属性的属性名输入框。 */
  focusRequest?: {propertyId?: string} | null;
}>();
const emit = defineEmits<{deleteBlocked: [{propertyId: string; references: PropertyReference[]}]}>();
const {t} = useI18n();

const root = ref<HTMLElement | null>(null);
const dialogPropertyId = ref<string | null>(null);
const blocked = ref<{propertyId: string; owners: string[]} | null>(null);
const csvOpen = ref(false);
const csvText = ref("");
const csvCard = ref<HTMLElement | null>(null);

// CSV 弹窗焦点契约（PLAN-DM-040 Task 9，F13）：与新建弹窗、UnsavedInputDialog 同源。
// 初始焦点落在弹窗内首个停靠点（CSV 内容文本域），Tab 圈闭，Escape 关闭并归还焦点。
const {onDialogKeydown: onCsvKeydown} = useDialogFocus({
  open: csvOpen,
  container: csvCard,
  onEscape: event => {
    event.stopPropagation();
    csvOpen.value = false;
  },
});
/** 本次会话新建的属性：只有它们允许在创建时选择作用域（SPEC-DM-017 §3.2 禁止改既有作用域）。 */
const createdIds = ref<string[]>([]);

/** 普通属性表只列普通属性；派生属性在派生分区维护。 */
const ordinaryProperties = computed(() =>
  props.document.properties.filter(property => property.kind === "text" || property.kind === "enum"),
);
const dialogProperty = computed<DraftEnumProperty | null>(() => {
  const property = props.document.properties.find(item => item.property_id === dialogPropertyId.value);
  return property !== undefined && property.kind === "enum" ? property : null;
});
const impactedNames = computed(() =>
  props.document.properties
    .filter(property => property.kind === "mapping" && property.source_property_id === dialogPropertyId.value)
    .map(property => property.name || property.property_id),
);
const csvRows = computed(() => parsePropertyCsv(csvText.value, props.document));

watch(
  () => props.focusRequest,
  async request => {
    if (request?.propertyId === undefined) return;
    await nextTick();
    root.value
      ?.querySelector<HTMLInputElement>(`[data-testid="ordinary-name-${request.propertyId}"]`)
      ?.focus();
  },
  {immediate: true},
);

function issuesOf(property: DraftProperty): DraftDiagnostic[] {
  return (props.diagnostics ?? []).filter(diagnostic => diagnostic.propertyId === property.property_id);
}

function hasError(property: DraftProperty): boolean {
  return issuesOf(property).some(diagnostic => diagnostic.severity === "error");
}

function issueText(property: DraftProperty): string {
  return issuesOf(property)
    .map(diagnostic => t(`standards.diagnostic.${diagnostic.code}`, diagnosticParams(diagnostic)))
    .join(t("standards.enumDialog.nameSeparator"));
}

function diagnosticParams(diagnostic: DraftDiagnostic): Record<string, string | number> {
  const property = props.document.properties.find(item => item.property_id === diagnostic.propertyId);
  return {
    property: property?.name ?? "",
    segment: diagnostic.segmentIndex === undefined ? "" : diagnostic.segmentIndex + 1,
    // `{field}`/`{source}` 占位符共用一个出错值；多余参数对无占位符的文案无副作用
    field: diagnostic.detail ?? "",
    source: diagnostic.detail ?? "",
  };
}

function addProperty(): void {
  const property = blankOrdinaryProperty(props.document, "text");
  props.document.properties.push(property);
  createdIds.value = [...createdIds.value, property.property_id];
}

function isCreated(property: DraftProperty): boolean {
  return createdIds.value.includes(property.property_id);
}

/** 作用域只在创建时可选；既有属性改作用域必须删除后重建（保留引用删除保护）。 */
function setScope(property: DraftProperty, scope: string): void {
  if (!isCreated(property)) return;
  property.scope = scope as DraftPropertyScope;
}

function setRequired(property: DraftProperty, event: Event): void {
  property.required = (event.target as HTMLInputElement).checked;
}

/** 文本 ↔ 枚举在普通属性内部允许切换；切到文本时丢弃枚举项，切到枚举时给一条待填空项。 */
function setKind(property: DraftProperty, kind: string): void {
  if (kind !== "text" && kind !== "enum") return;
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
  const next: DraftProperty = kind === "enum"
    ? {...base, kind, enum_items: [{item_id: "enum-new", value: ""}]}
    : {...base, kind};
  props.document.properties.splice(index, 1, next);
}

function enumSummary(property: DraftProperty): string {
  if (property.kind !== "enum") return "";
  return property.enum_items.map(item => item.value).filter(Boolean).join(" / ");
}

function openEnumDialog(property: DraftProperty): void {
  if (property.kind !== "enum") return;
  blocked.value = null;
  dialogPropertyId.value = property.property_id;
}

function saveEnum(items: DraftEnumItem[]): void {
  const property = dialogProperty.value;
  if (property !== null) property.enum_items = items;
  dialogPropertyId.value = null;
}

/** 引用方显示名：派生属性用属性名，DWG 命名模板用其专用名称。 */
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

function applyCsv(): void {
  const created = parsePropertyCsv(csvText.value, props.document);
  if (created.length === 0) return;
  props.document.properties.push(...created);
  createdIds.value = [...createdIds.value, ...created.map(property => property.property_id)];
  csvText.value = "";
  csvOpen.value = false;
}
</script>
<template>
  <section ref="root" class="ordinary-editor" role="region" :aria-label="$t('standards.ordinary.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.ordinary.title") }}</h3>
        <p class="section-hint">{{ $t("standards.ordinary.hint") }}</p>
      </div>
      <div class="section-actions">
        <UiButton variant="secondary" data-testid="ordinary-csv" @click="csvOpen = true">
          {{ $t("standards.ordinary.csv.title") }}
        </UiButton>
        <UiButton variant="secondary" data-testid="add-ordinary" @click="addProperty">
          {{ $t("standards.ordinary.add") }}
        </UiButton>
      </div>
    </header>
    <p class="flow-note" role="note">{{ $t("standards.ordinary.flow") }}</p>
    <p class="identity-note" role="note">{{ $t("standards.ordinary.identityNote") }}</p>
    <p v-if="blocked" class="delete-error" role="alert" data-testid="ordinary-delete-blocked">
      {{ $t("standards.ordinary.deleteBlocked", {count: blocked.owners.length, owners: blocked.owners.join(t("standards.enumDialog.nameSeparator"))}) }}
    </p>
    <p v-if="ordinaryProperties.length === 0" class="section-empty">{{ $t("standards.ordinary.empty") }}</p>
    <!-- 宽表局部滚动（PLAN-DM-039 Task 3）：页面本身不横向滚动，表格保持可读的结构基线宽度
         （SPEC-DM-017 编辑器 Demo 的 930px），只在自身容器内滚动。 -->
    <div v-else class="ordinary-scroll" data-testid="ordinary-table-scroll">
      <table class="ordinary-table" data-testid="ordinary-table">
      <thead>
        <tr>
          <th scope="col" class="col-name">{{ $t("standards.ordinary.name") }}</th>
          <th scope="col" class="col-scope">{{ $t("standards.ordinary.scope") }}</th>
          <th scope="col" class="col-kind">{{ $t("standards.ordinary.kind") }}</th>
          <th scope="col" class="col-required">{{ $t("standards.ordinary.required") }}</th>
          <th scope="col" class="col-default">{{ $t("standards.ordinary.defaultValue") }}</th>
          <th scope="col" class="col-enum">{{ $t("standards.ordinary.enumValues") }}</th>
          <th scope="col" class="col-description">{{ $t("standards.ordinary.description") }}</th>
          <th scope="col" class="col-actions"><span class="sr-only-label">{{ $t("standards.ordinary.remove") }}</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="property in ordinaryProperties" :key="property.property_id">
          <td class="col-name">
            <UiInput
              v-model="property.name"
              :label="$t('standards.ordinary.name')"
              :aria-label="$t('standards.ordinary.name')"
              :invalid="hasError(property)"
              :data-testid="`ordinary-name-${property.property_id}`"
            />
            <p v-if="hasError(property)" class="row-issue" :data-testid="`ordinary-issue-${property.property_id}`">
              {{ issueText(property) }}
            </p>
          </td>
          <td class="col-scope">
            <select
              v-if="isCreated(property)"
              class="cell-select"
              :value="property.scope"
              :aria-label="$t('standards.ordinary.scope')"
              :data-testid="`ordinary-scope-${property.property_id}`"
              @change="setScope(property, ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="scope in PROPERTY_SCOPES" :key="scope" :value="scope">{{ scope }}</option>
            </select>
            <span
              v-else
              class="scope-locked"
              :title="$t('standards.ordinary.scopeLocked')"
              :data-testid="`ordinary-scope-badge-${property.property_id}`"
            >{{ property.scope }}</span>
          </td>
          <td class="col-kind">
            <select
              class="cell-select"
              :value="property.kind"
              :aria-label="$t('standards.ordinary.kind')"
              :data-testid="`ordinary-kind-${property.property_id}`"
              @change="setKind(property, ($event.target as HTMLSelectElement).value)"
            >
              <option value="text">{{ $t("standards.ordinary.kindText") }}</option>
              <option value="enum">{{ $t("standards.ordinary.kindEnum") }}</option>
            </select>
          </td>
          <td class="col-required">
            <label class="required-hit">
              <input
                type="checkbox"
                class="required-check"
                :checked="property.required"
                :aria-label="$t('standards.ordinary.required')"
                :data-testid="`ordinary-required-${property.property_id}`"
                @change="setRequired(property, $event)"
              >
            </label>
          </td>
          <td class="col-default">
            <UiInput
              v-model="property.default_value"
              :label="$t('standards.ordinary.defaultValue')"
              :aria-label="$t('standards.ordinary.defaultValue')"
              :placeholder="$t('standards.ordinary.defaultPlaceholder')"
              :data-testid="`ordinary-default-${property.property_id}`"
            />
          </td>
          <td class="col-enum">
            <div class="enum-cell">
              <!-- 摘要即触发器（SPEC-DM-017 编辑器 Demo）：枚举值文本本身可点进入编辑对话框，
                   不再另设一个与摘要平级的动作按钮——那样会与摘要争宽并把行撑高。 -->
              <button
                v-if="property.kind === 'enum'"
                type="button"
                class="enum-trigger"
                :title="$t('standards.enumDialog.title', {name: property.name})"
                :data-testid="`edit-enum-${property.property_id}`"
                @click="openEnumDialog(property)"
              >
                <span class="enum-summary" :data-testid="`enum-summary-${property.property_id}`">{{ enumSummary(property) }}</span>
              </button>
              <span
                v-else
                class="enum-summary enum-summary--disabled"
                aria-disabled="true"
                :data-testid="`enum-summary-${property.property_id}`"
              >{{ $t("standards.ordinary.enumDisabled") }}</span>
            </div>
          </td>
          <td class="col-description">
            <UiInput
              v-model="property.description"
              :label="$t('standards.ordinary.description')"
              :aria-label="$t('standards.ordinary.description')"
              :data-testid="`ordinary-description-${property.property_id}`"
            />
          </td>
          <td class="col-actions">
            <UiIconButton
              icon="close"
              :label="$t('standards.ordinary.remove')"
              :data-testid="`ordinary-remove-${property.property_id}`"
              @click="removeProperty(property)"
            />
          </td>
        </tr>
      </tbody>
      </table>
    </div>
    <EnumValuesDialog
      :open="dialogProperty !== null"
      :property="dialogProperty"
      :impacted-names="impactedNames"
      @save="saveEnum"
      @cancel="dialogPropertyId = null"
    />
    <div v-if="csvOpen" class="modal-mask" @click.self="csvOpen = false" @keydown="onCsvKeydown">
      <section ref="csvCard" class="csv-dialog" role="dialog" aria-modal="true" tabindex="-1" :aria-label="$t('standards.ordinary.csv.title')">
        <h4 class="csv-title">{{ $t("standards.ordinary.csv.title") }}</h4>
        <p class="csv-hint">{{ $t("standards.ordinary.csv.hint") }}</p>
        <!-- 可见关联标签：label[for] 指向文本域，不依赖 aria-label 代替可见标签 -->
        <label class="csv-label" for="csv-content-input">{{ $t("standards.ordinary.csv.content") }}</label>
        <textarea id="csv-content-input" v-model="csvText" class="csv-input" rows="6" />
        <div class="csv-actions">
          <UiButton variant="secondary" @click="csvOpen = false">{{ $t("standards.enumDialog.cancel") }}</UiButton>
          <UiButton
            variant="secondary"
            :disabled="csvRows.length === 0"
            data-testid="apply-csv"
            @click="applyCsv"
          >{{ csvRows.length === 0 ? $t("standards.ordinary.csv.empty") : $t("standards.ordinary.csv.apply", {count: csvRows.length}) }}</UiButton>
        </div>
      </section>
    </div>
  </section>
</template>
<style scoped>
.ordinary-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
.flow-note,.identity-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.identity-note{color:var(--color-text-muted)}
.delete-error{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);font-size:var(--font-label)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.ordinary-scroll{overflow-x:auto;min-width:0}
/* 列标题已由表头表达（SPEC-DM-017 编辑器 Demo）：单元格内的 UiInput 可见字段标签
   会与表头重复、把行撑高并造成错位。标签保留在 DOM 与调用点 `label` 属性中
   （`check:ui` 的 visible-input-label 契约），可访问名由输入框自身的 `aria-label` 承担；
   仅视觉隐藏（`display:none`），不删除标签节点。 */
.ordinary-table :deep(.ui-input){gap:0}
.ordinary-table :deep(.ui-input__label){display:none}
.ordinary-table{width:100%;min-width:var(--standards-table-min-width);border-collapse:collapse;table-layout:fixed}
.ordinary-table th,.ordinary-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;vertical-align:top}
.ordinary-table th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500}
.col-scope{width:12%}
.col-kind{width:11%}
.col-required{width:8%;text-align:center}
.col-actions{width:7%;text-align:center}
.scope-locked{display:inline-block;padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-label)}
.cell-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
/* 必填复选框：本体固定 16×16，点击区域由标签扩展到 32×32，不继承输入框的统一高度与宽度。 */
.required-hit{display:inline-grid;place-items:center;width:var(--tap-target-min);height:var(--tap-target-min);border-radius:var(--radius-md);cursor:pointer}
.required-hit:hover{background:var(--color-bg-muted)}
.required-check{box-sizing:border-box;width:var(--checkbox-size);height:var(--checkbox-size);margin:0;padding:0;flex:none}
.row-issue{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-danger)}
.enum-cell{display:flex;align-items:center;min-width:0}
/* 枚举摘要即触发器（SPEC-DM-017 编辑器 Demo）：按钮只包住摘要文本，
   尺寸随单元格而不是被长摘要拉伸或折行。
   可访问名就是可见摘要文本（WCAG 2.5.3 Label in Name）；动作说明放在 `title` 上，
   它会在可访问名已由内容提供时作为可访问描述被读屏播报（不能改用 `aria-label` 覆盖可见文本）。 */
.enum-trigger{box-sizing:border-box;width:100%;min-width:0;min-height:var(--input-height);padding:0 var(--space-2);text-align:left;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);cursor:pointer}
.enum-trigger:hover{border-color:var(--color-accent)}
.enum-summary{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--font-label);color:var(--color-accent)}
.enum-summary--disabled{padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-muted)}
.sr-only-label{font-size:var(--font-label)}
.csv-dialog{display:grid;gap:var(--space-2);width:min(560px,calc(100vw - 32px));padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3)}
.csv-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.csv-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.csv-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.csv-input{box-sizing:border-box;width:100%;padding:var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font-family:var(--font-mono);font-size:var(--input-font-size)}
.csv-actions{display:flex;justify-content:flex-end;gap:var(--space-2)}
</style>
