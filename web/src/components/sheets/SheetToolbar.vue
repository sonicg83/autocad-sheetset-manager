<script setup lang="ts">
// 图纸工作区工具栏（PLAN-DM-015 任务 3/4，SPEC-DM-009 §3.1/§4.1/§4.2/§6.3）。
// 标题栏（当前范围 + 匹配/范围总数 + 已加载数 + 新增操作入口）、常驻搜索、
// 「筛选」展开的低频筛选、可清除条件标签、「显示列」配置面板、吸顶选择条（勾选集合 + 批量修改属性展开）。
// 新增操作入口先接线到任务 6 的表单（任务 3 提供过渡实现，一次只出现一种）。
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {BuiltinPrefField, SheetColumnOption} from "../../composables/useSheetColumns";
import type {SheetDiagFilter, SheetPathFilter, SheetPendingFilter} from "../../composables/useSheetsWorkspace";
import ColumnSettings from "./ColumnSettings.vue";
import UiButton from "../ui/UiButton.vue";

export type OperationKind = "rename" | "insert-sheet" | "insert-subset";

const props = defineProps<{
  rangeTitle: string;
  rangeTotal: number;
  matchCount: number;
  visibleCount: number;
  searchText: string;
  searchAll: boolean;
  filtersVisible: boolean;
  pathFilter: SheetPathFilter;
  diagnosticFilter: SheetDiagFilter;
  pendingFilter: SheetPendingFilter;
  selectedCount: number;
  hiddenSelectedCount: number;
  allFilteredSelected: boolean;
  canSelect: boolean;
  sheetPropertyNames: string[];
  bulkPropertyName: string;
  bulkPropertyValue: string;
  bulkMode: "set" | "clear";
  columnOptions: SheetColumnOption[];
  columnSaveError: string;
  newPropertyCount: number;
}>();
const searchText = defineModel<string>("searchText", {default: ""});
const searchAll = defineModel<boolean>("searchAll", {default: false});
const filtersVisible = defineModel<boolean>("filtersVisible", {default: false});
const pathFilter = defineModel<SheetPathFilter>("pathFilter", {default: "all"});
const diagnosticFilter = defineModel<SheetDiagFilter>("diagnosticFilter", {default: "all"});
const pendingFilter = defineModel<SheetPendingFilter>("pendingFilter", {default: "all"});
const bulkPropertyName = defineModel<string>("bulkPropertyName", {default: ""});
const bulkPropertyValue = defineModel<string>("bulkPropertyValue", {default: ""});
const bulkMode = defineModel<"set" | "clear">("bulkMode", {default: "set"});
const emit = defineEmits<{
  clearFilters: [];
  toggleFilteredSelection: [];
  clearSelection: [];
  queueBulkSheetProperty: [];
  openOperation: [kind: OperationKind];
  toggleBuiltin: [field: BuiltinPrefField, value: boolean];
  toggleProperty: [name: string, value: boolean];
  resetColumns: [];
}>();

function onToggleBuiltin(field: BuiltinPrefField, value: boolean) { emit("toggleBuiltin", field, value); }
function onToggleProperty(name: string, value: boolean) { emit("toggleProperty", name, value); }
function onResetColumns() { emit("resetColumns"); }

const {t} = useI18n();
// 筛选枚举 → 生效条件标签语义键映射（稳定筛选值 → sheets.toolbar.chips.*，整句键不做调用点拼接）
const CHIP_KEYS = {
  "path-resolved": {label: "sheets.toolbar.chips.pathResolved", clear: "sheets.toolbar.chips.pathResolvedClear"},
  "path-unresolved": {label: "sheets.toolbar.chips.pathUnresolved", clear: "sheets.toolbar.chips.pathUnresolvedClear"},
  "diag-blocking": {label: "sheets.toolbar.chips.diagBlocking", clear: "sheets.toolbar.chips.diagBlockingClear"},
  "diag-clean": {label: "sheets.toolbar.chips.diagClean", clear: "sheets.toolbar.chips.diagCleanClear"},
  "pending-pending": {label: "sheets.toolbar.chips.pendingPending", clear: "sheets.toolbar.chips.pendingPendingClear"},
  "pending-unchanged": {label: "sheets.toolbar.chips.pendingUnchanged", clear: "sheets.toolbar.chips.pendingUnchangedClear"},
} as const;

// 批量输入默认折叠：「选择后出现吸顶选择条，点击'批量修改属性'展开输入」
const bulkExpanded = ref(false);

function resetBulkInputs() {
  bulkMode.value = "set";
  bulkPropertyName.value = "";
  bulkPropertyValue.value = "";
}

function exitBulkAndToggleFilteredSelection() {
  bulkExpanded.value = false;
  resetBulkInputs();
  emit("toggleFilteredSelection");
}

function exitBulkAndClearSelection() {
  bulkExpanded.value = false;
  resetBulkInputs();
  emit("clearSelection");
}

watch(() => props.selectedCount, (selectedCount) => {
  if (selectedCount === 0) {
    bulkExpanded.value = false;
    resetBulkInputs();
  }
});

// 生效条件以可清除标签展示（低频筛选）
const conditionChips = computed(() => {
  const chips: {key: string; label: string; clearLabel: string; clear: () => void}[] = [];
  const push = (key: keyof typeof CHIP_KEYS, clear: () => void) => {
    chips.push({key, label: t(CHIP_KEYS[key].label), clearLabel: t(CHIP_KEYS[key].clear), clear});
  };
  if (pathFilter.value === "resolved") push("path-resolved", () => { pathFilter.value = "all"; });
  if (pathFilter.value === "unresolved") push("path-unresolved", () => { pathFilter.value = "all"; });
  if (diagnosticFilter.value === "blocking") push("diag-blocking", () => { diagnosticFilter.value = "all"; });
  if (diagnosticFilter.value === "clean") push("diag-clean", () => { diagnosticFilter.value = "all"; });
  if (pendingFilter.value === "pending") push("pending-pending", () => { pendingFilter.value = "all"; });
  if (pendingFilter.value === "unchanged") push("pending-unchanged", () => { pendingFilter.value = "all"; });
  return chips;
});
</script>
<template>
  <div class="sheets-toolbar">
    <div class="toolbar-head">
      <h2 class="range-title">{{ rangeTitle }}</h2>
      <div class="counts">
        <span class="count">{{ $t("sheets.toolbar.counts", {match: matchCount, total: rangeTotal}) }}</span>
        <span class="loaded">{{ $t("sheets.toolbar.loadedRows", {count: visibleCount}) }}</span>
      </div>
      <div class="operations">
        <!-- 三类操作入口常驻显示（任务 6）：同一表单已打开时点击不重开，另一表单经三选一保护切换 -->
        <UiButton size="compact" @click="$emit('openOperation', 'rename')">{{ $t("sheets.toolbar.renameSubset") }}</UiButton>
        <UiButton size="compact" @click="$emit('openOperation', 'insert-sheet')">{{ $t("sheets.toolbar.insertSheet") }}</UiButton>
        <UiButton size="compact" @click="$emit('openOperation', 'insert-subset')">{{ $t("sheets.toolbar.insertSubset") }}</UiButton>
      </div>
    </div>
    <div class="toolbar-filters">
      <label class="search-box">{{ $t("sheets.toolbar.searchLabel") }}<input v-model="searchText" :placeholder="$t('sheets.toolbar.searchPlaceholder')"></label>
      <label class="search-all"><input v-model="searchAll" type="checkbox">{{ $t("sheets.toolbar.searchAll") }}</label>
      <UiButton size="compact" class="filter-toggle" @click="filtersVisible = !filtersVisible">{{ $t("sheets.toolbar.filterToggle") }}</UiButton>
      <ColumnSettings
        :options="columnOptions"
        :save-error="columnSaveError"
        :new-property-count="newPropertyCount"
        @toggle-builtin="onToggleBuiltin"
        @toggle-property="onToggleProperty"
        @reset="onResetColumns"
      />
      <template v-if="filtersVisible">
        <label>{{ $t("sheets.toolbar.pathFilterLabel") }}<select v-model="pathFilter"><option value="all">{{ $t("sheets.toolbar.filterAll") }}</option><option value="resolved">{{ $t("sheets.toolbar.filterResolved") }}</option><option value="unresolved">{{ $t("sheets.toolbar.filterUnresolved") }}</option></select></label>
        <label>{{ $t("sheets.toolbar.diagFilterLabel") }}<select v-model="diagnosticFilter"><option value="all">{{ $t("sheets.toolbar.filterAll") }}</option><option value="blocking">{{ $t("sheets.toolbar.filterBlocking") }}</option><option value="clean">{{ $t("sheets.toolbar.filterClean") }}</option></select></label>
        <label>{{ $t("sheets.toolbar.pendingFilterLabel") }}<select v-model="pendingFilter"><option value="all">{{ $t("sheets.toolbar.filterAll") }}</option><option value="pending">{{ $t("sheets.toolbar.filterPending") }}</option><option value="unchanged">{{ $t("sheets.toolbar.filterUnchanged") }}</option></select></label>
      </template>
      <div v-if="conditionChips.length" class="chips">
        <span v-for="chip in conditionChips" :key="chip.key" class="chip">
          <span class="chip-label">{{ chip.label }}</span>
          <button type="button" class="chip-clear" :aria-label="chip.clearLabel" @click="chip.clear()">✕</button>
        </span>
        <button type="button" class="chips-clear-all" @click="$emit('clearFilters')">{{ $t("sheets.toolbar.clearAllFilters") }}</button>
      </div>
    </div>
    <!-- 未选择时只显示选择入口；选择后出现吸顶选择条 -->
    <div v-if="selectedCount" class="selection-bar">
      <div class="selection-actions">
        <span class="selection-summary" role="status">{{ $t("sheets.toolbar.selectionSummary", {selected: selectedCount, hidden: hiddenSelectedCount}) }}</span>
        <UiButton size="compact" :disabled="!canSelect" @click="exitBulkAndToggleFilteredSelection">{{ allFilteredSelected ? $t("sheets.toolbar.unselectAllFiltered") : $t("sheets.toolbar.selectAllFiltered") }}</UiButton>
        <UiButton size="compact" @click="exitBulkAndClearSelection">{{ $t("sheets.toolbar.clearSelection") }}</UiButton>
        <UiButton size="compact" class="bulk-toggle" @click="bulkExpanded = !bulkExpanded">{{ $t("sheets.toolbar.bulkToggle") }}</UiButton>
      </div>
      <div v-if="bulkExpanded" class="bulk-controls">
        <label>{{ $t("sheets.toolbar.bulkModeLabel") }}<select v-model="bulkMode"><option value="set">{{ $t("sheets.toolbar.bulkModeSet") }}</option><option value="clear">{{ $t("sheets.toolbar.bulkModeClear") }}</option></select></label>
        <label>{{ $t("sheets.toolbar.bulkPropertyLabel") }}<select v-model="bulkPropertyName"><option value="">{{ $t("sheets.toolbar.bulkPropertyPlaceholder") }}</option><option v-for="name in sheetPropertyNames" :key="name" :value="name">{{ name }}</option></select></label>
        <template v-if="bulkMode === 'set'">
          <label>{{ $t("sheets.toolbar.bulkValueLabel") }}<input v-model="bulkPropertyValue"></label>
          <UiButton size="compact" :disabled="!bulkPropertyName" @click="$emit('queueBulkSheetProperty')">{{ $t("sheets.toolbar.bulkQueue") }}</UiButton>
        </template>
        <template v-else>
          <span class="bulk-hint">{{ $t("sheets.toolbar.bulkClearHint") }}</span>
          <button type="button" class="danger" :disabled="!bulkPropertyName" @click="$emit('queueBulkSheetProperty')">{{ $t("sheets.toolbar.bulkClearQueue") }}</button>
        </template>
      </div>
    </div>
  </div>
</template>
<style scoped>
.sheets-toolbar{display:flex;flex-direction:column;gap:var(--space-3)}
.toolbar-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.range-title{margin:0;font-size:var(--font-toolbar-title);color:var(--color-text-primary)}
.counts{display:flex;gap:var(--space-3);font-size:var(--font-label);color:var(--color-text-secondary)}
.operations{margin-left:auto;display:flex;gap:var(--space-2)}
/* Task 7：这些按钮已改用 UiButton size="compact"（34px），本页不再自建高度。仅保留 :deep(.cols-toggle)：
   “显示列”入口在子组件内部，其行高/内边距/圆角/字号仍需由工具栏行统一约束。
   本规则是这些属性的**唯一**声明方（`ColumnSettings.vue` 侧已不再重复声明）：两侧同特异性时
   重复声明会让生效值随样式表注入顺序变化。 */
:deep(.cols-toggle){height:var(--control-height-compact);min-height:var(--control-height-compact);padding:0 var(--space-3);border-radius:var(--radius-md);font-size:var(--font-label)}
.toolbar-filters{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:var(--font-label)}
.search-box input{width:var(--sheet-search-width)}
.sheets-toolbar :is(input:not([type="checkbox"]),select){height:var(--control-height-form);min-width:0;max-width:100%;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.sheets-toolbar :is(input,select):focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.sheets-toolbar :is(input:not([type="checkbox"]),select):hover:not(:disabled){border-color:var(--color-accent)}
.sheets-toolbar :is(input,select):disabled{background:var(--color-bg-muted);color:var(--color-text-muted);cursor:not-allowed}
.toolbar-filters label{display:inline-flex;align-items:center;gap:6px}
.search-all{white-space:nowrap}
.chips{display:inline-flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--radius-lg);background:var(--color-info-bg);font-size:var(--font-caption)}
/* 审查 I1：可见 ✕ 与点击盒分离。内容盒保持字形大小（--icon-size-sm），透明 padding 把
   点击区扩到 --tap-target-min（32px），再以负 margin 抵消 padding 对布局的撑开——
   胶囊视觉尺寸不变。点击盒允许与相邻标签文本轻微重叠：标签不可交互，可点面积优先。
   不另设 hover 背景，避免重叠区出现误导性反馈。 */
.chip-clear{box-sizing:content-box;display:inline-flex;align-items:center;justify-content:center;width:var(--icon-size-sm);height:var(--icon-size-sm);padding:calc((var(--tap-target-min) - var(--icon-size-sm)) / 2);margin:calc((var(--icon-size-sm) - var(--tap-target-min)) / 2);border:none;background:none;cursor:pointer;color:var(--color-text-secondary);font-size:var(--font-caption);line-height:1;flex:none}
.selection-bar{display:flex;flex-direction:column;align-items:stretch;gap:var(--space-2);position:sticky;top:0;z-index:5;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md,8px);background:var(--color-bg-surface)}
.selection-actions,.bulk-controls{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.bulk-controls{padding-top:var(--space-2);border-top:1px solid var(--color-border-subtle)}
.bulk-controls label{display:inline-flex;align-items:center;gap:6px}
.selection-summary{font-weight:600;color:var(--color-text-primary)}
.bulk-hint{color:var(--color-text-secondary);font-size:var(--font-caption);max-width:var(--sheet-bulk-hint-max-width)}
.bulk-hint + .danger,.selection-bar .danger{color:var(--color-danger)}
</style>
