<script setup lang="ts">
// 唯一图纸主表（PLAN-DM-015 任务 3/4，SPEC-DM-009 §5）。
// 列由 useSheetColumns 的 visibleColumns 驱动：固定选择/图号/标题/状态/操作与可选子集/文件名/布局/属性列。
// 标题最多两行、文件名等完整值键盘聚焦读取；状态列阻断/待变更可并存，异常提供「诊断」跳转。
// 宽度不足仅表格内部横向滚动，不自动隐藏已配置列。
import {nextTick, ref, watch} from "vue";
import type {Sheet} from "../api/contracts";
import type {SheetColumn} from "../composables/useSheetColumns";
import type {SheetRow} from "../composables/useSheetsWorkspace";

const props = defineProps<{
  rows: SheetRow[];
  selectedIds: string[];
  pendingIds: Set<string>;
  diagnosticIds: Set<string>;
  focusedSheetId: string | null;
  columns: SheetColumn[];
}>();
const emit = defineEmits<{
  toggle: [sheetId: string];
  openSubset: [subsetId: string];
  edit: [sheet: Sheet];
  delete: [sheet: Sheet];
  openDiagnostics: [];
}>();

const windowEl = ref<HTMLElement | null>(null);
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
  <div ref="windowEl" class="sheet-table-window" tabindex="0" aria-label="过滤后的图纸表格">
    <table aria-label="图纸表格">
      <thead><tr><th v-for="col in columns" :key="col.key" :class="cellClass(col)">{{ col.label }}</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.sheet.id" :data-sheet-id="row.sheet.id" :class="{focused: row.sheet.id === focusedSheetId}">
          <td v-for="col in columns" :key="col.key" :class="cellClass(col)">
            <template v-if="col.key === 'builtin:select'">
              <input type="checkbox" :aria-label="`选择图纸 ${row.sheet.number}`" :checked="selectedIds.includes(row.sheet.id)" @change="$emit('toggle', row.sheet.id)">
            </template>
            <template v-else-if="col.key === 'builtin:number'"><span class="mono">{{ row.sheet.number }}</span></template>
            <template v-else-if="col.key === 'builtin:title'"><span class="title-text" tabindex="0" :title="row.sheet.title">{{ row.sheet.title || "—" }}</span></template>
            <template v-else-if="col.key === 'builtin:subset'"><button class="link-button" @click="$emit('openSubset', row.subset.id)">{{ row.subset.display_name }}</button></template>
            <template v-else-if="col.key === 'builtin:file'"><span class="ellipsis mono" tabindex="0" :title="displayFileName(row.sheet.layout.file_name)">{{ displayFileName(row.sheet.layout.file_name) }}</span></template>
            <template v-else-if="col.key === 'builtin:layout'"><span class="mono" tabindex="0" :title="row.sheet.layout.layout_name">{{ row.sheet.layout.layout_name }}</span></template>
            <template v-else-if="col.key === 'builtin:status'">
              <span v-if="pendingIds.has(row.sheet.id)" class="status pending">待变更</span>
              <span v-if="diagnosticIds.has(row.sheet.id)" class="status blocking">阻断</span>
              <span v-if="!pendingIds.has(row.sheet.id) && !diagnosticIds.has(row.sheet.id)">正常</span>
              <button v-if="diagnosticIds.has(row.sheet.id)" type="button" class="diag-link" @click="$emit('openDiagnostics')">诊断</button>
            </template>
            <template v-else-if="col.kind === 'sheet'"><span class="ellipsis" tabindex="0" :title="propertyValue(row, col)">{{ propertyValue(row, col) || "—" }}</span></template>
            <template v-else-if="col.key === 'builtin:actions'">
              <button type="button" class="link-button" @click="$emit('edit', row.sheet)">编辑属性</button>
              <button type="button" class="danger-link" @click="$emit('delete', row.sheet)">删除</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.sheet-table-window{flex:1;min-height:130px;max-height:none;overflow:auto;border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);outline:none}
.sheet-table-window:focus-visible{outline:2px solid var(--color-focus,var(--color-accent));outline-offset:-2px}
table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:13px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--color-border,var(--color-bg-surface-2));white-space:nowrap;vertical-align:top}
th{position:sticky;top:0;background:var(--color-bg-surface-2,var(--color-bg-surface));color:var(--color-text-secondary);font-weight:600;z-index:2}
tbody tr.focused{background:var(--color-accent-soft,var(--color-bg-surface-2))}
/* 固定列横向吸顶：选择/图号左侧、操作右侧，不随内部滚动隐藏 */
th.col-select,td.col-select{position:sticky;left:0;width:40px;min-width:40px;z-index:2;background:var(--color-bg-surface)}
th.col-number,td.col-number{position:sticky;left:40px;min-width:72px;z-index:2;background:var(--color-bg-surface)}
th.col-actions,td.col-actions{position:sticky;right:0;width:150px;min-width:150px;z-index:2;background:var(--color-bg-surface)}
th.col-title,td.col-title{min-width:180px}
th.col-subset,td.col-subset{min-width:200px}
th.col-file,td.col-file{min-width:240px}
td.col-actions .link-button{margin-right:10px}
th.col-select,th.col-number,th.col-actions{background:var(--color-bg-surface-2,var(--color-bg-surface));z-index:3}
tbody tr.focused td.col-select,tbody tr.focused td.col-number,tbody tr.focused td.col-actions{background:var(--color-accent-soft,var(--color-bg-surface-2))}
/* 标题最多两行；完整值悬停/键盘聚焦可读，不压缩焦点轮廓 */
.title-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:normal;max-width:280px;word-break:break-word}
.title-text:focus-visible,.ellipsis:focus-visible{outline:2px solid var(--color-focus,var(--color-accent));outline-offset:1px}
.ellipsis{display:inline-block;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.status{padding:1px 6px;border-radius:10px;font-size:12px;display:inline-block;margin-right:4px}
.status.pending{background:var(--color-warning-soft,transparent);color:var(--color-warning,#b7791f)}
.status.blocking{background:var(--color-danger-soft,transparent);color:var(--color-danger,#c53030)}
.danger-link{color:var(--color-danger,#c53030);background:none;border:none;cursor:pointer;font-size:13px;padding:0}
.danger-link:hover{text-decoration:underline}
.diag-link{color:var(--color-accent,var(--color-text-secondary));background:none;border:none;cursor:pointer;font-size:12px;padding:0;margin-left:4px;text-decoration:underline}
.link-button{color:var(--color-accent,var(--color-text-secondary));background:none;border:none;cursor:pointer;font-size:13px;padding:0;text-decoration:underline}
</style>
