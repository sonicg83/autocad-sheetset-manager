<script setup lang="ts">
// 标签① 图纸：左树右唯一主表工作区（PLAN-DM-015 任务 3，SPEC-DM-009 §3/§4/§6.3）。
// 范围/搜索/筛选/勾选集合由 App.vue 的 useSheetsWorkspace 持有（跨主标签保留），本组件只做呈现与转发。
// 三类操作表单（编辑子集/新增图纸/新建子集）由 SheetOperationForm 渲染于主表上方，
// 与 SheetPropertyEditor 共用唯一编辑上下文（任务 5/6），一次只出现一种。
import {computed} from "vue";
import type {Placement, Sheet, Workspace} from "../api/contracts";
import type {EditContext, SheetScope} from "../features/sheets/types";
import type {BuiltinPrefField, SheetColumn, SheetColumnOption} from "../composables/useSheetColumns";
import type {SheetDiagFilter, SheetPathFilter, SheetPendingFilter, SheetRow} from "../composables/useSheetsWorkspace";
import type {OperationContext} from "../composables/useSheetEditor";
import SheetTree from "../components/sheets/SheetTree.vue";
import SheetToolbar, {type OperationKind} from "../components/sheets/SheetToolbar.vue";
import SheetOperationForm from "../components/sheets/SheetOperationForm.vue";
import SheetTable from "../components/SheetTable.vue";
import SheetPropertyEditor from "../components/sheets/SheetPropertyEditor.vue";

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
  visibleColumns: SheetColumn[];
  columnOptions: SheetColumnOption[];
  newPropertyCount: number;
  columnSaveError: string;
  editContext: EditContext;
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
const bulkMode = defineModel<"set" | "clear">("bulkMode", {default: "set"});
const emit = defineEmits<{
  selectAll: []; selectSubset: [id: string]; selectSheet: [id: string];
  toggleFilteredSelection: []; clearSelection: []; clearFilters: [];
  toggleSheet: [id: string]; editSheet: [sheet: Sheet]; deleteSheet: [sheet: Sheet];
  queueBulkSheetProperty: [];
  editorSetValue: [name: string, value: string];
  editorSetPage: [page: number];
  editorSetSearch: [query: string];
  editorSubmit: [];
  editorCancel: [];
  editorJumpError: [name: string];
  openOperation: [kind: OperationKind];
  operationSubmit: []; operationCancel: []; operationDeleteSubset: [];
  selectTemplateFile: []; selectSubsetTemplateFile: []; selectBaseTemplateFile: [];
  toggleBuiltin: [field: BuiltinPrefField, value: boolean];
  toggleProperty: [name: string, value: boolean];
  resetColumns: [];
  openDiagnostics: [];
}>();
// 新增操作表单（一次只出现一种）由唯一编辑上下文驱动；无操作表单时不渲染
const operationContext = computed<OperationContext | null>(() => {
  const ctx = props.editContext;
  return ctx && (ctx.kind === "rename" || ctx.kind === "insert-sheet" || ctx.kind === "insert-subset") ? ctx : null;
});
const rangeTitle = computed(() => {
  const currentScope = props.scope;
  if (currentScope.kind !== "subset") return "全部图纸";
  return props.workspace.sheet_set.subsets.find((item) => item.id === currentScope.id)?.display_name ?? "全部图纸";
});
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
          :column-options="columnOptions"
          :column-save-error="columnSaveError"
          :new-property-count="newPropertyCount"
          v-model:search-text="searchText"
          v-model:search-all="searchAll"
          v-model:filters-visible="filtersVisible"
          v-model:path-filter="pathFilter"
          v-model:diagnostic-filter="diagnosticFilter"
          v-model:pending-filter="pendingFilter"
          v-model:bulk-property-name="bulkPropertyName"
          v-model:bulk-property-value="bulkPropertyValue"
          v-model:bulk-mode="bulkMode"
          @clear-filters="$emit('clearFilters')"
          @toggle-filtered-selection="$emit('toggleFilteredSelection')"
          @clear-selection="$emit('clearSelection')"
          @queue-bulk-sheet-property="$emit('queueBulkSheetProperty')"
          @open-operation="$emit('openOperation', $event)"
          @toggle-builtin="(field, value) => $emit('toggleBuiltin', field, value)"
          @toggle-property="(name, value) => $emit('toggleProperty', name, value)"
          @reset-columns="$emit('resetColumns')"
        />

        <p v-if="pruneMessage" class="notice prune-notice" role="status">{{ pruneMessage }}</p>
        <p v-if="hiddenTarget" class="notice hidden-target-notice" role="status">
          <span>目标被筛选隐藏</span>
          <button type="button" @click="$emit('clearFilters')">清除筛选并定位</button>
        </p>

        <!-- 三类操作表单（任务 6，SPEC-DM-009 §6.3）：位于主表上方，一次只出现一种 -->
        <SheetOperationForm
          v-if="operationContext"
          :context="operationContext"
          :workspace="workspace"
          @submit="$emit('operationSubmit')"
          @cancel="$emit('operationCancel')"
          @delete-subset="$emit('operationDeleteSubset')"
          @select-template-file="$emit('selectTemplateFile')"
          @select-subset-template-file="$emit('selectSubsetTemplateFile')"
          @select-base-template-file="$emit('selectBaseTemplateFile')"
        />

        <!-- 分页属性编辑（任务 5，SPEC-DM-009 §6.1）：唯一活动编辑上下文下的局部编辑区，一次只展开一张图纸 -->
        <SheetPropertyEditor
          v-if="editContext?.kind === 'sheet'"
          :context="editContext"
          @set-value="(name, value) => $emit('editorSetValue', name, value)"
          @set-page="(p) => $emit('editorSetPage', p)"
          @set-search="(q) => $emit('editorSetSearch', q)"
          @submit="$emit('editorSubmit')"
          @cancel="$emit('editorCancel')"
          @jump-error="(name) => $emit('editorJumpError', name)"
        />

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
            :columns="visibleColumns"
            @toggle="$emit('toggleSheet', $event)"
            @open-subset="$emit('selectSubset', $event)"
            @edit="$emit('editSheet', $event)"
            @delete="$emit('deleteSheet', $event)"
            @open-diagnostics="$emit('openDiagnostics')"
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
.empty-state{padding:var(--space-5);text-align:center;color:var(--color-text-secondary);border:1px dashed var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px)}
.load-more{margin:0 auto}
</style>
