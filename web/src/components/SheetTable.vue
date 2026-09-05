<script setup lang="ts">
// 唯一图纸主表（PLAN-DM-015 任务 3/4，SPEC-DM-009 §5）。
// 列由 useSheetColumns 的 visibleColumns 驱动：固定选择/图号/标题/状态/操作与可选子集/文件名/布局/属性列。
// 标题最多两行、文件名等完整值键盘聚焦读取；状态列阻断/待变更可并存，异常提供「诊断」跳转。
// 宽度不足仅表格内部横向滚动，不自动隐藏已配置列。
import {computed, nextTick, onMounted, onBeforeUnmount, ref, watch} from "vue";
import type {Sheet} from "../api/contracts";
import {columnWidth, type SheetColumn} from "../composables/useSheetColumns";
import type {SheetRow} from "../composables/useSheetsWorkspace";
import type {PropertyEditContext} from "../features/sheets/types";
import SheetPropertyEditor from "./sheets/SheetPropertyEditor.vue";

const props = defineProps<{
  rows: SheetRow[];
  selectedIds: string[];
  pendingIds: Set<string>;
  diagnosticIds: Set<string>;
  focusedSheetId: string | null;
  columns: SheetColumn[];
  allFilteredSelected: boolean;
  filteredSelectedCount: number;
  canSelect: boolean;
  editContext: PropertyEditContext | null;
}>();
const emit = defineEmits<{
  toggle: [sheetId: string];
  toggleFilteredSelection: [];
  openSubset: [subsetId: string];
  edit: [sheet: Sheet];
  delete: [sheet: Sheet];
  openDiagnostics: [];
  editorSetValue: [name: string, value: string];
  editorSetPage: [page: number];
  editorSetSearch: [query: string];
  editorSubmit: [];
  editorCancel: [];
  editorJumpError: [name: string];
}>();

const windowEl = ref<HTMLElement | null>(null);
const availableWidth = ref(0);
const tableMinWidth = computed(() => props.columns.reduce((sum, column) => sum + columnWidth(column), 0));
// 横向溢出时固定右侧操作列，使编辑与删除入口始终可达。
const stickyActions = computed(() => availableWidth.value > 0 && tableMinWidth.value > availableWidth.value + 1);
let resizeObserver: ResizeObserver | undefined;
onMounted(() => {
  resizeObserver = new ResizeObserver(() => { availableWidth.value = windowEl.value?.clientWidth ?? 0; });
  if (windowEl.value) resizeObserver.observe(windowEl.value);
});
onBeforeUnmount(() => resizeObserver?.disconnect());
// 定位：目标行滚动到可见区域
watch(() => props.focusedSheetId, async (id) => {
  if (!id) return;
  await nextTick();
  windowEl.value?.querySelector<HTMLElement>(`[data-sheet-id="${id}"]`)?.scrollIntoView({block: "nearest"});
});

function cellClass(col: SheetColumn): string {
  return col.kind === "sheet" ? "col-prop" : `col-${col.key.slice("builtin:".length)}`;
}
// custom_properties 按定义的原始大小写键控（服务端序列化原样透传），取值用原名而非规范化 PropertyKey
function propertyValue(row: SheetRow, col: SheetColumn): string {
  return col.name ? (row.sheet.custom_properties[col.name] ?? "") : "";
}
// file_name 兼容服务端返回的 Windows/POSIX 路径；主表只展示登记文件名部分，完整路径留给诊断区。
function displayFileName(value: string): string {
  const fileName = value.replace(/\\/g, "/").split("/").filter(Boolean).at(-1);
  return fileName || "—";
}
</script>
<template>
  <div ref="windowEl" class="sheet-table-window" :class="{'sticky-actions': stickyActions}" tabindex="0" aria-label="过滤后的图纸表格">
    <table aria-label="图纸表格" :style="{width: `${tableMinWidth}px`, minWidth: `${tableMinWidth}px`}">
      <colgroup><col v-for="col in columns" :key="col.key" :style="{width: `${columnWidth(col)}px`}"></colgroup>
      <thead><tr><th v-for="col in columns" :key="col.key" :class="cellClass(col)" :title="col.label || undefined">
        <input
          v-if="col.key === 'builtin:select'"
          type="checkbox"
          aria-label="全选当前结果"
          :checked="allFilteredSelected"
          :indeterminate="filteredSelectedCount > 0 && !allFilteredSelected"
          :disabled="!canSelect"
          @change="$emit('toggleFilteredSelection')"
        >
        <template v-else>{{ col.label }}</template>
      </th></tr></thead>
      <tbody>
        <template v-for="row in rows" :key="row.sheet.id">
        <tr :data-sheet-id="row.sheet.id" :class="{focused: row.sheet.id === focusedSheetId, selected: selectedIds.includes(row.sheet.id)}">
          <td v-for="col in columns" :key="col.key" :class="cellClass(col)">
            <template v-if="col.key === 'builtin:select'">
              <input type="checkbox" :aria-label="`选择图纸 ${row.sheet.number}`" :checked="selectedIds.includes(row.sheet.id)" @change="$emit('toggle', row.sheet.id)">
            </template>
            <template v-else-if="col.key === 'builtin:number'"><span class="ellipsis mono" tabindex="0" :title="row.sheet.number">{{ row.sheet.number }}</span></template>
            <template v-else-if="col.key === 'builtin:title'"><span class="title-text multiline-text" tabindex="0" :title="row.sheet.title">{{ row.sheet.title || "—" }}</span></template>
            <template v-else-if="col.key === 'builtin:subset'"><button class="link-button multiline-text" tabindex="0" :title="row.subset.display_name" @click="$emit('openSubset', row.subset.id)">{{ row.subset.display_name }}</button></template>
            <template v-else-if="col.key === 'builtin:file'"><span class="multiline-text mono" tabindex="0" :title="displayFileName(row.sheet.layout.file_name)">{{ displayFileName(row.sheet.layout.file_name) }}</span></template>
            <template v-else-if="col.key === 'builtin:layout'"><span class="multiline-text mono" tabindex="0" :title="row.sheet.layout.layout_name">{{ row.sheet.layout.layout_name || "—" }}</span></template>
            <template v-else-if="col.key === 'builtin:status'">
              <span v-if="pendingIds.has(row.sheet.id)" class="status pending">待变更</span>
              <span v-if="diagnosticIds.has(row.sheet.id)" class="status blocking">阻断</span>
              <span v-if="!pendingIds.has(row.sheet.id) && !diagnosticIds.has(row.sheet.id)">正常</span>
              <button v-if="diagnosticIds.has(row.sheet.id)" type="button" class="diag-link" @click="$emit('openDiagnostics')">诊断</button>
            </template>
            <template v-else-if="col.kind === 'sheet'"><span class="multiline-text" tabindex="0" :title="propertyValue(row, col)">{{ propertyValue(row, col) || "—" }}</span></template>
            <template v-else-if="col.key === 'builtin:actions'">
              <button type="button" class="link-button" @click="$emit('edit', row.sheet)">编辑属性</button>
              <button type="button" class="danger-link" @click="$emit('delete', row.sheet)">删除</button>
            </template>
          </td>
        </tr>
        <tr v-if="editContext?.objectId === row.sheet.id" class="sheet-editor-row">
          <td :colspan="columns.length">
            <SheetPropertyEditor
              :context="editContext"
              @set-value="(name, value) => emit('editorSetValue', name, value)"
              @set-page="(page) => emit('editorSetPage', page)"
              @set-search="(query) => emit('editorSetSearch', query)"
              @submit="emit('editorSubmit')"
              @cancel="emit('editorCancel')"
              @jump-error="(name) => emit('editorJumpError', name)"
            />
          </td>
        </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.sheet-table-window{container-type:inline-size;flex:1;min-height:130px;max-height:none;overflow:auto;border:1px solid var(--color-border-subtle);border-radius:var(--radius-md,8px);outline:none}
.sheet-table-window:focus-visible{outline:2px solid var(--color-focus);outline-offset:-2px}
table{table-layout:fixed;border-collapse:separate;border-spacing:0;font-size:13px}
th,td{box-sizing:border-box;text-align:left;padding:10px 8px;border-bottom:1px solid var(--color-border-subtle);white-space:nowrap;vertical-align:middle;height:44px;line-height:20px}
th{overflow:hidden;text-overflow:ellipsis}
th{position:sticky;top:0;background:var(--color-bg-muted);color:var(--color-text-secondary);font-weight:600;z-index:2}
tbody tr{background:var(--color-bg-surface)}
tbody tr:hover,tbody tr:focus-within{background:var(--color-bg-muted)}
tbody tr.focused,tbody tr.selected{background:var(--color-info-bg)}
/* 左侧识别列固定；出现横向滚动时，操作列固定在右侧。 */
th.col-select,td.col-select{position:sticky;left:0;z-index:2}
th.col-number,td.col-number{position:sticky;left:40px;z-index:2;box-shadow:2px 0 0 var(--color-border-subtle)}
.sticky-actions th.col-actions,.sticky-actions td.col-actions{position:sticky;right:0;z-index:2;box-shadow:-2px 0 0 var(--color-border-subtle)}
td.col-actions .link-button{margin-right:10px}
th.col-select,th.col-number,th.col-actions{background:var(--color-bg-muted);z-index:3}
/* 全部单元格继承不透明行背景，固定列在各交互状态下保持一致。 */
tbody tr td{background:inherit}
/* 内容字段最多两行；完整值可通过 title 与键盘焦点读取。 */
.multiline-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:normal;max-width:100%;word-break:break-word;text-align:left}
.title-text{max-width:280px}
.multiline-text:focus-visible,.ellipsis:focus-visible{outline:2px solid var(--color-focus);outline-offset:1px}
.ellipsis{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.col-status{white-space:normal}
.status{padding:1px 5px;border-radius:10px;font-size:12px;display:inline-block;margin:1px 2px 1px 0;white-space:nowrap}
.status.pending{background:var(--color-warning-bg);color:var(--color-warning)}
.status.blocking{background:var(--color-danger-bg);color:var(--color-danger)}
.danger-link{color:var(--color-danger);background:none;border:none;cursor:pointer;font-size:13px;padding:0}
.danger-link:hover{text-decoration:underline}
.diag-link{color:var(--color-accent);background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin-left:4px;text-decoration:underline}
.link-button{color:var(--color-accent);background:none;border:none;cursor:pointer;font-size:13px;padding:0;text-decoration:underline}
.sheet-editor-row,.sheet-editor-row:hover,.sheet-editor-row:focus-within{background:var(--color-info-bg)}
.sheet-editor-row>td{position:static!important;height:auto;padding:0;border-bottom:1px solid var(--color-border-strong);white-space:normal;box-shadow:none!important;background:inherit}
</style>
