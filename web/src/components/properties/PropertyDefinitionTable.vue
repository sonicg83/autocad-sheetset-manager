<!-- 属性字段定义表（PLAN-DM-016 任务 4，SPEC-DM-010 §4.1、P-02/P-14）。
     六条分页的展示表：列宽与 min-width 确定，容器只承担横向滚动（无第二个纵向滚动条）；
     弱化表头背景 + 语义分隔线 + sticky header；横向溢出时冻结右侧「操作」列并补不透明语义背景与
     分隔阴影，无溢出时保持普通列、不制造多余阴影；默认值最多两行摘要并提供键盘可达的完整值读取入口；
     删除为低强调危险文字按钮，accessible name 含作用域与名称。行 key 为 `${type}:${name.toLocaleLowerCase()}`。
     过滤与分页派生在 PropertyDefinitionPanel（纯函数来自 features/properties/model），本组件只展示。 -->
<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from "vue";
import type {PropertyDefinition} from "../../api/contracts";
import {definitionKey} from "../../features/properties/model";

const props = defineProps<{
  rows: PropertyDefinition[];
  page: number;
  lastPage: number;
  matchedCount: number;
  totalCount: number;
}>();
const emit = defineEmits<{
  changePage: [page: number];
  clearFilter: [];
  deleteDefinition: [definition: PropertyDefinition];
}>();

function scopeLabel(definition: PropertyDefinition): string {
  return definition.type === "sheetset" ? "图纸集" : "图纸";
}

// —— 列宽确定（table-layout:fixed + min-width），同图纸主表的模式 ——
const COLUMNS = [
  {key: "name", label: "字段名", width: 200},
  {key: "scope", label: "作用域", width: 88},
  {key: "default", label: "默认值", width: 320},
  {key: "actions", label: "操作", width: 140},
] as const;
const tableMinWidth = computed(() => COLUMNS.reduce((sum, column) => sum + column.width, 0));

// —— 长默认值：两行摘要 + 键盘可达的展开/收起（同一行内完整读取，不另开滚动容器）——
const LONG_DEFAULT_LIMIT = 30;
const expandedKey = ref<string | null>(null);
function isLong(definition: PropertyDefinition): boolean {
  return (definition.default_value ?? "").length > LONG_DEFAULT_LIMIT;
}
function toggleExpand(definition: PropertyDefinition) {
  const key = definitionKey(definition);
  expandedKey.value = expandedKey.value === key ? null : key;
}

// —— 横向溢出检测：列宽之和超过容器宽度时冻结右侧操作列（同图纸主表 sticky-actions 模式）——
const windowEl = ref<HTMLElement | null>(null);
const availableWidth = ref(0);
const stickyActions = computed(() => availableWidth.value > 0 && tableMinWidth.value > availableWidth.value + 1);
let resizeObserver: ResizeObserver | undefined;
onMounted(() => {
  resizeObserver = new ResizeObserver(() => { availableWidth.value = windowEl.value?.clientWidth ?? 0; });
  if (windowEl.value) resizeObserver.observe(windowEl.value);
});
onBeforeUnmount(() => resizeObserver?.disconnect());
</script>
<template>
  <div class="definition-table">
    <div
      ref="windowEl"
      class="table-window"
      :class="{'sticky-actions': stickyActions}"
      tabindex="0"
      aria-label="属性字段定义表格"
    >
      <table :style="{minWidth: `${tableMinWidth}px`}">
        <colgroup>
          <col v-for="column in COLUMNS" :key="column.key" :style="{width: `${column.width}px`}">
        </colgroup>
        <thead>
          <tr>
            <th v-for="column in COLUMNS" :key="column.key" :class="`col-${column.key}`" scope="col">{{ column.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="definition in rows" :key="definitionKey(definition)">
            <td class="col-name">{{ definition.name }}</td>
            <td class="col-scope">{{ scopeLabel(definition) }}</td>
            <td class="col-default">
              <span
                v-if="definition.default_value"
                class="default-text"
                :class="{expanded: expandedKey === definitionKey(definition)}"
              >{{ definition.default_value }}</span>
              <span v-else class="empty-value">（空）</span>
              <button
                v-if="isLong(definition)"
                type="button"
                class="text-action"
                :aria-expanded="expandedKey === definitionKey(definition)"
                :aria-label="`${expandedKey === definitionKey(definition) ? '收起' : '展开'}默认值 ${scopeLabel(definition)} ${definition.name}`"
                @click="toggleExpand(definition)"
              >{{ expandedKey === definitionKey(definition) ? "收起" : "展开" }}</button>
            </td>
            <td class="col-actions">
              <button
                type="button"
                class="danger-text"
                :aria-label="`删除 ${scopeLabel(definition)} 属性 ${definition.name}`"
                @click="emit('deleteDefinition', definition)"
              >删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="totalCount === 0" class="empty">没有属性定义；使用「新增字段」创建第一个字段。</p>
    <p v-else-if="matchedCount === 0" class="empty">没有匹配的字段定义。<button type="button" class="text-action" @click="emit('clearFilter')">清除查询</button></p>
    <div class="table-foot">
      <span class="foot-info">匹配 {{ matchedCount }} 项 · 第 {{ page }} / {{ lastPage }} 页</span>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="emit('changePage', page - 1)">上一页</button>
        <button type="button" :disabled="page >= lastPage" @click="emit('changePage', page + 1)">下一页</button>
      </div>
    </div>
  </div>
</template>
<style scoped>
/* 容器只承担横向滚动：分页限制行数，内容不产生第二个纵向滚动条。 */
.table-window{overflow-x:auto;border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);outline:none}
.table-window:focus-visible{outline:2px solid var(--color-focus);outline-offset:-2px}
table{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;font-size:13px}
th,td{box-sizing:border-box;padding:10px 8px;border-bottom:1px solid var(--color-border-subtle);white-space:nowrap;text-align:left;vertical-align:middle;height:44px}
/* 弱化表头背景 + 语义分隔线 + sticky header */
th{position:sticky;top:0;z-index:2;background:var(--color-bg-muted);color:var(--color-text-secondary);font-weight:600}
th:not(:first-child),td:not(:first-child){border-left:1px solid var(--color-border-subtle)}
tbody tr{background:var(--color-bg-surface)}
tbody tr td{background:inherit}
tbody tr:hover,tbody tr:focus-within{background:var(--color-bg-muted)}
/* 默认值最多两行摘要；展开后完整读取，不截断提交值 */
td.col-default{white-space:normal}
.default-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-wrap;word-break:break-word;max-width:100%}
.default-text.expanded{display:block;-webkit-line-clamp:unset;overflow:visible}
.empty-value{color:var(--color-text-muted)}
/* 低强调危险文字按钮与纯文字操作：沿用属性页受控按钮基线，仅调整文字颜色 */
.danger-text{color:var(--color-danger)}
.danger-text:hover:not(:disabled){background:var(--color-danger-bg)}
.text-action{color:var(--color-accent)}
/* 横向溢出时冻结右侧操作列：行背景本身不透明，固定列在各交互状态下保持一致；无溢出时无阴影 */
.sticky-actions th.col-actions,.sticky-actions td.col-actions{position:sticky;right:0;z-index:2;box-shadow:-2px 0 0 var(--color-border-subtle)}
.sticky-actions th.col-actions{background:var(--color-bg-muted)}
/* 空态与页脚 */
.empty{margin:0;padding:var(--space-4);color:var(--color-text-secondary);text-align:center;border:1px dashed var(--color-border-subtle);border-top:0;border-radius:0 0 var(--radius-md) var(--radius-md)}
.table-foot{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;margin-top:var(--space-3)}
.foot-info{color:var(--color-text-muted);font-size:12px}
.pager{display:flex;gap:var(--space-2);margin-left:auto}
</style>
