<!-- 图纸集属性值面板（PLAN-DM-016 任务 3，SPEC-DM-010 §5.2/§5.3）。
     消费 usePropertiesWorkspace 的缓冲/状态/过滤/动作（不直接 emit API 命令，不修改 Workspace）：
     33 项按服务端映射顺序平铺（最多两列、无分组无分页、全部 text input 38px），
     图纸集名称独立标注且不参与搜索；三态标记（琥珀未加入草稿/蓝待写入/红错误冲突）文字与颜色并存，
     输入 aria-describedby 关联状态与错误；搜索三模式与仅看修改取交集，活动字段暂留并标注；
     值对照与展开编辑走独立对话框；单项撤回仅回到草稿投影。样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {PropertyBuffer, PropertySearchMode, ValueKey, ValueStatus} from "../../features/properties/types";
import PropertyValueCompareDialog from "./PropertyValueCompareDialog.vue";

const props = defineProps<{
  input: PropertyBuffer;
  base: PropertyBuffer;
  draft: PropertyBuffer;
  statusOf: (key: ValueKey) => ValueStatus;
  errors: Partial<Record<ValueKey, string>>;
  matchedKeys: ValueKey[];
  hiddenDirtyCount: number;
  search: string;
  searchMode: PropertySearchMode;
  changedOnly: boolean;
  activeKey: ValueKey | null;
  // 折叠为工作区会话态（默认展开）：折叠后标题栏仍显示字段数与 dirty/pending/error 计数
  collapsed: boolean;
}>();
const emit = defineEmits<{
  setValue: [key: ValueKey, value: string];
  revertValue: [key: ValueKey];
  submit: [];
  discard: [];
  "update:search": [value: string];
  "update:searchMode": [value: PropertySearchMode];
  "update:changedOnly": [value: boolean];
  "update:activeKey": [key: ValueKey | null];
  "update:collapsed": [value: boolean];
  addSheetsetField: [];
}>();

const NAME_KEY: ValueKey = "@name";

const {t} = useI18n();
// 字段标签：@name 用独立语义键，其余为属性名（用户数据，保持原样，I18N-16）
function labelOf(key: ValueKey): string {
  return key === NAME_KEY ? t("properties.values.nameLabel") : key.slice("sheetset:".length);
}
function readOf(buffer: PropertyBuffer, key: ValueKey): string | undefined {
  return key === NAME_KEY ? buffer.name : buffer.values[key.slice("sheetset:".length)];
}
function errorOf(key: ValueKey): string | undefined {
  return props.errors[key];
}
function fieldId(key: ValueKey): string {
  return `prop-value-${key}`;
}
function statusId(key: ValueKey): string {
  return `prop-status-${key}`;
}
function errorId(key: ValueKey): string {
  return `prop-error-${key}`;
}
// aria-describedby 只指向实际有内容的状态/错误说明（不只依赖颜色）
function describedBy(key: ValueKey): string | undefined {
  const status = props.statusOf(key);
  const parts: string[] = [];
  if (status.dirty || status.pending) parts.push(statusId(key));
  if (errorOf(key)) parts.push(errorId(key));
  return parts.length ? parts.join(" ") : undefined;
}
// 长值整行展示（full-width），配合「展开编辑」保证长文本可完整读取
function isLong(key: ValueKey): boolean {
  return (readOf(props.input, key) ?? "").length > 40;
}

// —— 显示顺序：名称在最前，其后按匹配顺序（原顺序，不排序、不补造），活动字段暂留在末尾 ——
const valueCount = computed(() => Object.keys(props.input.values).length);
const pinnedKey = computed<ValueKey | null>(() => {
  const active = props.activeKey;
  if (!active || active === NAME_KEY) return null;
  return props.matchedKeys.includes(active) ? null : active;
});
const displayKeys = computed<ValueKey[]>(() => {
  const keys: ValueKey[] = [NAME_KEY, ...props.matchedKeys];
  if (pinnedKey.value) keys.push(pinnedKey.value);
  return keys;
});
function isPinned(key: ValueKey): boolean {
  return key === pinnedKey.value;
}
const hasNoMatch = computed(() => props.matchedKeys.length === 0 && !pinnedKey.value);
// 无自定义值：仍展示名称，并提供新增 sheetset 字段入口（与查询无结果区分的空态）
const hasNoValues = computed(() => props.input.values && Object.keys(props.input.values).length === 0);

// —— 状态摘要 ——
const allKeys = computed<ValueKey[]>(() => [NAME_KEY, ...Object.keys(props.input.values).map((name) => `sheetset:${name}` as ValueKey)]);
const dirtyCount = computed(() => allKeys.value.filter((key) => props.statusOf(key).dirty).length);
const pendingCount = computed(() => allKeys.value.filter((key) => props.statusOf(key).pending).length);
const errorCount = computed(() => Object.keys(props.errors).length);

// —— 编辑与动作 ——
function onInput(key: ValueKey, event: Event) {
  emit("setValue", key, (event.target as HTMLInputElement).value);
  emit("update:activeKey", key);
}
function endEdit() {
  emit("update:activeKey", null);
}
function clearSearch() {
  emit("update:search", "");
  emit("update:changedOnly", false);
}

// —— 值对照：三阶段（原文件值/草稿值/当前输入），相邻相同阶段合并展示（合并标签走专用语义键，不拼接片段）——
const compareKey = ref<ValueKey | null>(null);
const compareHeading = computed(() => (compareKey.value ? t("properties.values.compareHeading", {name: labelOf(compareKey.value)}) : ""));
const compareStages = computed(() => {
  const key = compareKey.value;
  if (!key) return [];
  const base = readOf(props.base, key);
  const draft = readOf(props.draft, key);
  const input = readOf(props.input, key);
  const single = (labelKey: string, value: string | undefined) => ({label: t(labelKey), value});
  if (base === draft && draft === input) return [{label: t("properties.compare.stageAll"), value: base}];
  if (base === draft) return [single("properties.compare.stageBaseDraft", base), single("properties.compare.stageInput", input)];
  if (draft === input) return [single("properties.compare.stageBase", base), single("properties.compare.stageDraftInput", draft)];
  return [single("properties.compare.stageBase", base), single("properties.compare.stageDraft", draft), single("properties.compare.stageInput", input)];
});

// —— 展开编辑：长值完整读取与编辑（textarea 不截断），关闭后焦点回字段输入 ——
const expandKey = ref<ValueKey | null>(null);
const expandedValue = ref("");
const expandCard = ref<HTMLElement | null>(null);
const expandTextarea = ref<HTMLTextAreaElement | null>(null);
// 关闭后归还焦点的目标字段（openExpand 时记录）
const expandOpener = ref<ValueKey | null>(null);
watch(expandKey, async (key) => {
  if (!key) return;
  expandedValue.value = readOf(props.input, key) ?? "";
  await nextTick();
  expandTextarea.value?.focus();
});
function openExpand(key: ValueKey) {
  expandOpener.value = key;
  expandKey.value = key;
}
function closeExpand() {
  const opener = expandOpener.value;
  expandKey.value = null;
  if (opener) document.getElementById(fieldId(opener))?.focus();
}
function applyExpand() {
  const key = expandKey.value;
  if (key) {
    emit("setValue", key, expandedValue.value);
    emit("update:activeKey", key);
  }
  closeExpand();
}
function onExpandKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") { event.stopPropagation(); closeExpand(); return; }
  if (event.key !== "Tab" || !expandCard.value) return;
  const items = Array.from(expandCard.value.querySelectorAll<HTMLElement>("textarea,button")).filter((el) => !el.hasAttribute("disabled"));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
</script>
<template>
  <section class="value-panel" :aria-label="$t('properties.values.panelAria')">
    <header class="panel-head">
      <button
        type="button"
        class="head-toggle"
        :aria-expanded="!collapsed"
        aria-controls="value-body"
        :aria-label="collapsed ? $t('properties.values.openPanel') : $t('properties.values.collapsePanel')"
        @click="emit('update:collapsed', !collapsed)"
      >
        <span class="chevron" aria-hidden="true">{{ collapsed ? "▸" : "▾" }}</span>
        <span class="head-title">{{ $t("properties.values.title") }} <small>{{ $t("properties.values.totalItems", {count: valueCount}) }}</small></span>
      </button>
      <div class="metrics" role="status" aria-live="polite">
        <span v-if="dirtyCount" class="flag dirty">{{ $t("properties.values.dirtyCount", {count: dirtyCount}) }}</span>
        <span v-if="pendingCount" class="flag pending">{{ $t("properties.values.pendingCount", {count: pendingCount}) }}</span>
        <span v-if="errorCount" class="flag error">{{ $t("properties.values.errorCount", {count: errorCount}) }}</span>
        <span v-if="!dirtyCount && !pendingCount && !errorCount" class="hint">{{ $t("properties.values.noChanges") }}</span>
      </div>
      <div class="head-actions">
        <span v-if="dirtyCount" class="submit-hint">{{ $t("properties.values.submitHint", {count: dirtyCount, hidden: hiddenDirtyCount}) }}</span>
        <button type="button" @click="emit('discard')">{{ $t("properties.values.discardInput") }}</button>
        <button type="button" class="primary" @click="emit('submit')">{{ $t("properties.values.submit") }}</button>
      </div>
    </header>
    <div v-if="!collapsed" id="value-body" class="panel-body">
      <p class="legend">
        <span class="flag dirty">{{ $t("properties.values.flagDirty") }}</span>
        <span class="flag pending">{{ $t("properties.values.flagPending") }}</span>
        <span class="flag error">{{ $t("properties.values.flagError") }}</span>
        <span class="hint">{{ $t("properties.values.legendHint") }}</span>
      </p>
      <div v-if="!hasNoValues" class="value-toolbar">
        <input
          type="search"
          :aria-label="$t('properties.values.searchLabel')"
          :placeholder="$t('properties.values.searchPlaceholder')"
          :value="search"
          @input="emit('update:search', ($event.target as HTMLInputElement).value)"
        >
        <select :aria-label="$t('properties.values.searchScopeLabel')" :value="searchMode" @change="emit('update:searchMode', ($event.target as HTMLSelectElement).value as PropertySearchMode)">
          <option value="all">{{ $t("properties.values.searchAll") }}</option>
          <option value="name">{{ $t("properties.values.searchNameOnly") }}</option>
          <option value="value">{{ $t("properties.values.searchValueOnly") }}</option>
        </select>
        <label class="only-changed"><input type="checkbox" :checked="changedOnly" @change="emit('update:changedOnly', ($event.target as HTMLInputElement).checked)">{{ $t("properties.values.changedOnly") }}</label>
        <button type="button" class="link" @click="clearSearch">{{ $t("properties.values.clearSearch") }}</button>
        <span class="match-count">{{ $t("properties.values.matchCount", {matched: matchedKeys.length, total: valueCount}) }}<template v-if="hiddenDirtyCount">{{ $t("properties.values.hiddenDirtySuffix", {count: hiddenDirtyCount}) }}</template></span>
      </div>
      <div class="value-grid">
        <div v-for="key in displayKeys" :key="key" class="value-item" :class="{name: key === NAME_KEY, full: isLong(key), invalid: Boolean(errorOf(key)), pinned: isPinned(key)}">
          <label :for="fieldId(key)">{{ labelOf(key) }}</label>
          <div class="input-line">
            <input
              :id="fieldId(key)"
              type="text"
              autocomplete="off"
              :value="readOf(input, key) ?? ''"
              :aria-label="key === NAME_KEY ? undefined : $t('properties.values.fieldAria', {name: labelOf(key)})"
              :aria-invalid="errorOf(key) ? 'true' : undefined"
              :aria-describedby="describedBy(key)"
              @input="onInput(key, $event)"
              @focus="emit('update:activeKey', key)"
            >
            <button type="button" class="link" :aria-label="$t('properties.values.expandEditAria', {name: labelOf(key)})" @click="openExpand(key)">{{ $t("properties.values.expandEdit") }}</button>
          </div>
          <div class="field-foot">
            <span :id="statusId(key)" class="flags">
              <span v-if="statusOf(key).dirty" class="flag dirty">{{ $t("properties.values.flagDirty") }}</span>
              <span v-if="statusOf(key).pending" class="flag pending">{{ $t("properties.values.flagPending") }}</span>
            </span>
            <span class="spacer"></span>
            <button type="button" class="link" :aria-label="$t('properties.values.compareAria', {name: labelOf(key)})" @click="compareKey = key">{{ $t("properties.values.compare") }}</button>
            <button type="button" class="link" :aria-label="$t('properties.values.revertAria', {name: labelOf(key)})" :disabled="!statusOf(key).dirty" @click="emit('revertValue', key)">{{ $t("properties.values.revert") }}</button>
          </div>
          <p v-if="errorOf(key)" :id="errorId(key)" class="field-error">{{ errorOf(key) }}</p>
          <p v-if="isPinned(key)" class="pinned-note">{{ $t("properties.values.pinnedNote") }} <button type="button" class="link" @click="endEdit">{{ $t("properties.values.endEdit") }}</button></p>
        </div>
      </div>
      <div v-if="hasNoValues" class="empty empty-values">
        <p>{{ $t("properties.values.noValuesHint") }}</p>
        <button type="button" @click="emit('addSheetsetField')">{{ $t("properties.values.addSheetsetField") }}</button>
      </div>
      <p v-else-if="hasNoMatch" class="empty">{{ $t("properties.values.noMatch") }}</p>
    </div>
    <PropertyValueCompareDialog :open="compareKey !== null" :heading="compareHeading" :stages="compareStages" @close="compareKey = null" />
    <div v-if="expandKey" class="modal-mask" @keydown="onExpandKeydown">
      <div ref="expandCard" class="modal-card" role="dialog" aria-modal="true" :aria-label="$t('properties.values.expandDialogTitle', {name: labelOf(expandKey)})" tabindex="-1">
        <h2>{{ $t("properties.values.expandDialogTitle", {name: labelOf(expandKey)}) }}</h2>
        <p class="expand-hint">{{ $t("properties.values.expandHint") }}</p>
        <textarea ref="expandTextarea" v-model="expandedValue" rows="8" :aria-label="$t('properties.values.expandedTextareaAria')"></textarea>
        <div class="modal-actions">
          <button type="button" @click="closeExpand">{{ $t("properties.values.cancel") }}</button>
          <button type="button" class="primary" @click="applyExpand">{{ $t("properties.values.applyToInput") }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.value-panel{background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:60px;padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
/* 折叠开关沿用属性页受控按钮基线（≥36px、边框与不透明背景），仅排布为标题样式 */
.head-toggle{display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);min-height:36px}
/* 标题文字用 span（button 内不允许 h2）：面板名由 section aria-label 与按钮 aria-label 提供 */
.head-title{margin:0;font-size:16px;font-weight:600}
.head-title small{font-weight:400;color:var(--color-text-secondary);font-size:12px}
.chevron{color:var(--color-text-secondary);font-size:12px}
.metrics{display:flex;gap:var(--space-2);flex-wrap:wrap}
.head-actions{margin-left:auto;display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:center}
.submit-hint{color:var(--color-text-muted);font-size:12px}
.head-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.legend{display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:center;font-size:12px;color:var(--color-text-secondary);margin:0 0 var(--space-3)}
.flag{display:inline-block;font-size:12px;padding:3px 9px;border-radius:var(--radius-full);white-space:nowrap}
.flag.dirty{color:var(--color-warning);background:var(--color-warning-bg)}
.flag.pending{color:var(--color-info);background:var(--color-info-bg)}
.flag.error{color:var(--color-danger);background:var(--color-danger-bg)}
.hint{color:var(--color-text-muted);font-size:12px}
/* 面板体作为容器查询上下文：缩放/极窄容器下两列最小宽度放不下时兜底降一列 */
.panel-body{padding:var(--space-4) var(--space-5);container:value-body / inline-size}
/* 双列节奏（minmax(240px,360px)）；视口 ≤900px（与 Demo 断点对齐）或容器不足以容纳两个最小列时降一列。
   长值与名称行整行展示。 */
.value-grid{display:grid;grid-template-columns:repeat(2,minmax(240px,360px));gap:var(--space-3) var(--space-5);justify-content:start}
.value-item{min-width:0;display:flex;flex-direction:column;gap:var(--space-1);padding:var(--space-2);border:1px solid transparent;border-radius:var(--radius-md)}
.value-item:focus-within{background:var(--color-bg-canvas)}
.value-item.full,.value-item.name{grid-column:1 / -1}
.value-item.name{border-bottom:1px solid var(--color-border-subtle);border-radius:0;padding-bottom:var(--space-3);margin-bottom:var(--space-2)}
.value-item.invalid{border-color:var(--color-danger);background:var(--color-danger-bg)}
.value-item label{font-size:13px;font-weight:500;color:var(--color-text-secondary)}
.value-item input{height:38px;width:100%;min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.value-item input:hover:not(:disabled){border-color:var(--color-accent)}
.value-item.invalid input{border-color:var(--color-danger)}
.input-line{display:flex;align-items:center;gap:var(--space-1)}
.input-line input{flex:1}
.field-foot{min-height:36px;display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap}
.field-foot .flags{display:flex;gap:var(--space-1);flex-wrap:wrap}
.field-foot .spacer{flex:1;min-width:0}
.field-error{margin:0;color:var(--color-danger);font-size:12px;line-height:1.7}
.pinned-note{margin:0;color:var(--color-text-secondary);font-size:12px}
/* 值面板行内文字操作按钮属 36px 普通档（34px 仅限工具栏紧凑按钮）：不透明语义背景 + 8px 横向留白 */
button.link{min-height:36px;padding:2px var(--space-2);border:1px solid transparent;border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-accent);white-space:nowrap;font-size:12px}
button.link:hover:not(:disabled){background:var(--color-bg-muted)}
button.link:disabled{color:var(--color-text-muted);cursor:not-allowed}
button.link:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
/* 搜索工具行与值网格共用 38px 输入密度 */
.value-toolbar{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap;margin-bottom:var(--space-3)}
.value-toolbar input[type="search"]{height:38px;width:280px;min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.value-toolbar select{height:38px;padding:6px 8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.value-toolbar .only-changed{display:inline-flex;align-items:center;gap:var(--space-1);font-size:13px;color:var(--color-text-secondary)}
.match-count{margin-left:auto;color:var(--color-text-muted);font-size:12px}
.empty{text-align:center;padding:var(--space-5);color:var(--color-text-secondary);margin:0}
/* 无自定义值空态：与查询无结果区分，提供新增 sheetset 字段入口 */
.empty-values{display:grid;justify-items:center;gap:var(--space-3);border:1px dashed var(--color-border-subtle);border-radius:var(--radius-md)}
.empty-values p{margin:0}
.empty-values button{min-height:36px;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface)}
/* 展开编辑对话框（复用公共模态原语；textarea 长文本完整显示不截断） */
.expand-hint{margin:0 0 var(--space-3);color:var(--color-text-secondary);font-size:13px;line-height:1.7}
textarea{width:100%;min-height:140px;resize:vertical;padding:8px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
@media (max-width:900px){.value-grid{grid-template-columns:minmax(0,1fr)}}
@container value-body (max-width:511px){.value-grid{grid-template-columns:minmax(0,1fr)}}
</style>
