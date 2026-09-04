<script setup lang="ts">
// 图纸工作区工具栏（PLAN-DM-015 任务 3，SPEC-DM-009 §3.1/§4.1/§4.2/§6.3）。
// 标题栏（当前范围 + 匹配/范围总数 + 已加载数 + 新增操作入口）、常驻搜索、
// 「筛选」展开的低频筛选、可清除条件标签、吸顶选择条（勾选集合 + 批量修改属性展开）。
// 新增操作入口先接线到任务 6 的表单（任务 3 提供过渡实现，一次只出现一种）。
import {computed, ref} from "vue";
import type {SheetDiagFilter, SheetPathFilter, SheetPendingFilter} from "../../composables/useSheetsWorkspace";

export type OperationKind = "rename" | "insert-sheet" | "insert-subset";

defineProps<{
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
  activeOperation: OperationKind | null;
}>();
const searchText = defineModel<string>("searchText", {default: ""});
const searchAll = defineModel<boolean>("searchAll", {default: false});
const filtersVisible = defineModel<boolean>("filtersVisible", {default: false});
const pathFilter = defineModel<SheetPathFilter>("pathFilter", {default: "all"});
const diagnosticFilter = defineModel<SheetDiagFilter>("diagnosticFilter", {default: "all"});
const pendingFilter = defineModel<SheetPendingFilter>("pendingFilter", {default: "all"});
const bulkPropertyName = defineModel<string>("bulkPropertyName", {default: ""});
const bulkPropertyValue = defineModel<string>("bulkPropertyValue", {default: ""});
const emit = defineEmits<{
  clearFilters: [];
  toggleFilteredSelection: [];
  clearSelection: [];
  queueBulkSheetProperty: [];
  openOperation: [kind: OperationKind];
}>();

// 批量输入默认折叠：「选择后出现吸顶选择条，点击'批量修改属性'展开输入」
const bulkExpanded = ref(false);

// 生效条件以可清除标签展示（低频筛选）
const conditionChips = computed(() => {
  const chips: {key: string; label: string; clearLabel: string; clear: () => void}[] = [];
  if (pathFilter.value === "resolved") chips.push({key: "path-resolved", label: "路径：已解析", clearLabel: "清除筛选：路径已解析", clear: () => { pathFilter.value = "all"; }});
  if (pathFilter.value === "unresolved") chips.push({key: "path-unresolved", label: "路径：未解析", clearLabel: "清除筛选：路径未解析", clear: () => { pathFilter.value = "all"; }});
  if (diagnosticFilter.value === "blocking") chips.push({key: "diag-blocking", label: "诊断：有阻断", clearLabel: "清除筛选：有阻断诊断", clear: () => { diagnosticFilter.value = "all"; }});
  if (diagnosticFilter.value === "clean") chips.push({key: "diag-clean", label: "诊断：无阻断", clearLabel: "清除筛选：无阻断诊断", clear: () => { diagnosticFilter.value = "all"; }});
  if (pendingFilter.value === "pending") chips.push({key: "pending-pending", label: "待变更：待变更", clearLabel: "清除筛选：待变更", clear: () => { pendingFilter.value = "all"; }});
  if (pendingFilter.value === "unchanged") chips.push({key: "pending-unchanged", label: "待变更：未变更", clearLabel: "清除筛选：未变更", clear: () => { pendingFilter.value = "all"; }});
  return chips;
});
</script>
<template>
  <div class="sheets-toolbar">
    <div class="toolbar-head">
      <h2 class="range-title">{{ rangeTitle }}</h2>
      <div class="counts">
        <span class="count">匹配 {{ matchCount }} / 全部 {{ rangeTotal }} 张</span>
        <span class="loaded">已加载 {{ visibleCount }} 行</span>
      </div>
      <div class="operations">
        <button type="button" @click="$emit('openOperation', 'rename')">编辑子集</button>
        <button type="button" @click="$emit('openOperation', 'insert-sheet')">新增图纸</button>
        <button v-if="activeOperation !== 'insert-subset'" type="button" @click="$emit('openOperation', 'insert-subset')">新建子集</button>
      </div>
    </div>
    <div class="toolbar-filters">
      <label class="search-box">搜索图纸<input v-model="searchText" placeholder="图号、标题、属性或 DWG"></label>
      <label class="search-all"><input v-model="searchAll" type="checkbox">搜索全部图纸</label>
      <button type="button" class="filter-toggle" @click="filtersVisible = !filtersVisible">筛选</button>
      <template v-if="filtersVisible">
        <label>路径状态<select v-model="pathFilter"><option value="all">全部</option><option value="resolved">已解析</option><option value="unresolved">未解析</option></select></label>
        <label>诊断状态<select v-model="diagnosticFilter"><option value="all">全部</option><option value="blocking">有阻断诊断</option><option value="clean">无阻断诊断</option></select></label>
        <label>待变更状态<select v-model="pendingFilter"><option value="all">全部</option><option value="pending">待变更</option><option value="unchanged">未变更</option></select></label>
      </template>
      <div v-if="conditionChips.length" class="chips">
        <span v-for="chip in conditionChips" :key="chip.key" class="chip">
          <span class="chip-label">{{ chip.label }}</span>
          <button type="button" class="chip-clear" :aria-label="chip.clearLabel" @click="chip.clear()">✕</button>
        </span>
        <button type="button" class="chips-clear-all" @click="$emit('clearFilters')">清除全部筛选</button>
      </div>
    </div>
    <!-- 未选择时只显示选择入口；选择后出现吸顶选择条 -->
    <div v-if="selectedCount" class="selection-bar">
      <span class="selection-summary" role="status">已选 {{ selectedCount }} 张，其中 {{ hiddenSelectedCount }} 张不在当前结果</span>
      <button type="button" :disabled="!canSelect" @click="$emit('toggleFilteredSelection')">{{ allFilteredSelected ? "取消全选当前结果" : "全选当前结果" }}</button>
      <button type="button" @click="$emit('clearSelection')">清除选择</button>
      <button type="button" class="bulk-toggle" @click="bulkExpanded = !bulkExpanded">批量修改属性</button>
      <template v-if="bulkExpanded">
        <label>既有图纸属性<select v-model="bulkPropertyName"><option value="">请选择</option><option v-for="name in sheetPropertyNames" :key="name" :value="name">{{ name }}</option></select></label>
        <label>批量值<input v-model="bulkPropertyValue"></label>
        <button type="button" :disabled="!bulkPropertyName" @click="$emit('queueBulkSheetProperty')">批量加入草稿</button>
      </template>
    </div>
    <div v-else class="select-entry">
      <button type="button" :disabled="!canSelect" @click="$emit('toggleFilteredSelection')">{{ allFilteredSelected ? "取消全选当前结果" : "全选当前结果" }}</button>
    </div>
  </div>
</template>
<style scoped>
.sheets-toolbar{display:flex;flex-direction:column;gap:var(--space-3)}
.toolbar-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.range-title{margin:0;font-size:17px;color:var(--color-text-primary)}
.counts{display:flex;gap:var(--space-3);font-size:13px;color:var(--color-text-secondary)}
.operations{margin-left:auto;display:flex;gap:var(--space-2)}
.toolbar-filters{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:13px}
.search-box input{width:260px}
.toolbar-filters label{display:inline-flex;align-items:center;gap:6px}
.search-all{white-space:nowrap}
.chips{display:inline-flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;background:var(--color-accent-soft,var(--color-bg-surface-2));font-size:12px}
.chip-clear{border:none;background:none;cursor:pointer;color:var(--color-text-secondary);font-size:12px;padding:0}
.selection-bar{display:flex;align-items:center;gap:var(--space-3);position:sticky;top:0;z-index:5;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);background:var(--color-bg-surface);flex-wrap:wrap}
.selection-summary{font-weight:600;color:var(--color-text-primary)}
.select-entry{display:flex}
</style>
