<!-- 属性字段定义表（PLAN-DM-016 任务 4，SPEC-DM-010 §4.1、P-02/P-14）。
     六条分页的展示表：列宽与 min-width 确定，容器只承担横向滚动（无第二个纵向滚动条）；
     弱化表头背景 + 语义分隔线 + sticky header；横向溢出时冻结右侧「操作」列并补不透明语义背景与
     分隔阴影，无溢出时保持普通列、不制造多余阴影；默认值最多两行摘要并提供键盘可达的完整值读取入口；
     删除为低强调危险文字按钮，accessible name 含作用域与名称。行 key 为 `${type}:${name.toLocaleLowerCase()}`。
     过滤与分页派生在 PropertyDefinitionPanel（纯函数来自 features/properties/model），本组件只展示。 -->
<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from "vue";
import {useI18n} from "vue-i18n";
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

// 稳定作用域枚举 → 语义键映射（I18N-16：枚举值本身不翻译）
const {t} = useI18n();
function scopeLabel(definition: PropertyDefinition): string {
  return t(definition.type === "sheetset" ? "properties.scope.sheetset" : "properties.scope.sheet");
}

// —— 列宽确定（table-layout:fixed + min-width），同图纸主表的模式；列头走语义键 ——
const COLUMNS = [
  {key: "name", labelKey: "properties.definitions.colName", width: 200},
  {key: "scope", labelKey: "properties.definitions.colScope", width: 88},
  {key: "default", labelKey: "properties.definitions.colDefault", width: 320},
  {key: "actions", labelKey: "properties.definitions.colActions", width: 140},
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
      :aria-label="$t('properties.definitions.tableAria')"
    >
      <table :style="{minWidth: `${tableMinWidth}px`}">
        <colgroup>
          <col v-for="column in COLUMNS" :key="column.key" :style="{width: `${column.width}px`}">
        </colgroup>
        <thead>
          <tr>
            <th v-for="column in COLUMNS" :key="column.key" :class="`col-${column.key}`" scope="col">{{ $t(column.labelKey) }}</th>
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
              <span v-else class="empty-value">{{ $t("properties.definitions.emptyValue") }}</span>
              <button
                v-if="isLong(definition)"
                type="button"
                class="text-action"
                :aria-expanded="expandedKey === definitionKey(definition)"
                :aria-label="expandedKey === definitionKey(definition) ? $t('properties.definitions.collapseDefaultAria', {scope: scopeLabel(definition), name: definition.name}) : $t('properties.definitions.expandDefaultAria', {scope: scopeLabel(definition), name: definition.name})"
                @click="toggleExpand(definition)"
              >{{ expandedKey === definitionKey(definition) ? $t("properties.definitions.collapse") : $t("properties.definitions.expand") }}</button>
            </td>
            <td class="col-actions">
              <button
                type="button"
                class="danger-text"
                :aria-label="$t('properties.definitions.deleteAria', {scope: scopeLabel(definition), name: definition.name})"
                @click="emit('deleteDefinition', definition)"
              >{{ $t("properties.definitions.delete") }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="totalCount === 0" class="empty">{{ $t("properties.definitions.emptyNoDefinitions") }}</p>
    <p v-else-if="matchedCount === 0" class="empty">{{ $t("properties.definitions.emptyNoMatch") }}<button type="button" class="text-action" @click="emit('clearFilter')">{{ $t("properties.definitions.clearQuery") }}</button></p>
    <div class="table-foot">
      <span class="foot-info">{{ $t("properties.definitions.pageInfo", {matched: matchedCount, page, total: lastPage}) }}</span>
      <div class="pager">
        <button type="button" :disabled="page <= 1" @click="emit('changePage', page - 1)">{{ $t("properties.definitions.prevPage") }}</button>
        <button type="button" :disabled="page >= lastPage" @click="emit('changePage', page + 1)">{{ $t("properties.definitions.nextPage") }}</button>
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
