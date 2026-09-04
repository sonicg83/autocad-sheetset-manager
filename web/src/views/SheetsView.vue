<script setup lang="ts">
// 标签① 图纸：左树右唯一主表工作区（PLAN-DM-015 任务 3，SPEC-DM-009 §3/§4/§6.3）。
// 范围/搜索/筛选/勾选集合由 App.vue 的 useSheetsWorkspace 持有（跨主标签保留），本组件只做呈现与转发。
// 新增操作（编辑子集/新增图纸/新建子集）先接线任务 6 的入口，任务 3 提供非驻留的过渡表单实现。
import {computed} from "vue";
import type {LayoutSourceType, Placement, Sheet, Workspace} from "../api/contracts";
import type {SheetScope} from "../features/sheets/types";
import type {SheetDiagFilter, SheetPathFilter, SheetPendingFilter, SheetRow} from "../composables/useSheetsWorkspace";
import SheetTree from "../components/sheets/SheetTree.vue";
import SheetToolbar, {type OperationKind} from "../components/sheets/SheetToolbar.vue";
import SheetTable from "../components/SheetTable.vue";

type InsertSheetForm = {subsetId: string; sequence: string; direction: Placement; count: string; sourceType: LayoutSourceType; sourceFile: string; sourceLayout: string};
type InsertSubsetForm = {sequence: string; direction: Placement; title: string; initialSheetCount: string; baseTemplateFile: string; templateFile: string; templateLayout: string};

const props = defineProps<{
  workspace: Workspace;
  scope: SheetScope;
  focusedSheetId: string | null;
  selectedIds: string[];
  filteredRows: SheetRow[];
  visibleRows: SheetRow[];
  hiddenSelectedCount: number;
  allFilteredSelected: boolean;
  hiddenTarget: string | null;
  pruneMessage: string;
  scopeTotal: number;
  allTotal: number;
  rangeTotal: number;
  pendingSheetIds: Set<string>;
  diagnosticObjectIds: Set<string>;
  sheetPropertyNames: string[];
  activeOperation: OperationKind | null;
  operationSubsetId: string;
  insertSheetForm: InsertSheetForm;
  insertSubsetForm: InsertSubsetForm;
  layoutOptions: string[]; layoutLoading: boolean; layoutError: string; layoutManual: boolean;
  subsetLayoutOptions: string[]; subsetLayoutLoading: boolean; subsetLayoutError: string; subsetLayoutManual: boolean;
}>();
const searchText = defineModel<string>("searchText", {default: ""});
const searchAll = defineModel<boolean>("searchAll", {default: false});
const filtersVisible = defineModel<boolean>("filtersVisible", {default: false});
const pathFilter = defineModel<SheetPathFilter>("pathFilter", {default: "all"});
const diagnosticFilter = defineModel<SheetDiagFilter>("diagnosticFilter", {default: "all"});
const pendingFilter = defineModel<SheetPendingFilter>("pendingFilter", {default: "all"});
const renderLimit = defineModel<number>("renderLimit", {default: 80});
const bulkPropertyName = defineModel<string>("bulkPropertyName", {default: ""});
const bulkPropertyValue = defineModel<string>("bulkPropertyValue", {default: ""});
const subsetTitleBuffer = defineModel<string>("subsetTitleBuffer", {default: ""});
const emit = defineEmits<{
  selectAll: []; selectSubset: [id: string]; selectSheet: [id: string];
  toggleFilteredSelection: []; clearSelection: []; clearFilters: [];
  toggleSheet: [id: string]; deleteSheet: [sheet: Sheet];
  queueBulkSheetProperty: [];
  openOperation: [kind: OperationKind]; closeOperation: [];
  selectTemplateFile: []; selectSubsetTemplateFile: []; selectBaseTemplateFile: [];
  queueSubsetTitle: []; queueDeleteSubset: []; queueInsertSheet: []; queueInsertSubset: [];
}>();

const rangeTitle = computed(() => {
  const currentScope = props.scope;
  if (currentScope.kind !== "subset") return "全部图纸";
  return props.workspace.sheet_set.subsets.find((item) => item.id === currentScope.id)?.display_name ?? "全部图纸";
});
// 编辑子集表单目标子集（App.vue 在打开时按当前范围或首个子集选定）
const operationSubset = computed(() => props.workspace.sheet_set.subsets.find((item) => item.id === props.operationSubsetId) ?? null);
const hasAnyFilter = computed(() => Boolean(searchText.value.trim()) || pathFilter.value !== "all" || diagnosticFilter.value !== "all" || pendingFilter.value !== "all");
</script>
<template>
  <section class="sheets-view" role="tabpanel" id="panel-sheets" aria-label="图纸">
    <div class="sheets-workspace">
      <aside class="sheet-tree-pane" aria-label="图纸导航栏">
        <div class="tree-root">{{ workspace.sheet_set.name }}（{{ allTotal }} 张）</div>
        <SheetTree
          :workspace="workspace"
          :scope="scope"
          :focused-sheet-id="focusedSheetId"
          @select-all="$emit('selectAll')"
          @select-subset="$emit('selectSubset', $event)"
          @select-sheet="$emit('selectSheet', $event)"
        />
      </aside>
      <main class="sheets-main">
        <SheetToolbar
          :range-title="rangeTitle"
          :range-total="rangeTotal"
          :match-count="filteredRows.length"
          :visible-count="visibleRows.length"
          :selected-count="selectedIds.length"
          :hidden-selected-count="hiddenSelectedCount"
          :all-filtered-selected="allFilteredSelected"
          :can-select="filteredRows.length > 0"
          :sheet-property-names="sheetPropertyNames"
          :active-operation="activeOperation"
          v-model:search-text="searchText"
          v-model:search-all="searchAll"
          v-model:filters-visible="filtersVisible"
          v-model:path-filter="pathFilter"
          v-model:diagnostic-filter="diagnosticFilter"
          v-model:pending-filter="pendingFilter"
          v-model:bulk-property-name="bulkPropertyName"
          v-model:bulk-property-value="bulkPropertyValue"
          @clear-filters="$emit('clearFilters')"
          @toggle-filtered-selection="$emit('toggleFilteredSelection')"
          @clear-selection="$emit('clearSelection')"
          @queue-bulk-sheet-property="$emit('queueBulkSheetProperty')"
          @open-operation="$emit('openOperation', $event)"
        />

        <p v-if="pruneMessage" class="notice prune-notice" role="status">{{ pruneMessage }}</p>
        <p v-if="hiddenTarget" class="notice hidden-target-notice" role="status">
          <span>目标被筛选隐藏</span>
          <button type="button" @click="$emit('clearFilters')">清除筛选并定位</button>
        </p>

        <!-- 新增操作表单（任务 3 过渡实现，一次只出现一种，位于主表上方） -->
        <section v-if="activeOperation === 'rename'" class="operation-form" aria-label="编辑子集">
          <h3>编辑子集</h3>
          <template v-if="operationSubset">
            <div class="form-row">
              <label>当前子集标题<input v-model="subsetTitleBuffer"></label>
              <button type="button" @click="$emit('queueSubsetTitle')">加入标题变更</button>
              <button type="button" class="danger" @click="$emit('queueDeleteSubset')">删除整个子集</button>
            </div>
            <p class="derived">只读图号范围：{{ operationSubset.number_range || "—" }} · 显示名：{{ operationSubset.display_name }}</p>
          </template>
          <p v-else class="derived">请先在树中或全部范围内选择子集。</p>
          <button type="button" @click="$emit('closeOperation')">取消</button>
        </section>

        <section v-else-if="activeOperation === 'insert-sheet'" class="operation-form" aria-label="批量新增图纸">
          <fieldset><legend>批量新增图纸</legend><div class="form-grid">
            <label>目标子集<select v-model="insertSheetForm.subsetId"><option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option></select></label>
            <label>图纸序号<input v-model="insertSheetForm.sequence" inputmode="numeric"></label><label>图纸方向<select v-model="insertSheetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>新增图纸数量<input v-model="insertSheetForm.count" inputmode="numeric"></label>
            <label>模板来源<select v-model="insertSheetForm.sourceType"><option value="template_layout">DWG/DWT 模板布局</option><option value="existing_snapshot">已有布局</option></select></label><template v-if="insertSheetForm.sourceType === 'existing_snapshot'"><label>来源说明<span>来源为目标子集 DWG 的第一个非 Model 布局</span></label></template><template v-else><label>布局模板文件<button type="button" aria-label="选择模板文件" @click="$emit('selectTemplateFile')">选择模板文件</button><span v-if="insertSheetForm.sourceFile">{{ insertSheetForm.sourceFile }}</span></label><label>布局模板名称<span v-if="layoutLoading">正在读取布局…</span><template v-else-if="layoutError"><span class="error">{{ layoutError }}</span><input v-model="insertSheetForm.sourceLayout"></template><select v-else-if="layoutOptions.length && !layoutManual" v-model="insertSheetForm.sourceLayout"><option v-for="l in layoutOptions" :value="l">{{ l }}</option></select></label></template>
          </div><button type="button" @click="$emit('queueInsertSheet')">批量新增图纸</button> <button type="button" @click="$emit('closeOperation')">取消</button></fieldset>
        </section>

        <section v-else-if="activeOperation === 'insert-subset'" class="operation-form" aria-label="新建子集">
          <fieldset><legend>新建子集</legend><div class="form-grid"><label>子集序号<input v-model="insertSubsetForm.sequence" inputmode="numeric"></label><label>子集方向<select v-model="insertSubsetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>子集标题<input v-model="insertSubsetForm.title"></label><label>初始图纸数<input v-model="insertSubsetForm.initialSheetCount" inputmode="numeric"></label><label>基础模板文件<button type="button" aria-label="选择基础模板文件" @click="$emit('selectBaseTemplateFile')">选择基础模板文件</button><span v-if="insertSubsetForm.baseTemplateFile">{{ insertSubsetForm.baseTemplateFile }}</span></label><label>布局模板文件<button type="button" aria-label="选择布局模板文件" @click="$emit('selectSubsetTemplateFile')">选择布局模板文件</button><span v-if="insertSubsetForm.templateFile">{{ insertSubsetForm.templateFile }}</span></label><label>布局模板名称<span v-if="subsetLayoutLoading">正在读取布局…</span><template v-else-if="subsetLayoutError"><span class="error">{{ subsetLayoutError }}</span><input v-model="insertSubsetForm.templateLayout"></template><select v-else-if="subsetLayoutOptions.length && !subsetLayoutManual" v-model="insertSubsetForm.templateLayout"><option v-for="l in subsetLayoutOptions" :value="l">{{ l }}</option></select></label></div><button type="button" @click="$emit('queueInsertSubset')">新建子集</button> <button type="button" @click="$emit('closeOperation')">取消</button></fieldset>
        </section>

        <!-- 唯一业务表：空集/无结果显示原因与入口，不渲染无说明的空表头 -->
        <div v-if="allTotal === 0" class="empty-state" role="status">
          <p>图纸集为空</p>
          <button type="button" @click="$emit('openOperation', 'insert-subset')">创建首个子集</button>
        </div>
        <div v-else-if="scopeTotal === 0" class="empty-state" role="status">
          <p>当前范围无图纸</p>
          <button type="button" @click="$emit('selectAll')">查看全部图纸</button>
        </div>
        <div v-else-if="filteredRows.length === 0" class="empty-state" role="status">
          <p>无匹配图纸</p>
          <button v-if="hasAnyFilter" type="button" @click="$emit('clearFilters')">清除筛选</button>
        </div>
        <template v-else>
          <SheetTable
            :rows="visibleRows"
            :selected-ids="selectedIds"
            :pending-ids="pendingSheetIds"
            :diagnostic-ids="diagnosticObjectIds"
            :focused-sheet-id="focusedSheetId"
            @toggle="$emit('toggleSheet', $event)"
            @open-subset="$emit('selectSubset', $event)"
            @delete="$emit('deleteSheet', $event)"
          />
          <button v-if="visibleRows.length < filteredRows.length" type="button" class="load-more" @click="renderLimit += 80">继续加载（尚余 {{ filteredRows.length - visibleRows.length }}）</button>
        </template>
      </main>
    </div>
  </section>
</template>
<style scoped>
.sheets-view{display:block}
.sheets-workspace{display:flex;align-items:stretch;gap:var(--space-4);background:var(--color-bg-surface);border-radius:var(--radius-md,8px);padding:var(--space-4)}
.sheet-tree-pane{flex:0 0 240px;min-width:0;display:flex;flex-direction:column;gap:var(--space-3);border-right:1px solid var(--color-border,var(--color-bg-surface-2));padding-right:var(--space-3);max-height:calc(100vh - 160px);overflow:auto}
.tree-root{font-size:14px;font-weight:600;color:var(--color-text-primary);padding:0 var(--space-2)}
.sheets-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:var(--space-4)}
.notice{padding:var(--space-2) var(--space-3);border-radius:var(--radius-md,8px);font-size:13px;margin:0}
.prune-notice{background:var(--color-accent-soft,var(--color-bg-surface-2))}
.hidden-target-notice{background:var(--color-warning-soft,transparent);border:1px solid var(--color-warning,#b7791f)}
.operation-form{border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);padding:var(--space-4)}
.operation-form h3{margin:0 0 var(--space-3);font-size:15px}
.form-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.form-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--space-3)}
.derived{color:var(--color-text-secondary);font-size:13px}
.empty-state{padding:var(--space-5);text-align:center;color:var(--color-text-secondary);border:1px dashed var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px)}
.load-more{margin:0 auto}
</style>
