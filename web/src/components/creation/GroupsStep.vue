<script setup lang="ts">
// 第三阶段：图纸组（SPEC-DM-018 §4；PLAN-DM-036 Task 8）。
// 一行一个子集、一个主 DWG：图名｜张数｜基础模板｜布局模板｜图幅｜其他可输入 sheet 属性
// + 末列操作。末列沿用图纸目录插件的 32×32 图标按钮视觉（↑/↓/✕，各自有完整可访问名称，
// 首末行禁用正确）。新建组复制创建序最大的组并聚焦图名；重复图名只标错、不自动改名。
// 图号、标题、DWG 文件名与派生属性由预览计算，本阶段不提供逐张输入。
import {computed, nextTick, ref, type ComponentPublicInstance} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import GroupBatchDialog from "./GroupBatchDialog.vue";
import {BASE_TEMPLATE_KIND, LAYOUT_TEMPLATE_KIND, creationAssetOptions, creationPaperLayouts} from "../../features/creation/inputModel";
import type {CreationGroupIssueCode} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{store: CreationStore}>();
const {t} = useI18n();

const batchOpen = ref(false);
const titleInputs = ref<Record<string, HTMLInputElement | null>>({});

// 即时提示码 → 语言包键的稳定映射（不在模板里拼键名）
const ISSUE_KEYS: Record<CreationGroupIssueCode, string> = {
  title_empty: "creation.groups.issueTitleEmpty",
  title_duplicate: "creation.groups.issueTitleDuplicate",
  count_invalid: "creation.groups.issueCountInvalid",
  base_asset_missing: "creation.groups.issueBaseMissing",
  layout_asset_missing: "creation.groups.issueLayoutMissing",
  paper_layout_missing: "creation.groups.issuePaperMissing",
};

const sheetProperties = computed(() => props.store.standard?.sheet_properties ?? []);
const baseOptions = computed(() => creationAssetOptions(props.store.standard, BASE_TEMPLATE_KIND));
const layoutOptions = computed(() => creationAssetOptions(props.store.standard, LAYOUT_TEMPLATE_KIND));
const totalSheets = computed(() =>
  props.store.groups.reduce((sum, group) => sum + (Number.isFinite(group.count) ? group.count : 0), 0),
);
const allSelected = computed(
  () =>
    props.store.groups.length > 0 &&
    props.store.selectedGroupIds.length === props.store.groups.length,
);

function issueText(code: CreationGroupIssueCode): string {
  return t(ISSUE_KEYS[code]);
}
function issuesOf(groupId: string): CreationGroupIssueCode[] {
  return props.store.groupIssues(groupId);
}
/** 单元格可访问名：表头给出列名，这里补上组序号，避免整列同名控件无法区分。 */
function cellLabel(index: number, column: string): string {
  return t("creation.groups.cellFor", {index: index + 1, column});
}
function registerTitleInput(groupId: string, instance: ComponentPublicInstance | null): void {
  const root = instance?.$el;
  titleInputs.value[groupId] = root instanceof HTMLElement ? root.querySelector<HTMLInputElement>("input") : null;
}
function paperOptions(group: {layout_asset_id: string}): string[] {
  return creationPaperLayouts(props.store.standard, group.layout_asset_id);
}
async function addGroup(): Promise<void> {
  const group = props.store.addGroup();
  await nextTick();
  const input = titleInputs.value[group.group_id];
  input?.focus();
  input?.select();
}
function toggleAll(event: Event): void {
  if ((event.target as HTMLInputElement).checked) props.store.selectAllGroups();
  else props.store.clearGroupSelection();
}
</script>
<template>
  <section class="groups-step" role="region" :aria-label="$t('creation.groups.region')">
    <section class="card">
      <header class="card-head">
        <div>
          <h2>{{ $t("creation.groups.title") }}</h2>
          <p>{{ $t("creation.groups.lead") }}</p>
        </div>
        <div class="toolbar">
          <UiButton variant="secondary" @click="addGroup">{{ $t("creation.groups.add") }}</UiButton>
          <UiButton
            variant="secondary" :disabled="store.selectedGroupIds.length === 0"
            @click="batchOpen = true"
          >{{ $t("creation.groups.batchOpen") }}</UiButton>
          <span class="summary" data-testid="creation-group-summary">
            {{ $t("creation.groups.summary", {groups: store.groups.length, sheets: totalSheets}) }}
          </span>
        </div>
      </header>
      <p class="note">{{ $t("creation.groups.addHint") }}</p>
      <p v-if="store.groups.length === 0" class="note" data-testid="creation-groups-empty">
        {{ $t("creation.groups.empty") }}
      </p>
      <div v-else class="table-scroll">
        <table class="group-table" :aria-label="$t('creation.groups.tableLabel')">
          <thead>
            <tr>
              <th class="select-col">
                <label class="select-hit">
                  <input
                    type="checkbox" :checked="allSelected"
                    :aria-label="$t('creation.groups.selectAll')" @change="toggleAll"
                  >
                </label>
              </th>
              <th>{{ $t("creation.groups.columnTitle") }}</th>
              <th>{{ $t("creation.groups.columnCount") }}</th>
              <th>{{ $t("creation.groups.columnBase") }}</th>
              <th>{{ $t("creation.groups.columnLayout") }}</th>
              <th>{{ $t("creation.groups.columnPaper") }}</th>
              <th v-for="property in sheetProperties" :key="property.property_id">{{ property.name }}</th>
              <th>{{ $t("creation.groups.columnActions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(group, index) in store.groups" :key="group.group_id" :data-group-id="group.group_id">
              <td class="select-col">
                <label class="select-hit">
                  <input
                    type="checkbox" :checked="store.selectedGroupIds.includes(group.group_id)"
                    :aria-label="$t('creation.groups.selectGroup', {index: index + 1})"
                    @change="store.toggleGroup(group.group_id, ($event.target as HTMLInputElement).checked)"
                  >
                </label>
              </td>
              <td class="title-cell">
                <UiInput
                  :ref="instance => registerTitleInput(group.group_id, instance as ComponentPublicInstance | null)"
                  :label="$t('creation.groups.columnTitle')"
                  :aria-label="cellLabel(index, $t('creation.groups.columnTitle'))"
                  :invalid="issuesOf(group.group_id).includes('title_empty') || issuesOf(group.group_id).includes('title_duplicate')"
                  :placeholder="$t('creation.groups.titlePlaceholder')"
                  :model-value="group.title"
                  @update:model-value="(value: string) => store.updateGroup(group.group_id, {title: value})"
                />
                <!-- 即时提示不加 role="alert"：逐键输入时会反复播报；错误态已由 aria-invalid 暴露 -->
                <ul v-if="issuesOf(group.group_id).length > 0" class="row-issues">
                  <li v-for="code in issuesOf(group.group_id)" :key="code">{{ issueText(code) }}</li>
                </ul>
              </td>
              <td class="count-cell">
                <UiInput
                  type="number" :label="$t('creation.groups.columnCount')"
                  :aria-label="cellLabel(index, $t('creation.groups.columnCount'))"
                  :invalid="issuesOf(group.group_id).includes('count_invalid')"
                  :model-value="String(group.count)" min="1" step="1"
                  @update:model-value="(value: string) => store.updateGroup(group.group_id, {count: Number(value)})"
                />
              </td>
              <td>
                <UiSelect
                  :label="$t('creation.groups.columnBase')"
                  :aria-label="cellLabel(index, $t('creation.groups.columnBase'))"
                  :invalid="issuesOf(group.group_id).includes('base_asset_missing')"
                  :model-value="group.base_asset_id"
                  @update:model-value="(value: string) => store.updateGroup(group.group_id, {base_asset_id: value})"
                >
                  <option v-if="baseOptions.length === 0" value="">{{ $t("creation.groups.noOptions") }}</option>
                  <option v-for="option in baseOptions" :key="option.asset_id" :value="option.asset_id">
                    {{ option.label }}
                  </option>
                </UiSelect>
              </td>
              <td>
                <UiSelect
                  :label="$t('creation.groups.columnLayout')"
                  :aria-label="cellLabel(index, $t('creation.groups.columnLayout'))"
                  :invalid="issuesOf(group.group_id).includes('layout_asset_missing')"
                  :model-value="group.layout_asset_id"
                  @update:model-value="(value: string) => store.updateGroup(group.group_id, {layout_asset_id: value})"
                >
                  <option v-if="layoutOptions.length === 0" value="">{{ $t("creation.groups.noOptions") }}</option>
                  <option v-for="option in layoutOptions" :key="option.asset_id" :value="option.asset_id">
                    {{ option.label }}
                  </option>
                </UiSelect>
              </td>
              <td>
                <UiSelect
                  :label="$t('creation.groups.columnPaper')"
                  :aria-label="cellLabel(index, $t('creation.groups.columnPaper'))"
                  :invalid="issuesOf(group.group_id).includes('paper_layout_missing')"
                  :model-value="group.paper_layout"
                  @update:model-value="(value: string) => store.updateGroup(group.group_id, {paper_layout: value})"
                >
                  <option v-if="paperOptions(group).length === 0" value="">{{ $t("creation.groups.noOptions") }}</option>
                  <option v-for="layout in paperOptions(group)" :key="layout" :value="layout">{{ layout }}</option>
                </UiSelect>
              </td>
              <td v-for="property in sheetProperties" :key="property.property_id">
                <UiSelect
                  v-if="property.kind === 'enum'"
                  :label="property.name" :aria-label="cellLabel(index, property.name)"
                  :model-value="group.sheet_values[property.property_id] ?? ''"
                  @update:model-value="(value: string) => store.setGroupSheetValue(group.group_id, property.property_id, value)"
                >
                  <option value="">{{ $t("creation.project.emptyValue") }}</option>
                  <option v-for="option in property.options" :key="option.item_id" :value="option.value">
                    {{ option.value }}
                  </option>
                </UiSelect>
                <UiInput
                  v-else
                  :label="property.name" :aria-label="cellLabel(index, property.name)"
                  :model-value="group.sheet_values[property.property_id] ?? ''"
                  @update:model-value="(value: string) => store.setGroupSheetValue(group.group_id, property.property_id, value)"
                />
              </td>
              <td>
                <div class="row-actions">
                  <button
                    type="button" :disabled="index === 0"
                    :aria-label="$t('creation.groups.moveUp', {index: index + 1})"
                    @click="store.moveGroup(index, index - 1)"
                  >↑</button>
                  <button
                    type="button" :disabled="index === store.groups.length - 1"
                    :aria-label="$t('creation.groups.moveDown', {index: index + 1})"
                    @click="store.moveGroup(index, index + 1)"
                  >↓</button>
                  <button
                    type="button" class="danger-text"
                    :aria-label="$t('creation.groups.remove', {index: index + 1})"
                    @click="store.removeGroup(group.group_id)"
                  >✕</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">{{ $t("creation.groups.derivedHint") }}</p>
    </section>
    <GroupBatchDialog :store="store" :open="batchOpen" @close="batchOpen = false" />
  </section>
</template>
<style scoped>
.groups-step{display:grid;gap:var(--space-4);min-width:0}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);display:grid;gap:var(--space-3);min-width:0}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.card-head h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.card-head p{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.toolbar{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.summary{color:var(--color-text-secondary);font-size:var(--font-caption)}
.note{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
/* 表宽随内容，容器自身横向滚动：900×768 下页面整体不横溢 */
.table-scroll{overflow-x:auto;min-width:0}
.group-table{width:100%;min-width:max-content;border-collapse:collapse}
.group-table th,.group-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;vertical-align:top}
.group-table th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500;white-space:nowrap}
/* 表头已给出列名（与图纸目录编辑器同一做法）：单元格内的可见字段标签会与表头重复并撑高行，
   故仅视觉隐藏标签节点，可访问名由 `aria-label`（含组序号）承担。 */
.group-table :deep(.ui-input){gap:0}
.group-table :deep(.ui-input__label){display:none}
.group-table :deep(.ui-select){gap:0}
.group-table :deep(.ui-select__label){display:none}
.group-table :deep(.ui-select__control){min-width:var(--sheet-property-search-width)}
.select-col{width:var(--tap-target-min)}
.select-hit{display:inline-grid;place-items:center;width:var(--tap-target-min);height:var(--tap-target-min);cursor:pointer}
.title-cell{min-width:var(--sheet-title-max-width)}
.count-cell :deep(.ui-input__control){min-width:var(--space-6)}
.row-issues{list-style:none;margin:var(--space-1) 0 0;padding:0;display:grid;gap:2px;color:var(--color-danger);font-size:var(--font-caption);line-height:1.5}
.row-actions{display:flex;gap:4px;justify-content:flex-end}
.row-actions button{width:var(--tap-target-min);min-height:var(--tap-target-min);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary);font-size:var(--font-label);line-height:1;cursor:pointer}
.row-actions button:hover:not(:disabled){background:var(--color-bg-muted)}
.row-actions button:disabled{cursor:not-allowed;color:var(--color-text-muted)}
.row-actions button.danger-text{color:var(--color-danger)}
</style>
