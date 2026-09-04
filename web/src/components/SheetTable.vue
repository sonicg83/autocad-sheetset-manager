<script setup lang="ts">
// 唯一图纸主表（PLAN-DM-015 任务 3，SPEC-DM-009 §5）：固定选择/图号/标题，状态列阻断与待变更可并存。
// 操作列提供「删除」入口；定位行高亮；列配置由任务 4 提供。
import {nextTick, ref, watch} from "vue";
import type {Sheet} from "../api/contracts";
import type {SheetRow} from "../composables/useSheetsWorkspace";

const props = defineProps<{
  rows: SheetRow[];
  selectedIds: string[];
  pendingIds: Set<string>;
  diagnosticIds: Set<string>;
  focusedSheetId: string | null;
}>();
const emit = defineEmits<{
  toggle: [sheetId: string];
  openSubset: [subsetId: string];
  delete: [sheet: Sheet];
}>();

const windowEl = ref<HTMLElement | null>(null);
// 定位：目标行滚动到可见区域
watch(() => props.focusedSheetId, async (id) => {
  if (!id) return;
  await nextTick();
  windowEl.value?.querySelector<HTMLElement>(`[data-sheet-id="${id}"]`)?.scrollIntoView({block: "nearest"});
});
</script>
<template>
  <div ref="windowEl" class="sheet-table-window" tabindex="0" aria-label="过滤后的图纸表格">
    <table aria-label="图纸表格">
      <thead><tr><th>选择</th><th>子集</th><th>图号</th><th>标题</th><th>DWG</th><th>布局</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.sheet.id" :data-sheet-id="row.sheet.id" :class="{focused: row.sheet.id === focusedSheetId}">
          <td><input type="checkbox" :aria-label="`选择图纸 ${row.sheet.number}`" :checked="selectedIds.includes(row.sheet.id)" @change="$emit('toggle', row.sheet.id)"></td>
          <td><button class="link-button" @click="$emit('openSubset', row.subset.id)">{{ row.subset.display_name }}</button></td>
          <td>{{ row.sheet.number }}</td>
          <td>{{ row.sheet.title }}</td>
          <td><span>{{ row.sheet.layout.file_name }}</span><small>{{ row.sheet.layout.relative_file_name }} · {{ row.sheet.layout.resolved_path ?? "未解析" }}</small></td>
          <td>{{ row.sheet.layout.layout_name }}</td>
          <td>
            <span v-if="pendingIds.has(row.sheet.id)" class="status pending">待变更</span>
            <span v-if="diagnosticIds.has(row.sheet.id)" class="status blocking">阻断</span>
            <span v-if="!pendingIds.has(row.sheet.id) && !diagnosticIds.has(row.sheet.id)">正常</span>
          </td>
          <td><button class="danger-link" @click="$emit('delete', row.sheet)">删除</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.sheet-table-window{overflow:auto;max-height:calc(100vh - 300px);border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);outline:none}
.sheet-table-window:focus-visible{outline:2px solid var(--color-focus,var(--color-accent));outline-offset:-2px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--color-border,var(--color-bg-surface-2));white-space:nowrap;vertical-align:top}
th{position:sticky;top:0;background:var(--color-bg-surface-2,var(--color-bg-surface));color:var(--color-text-secondary);font-weight:600;z-index:1}
tbody tr.focused{background:var(--color-accent-soft,var(--color-bg-surface-2))}
td small{display:block;color:var(--color-text-secondary);font-size:12px}
.status{padding:1px 6px;border-radius:10px;font-size:12px;display:inline-block;margin-right:4px}
.status.pending{background:var(--color-warning-soft,transparent);color:var(--color-warning,#b7791f)}
.status.blocking{background:var(--color-danger-soft,transparent);color:var(--color-danger,#c53030)}
.danger-link{color:var(--color-danger,#c53030);background:none;border:none;cursor:pointer;font-size:13px;padding:0}
.danger-link:hover{text-decoration:underline}
</style>
