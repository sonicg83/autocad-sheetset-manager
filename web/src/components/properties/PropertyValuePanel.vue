<!-- 图纸集属性值面板（PLAN-DM-016 任务 3，SPEC-DM-010 §5.2/§5.3）。
     消费 usePropertiesWorkspace 的缓冲/状态/过滤/动作（不直接 emit API 命令，不修改 Workspace）：
     33 项按服务端映射顺序平铺（最多两列、无分组无分页、全部 text input 38px），
     图纸集名称独立标注且不参与搜索；三态标记（琥珀未加入草稿/蓝待写入/红错误冲突）文字与颜色并存，
     输入 aria-describedby 关联状态与错误；搜索三模式与仅看修改取交集，活动字段暂留并标注；
     值对照与展开编辑走独立对话框；单项撤回仅回到草稿投影。样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
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
}>();

const NAME_KEY: ValueKey = "@name";

function labelOf(key: ValueKey): string {
  return key === NAME_KEY ? "图纸集名称" : key.slice("sheetset:".length);
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

// —— 值对照：三阶段（原文件值/草稿值/当前输入），相邻相同阶段合并展示 ——
const compareKey = ref<ValueKey | null>(null);
const compareHeading = computed(() => (compareKey.value ? `值对照 · ${labelOf(compareKey.value)}` : ""));
const compareStages = computed(() => {
  const key = compareKey.value;
  if (!key) return [];
  const raw = [
    {label: "原文件值", value: readOf(props.base, key)},
    {label: "草稿值", value: readOf(props.draft, key)},
    {label: "当前输入", value: readOf(props.input, key)},
  ];
  const merged: {label: string; value: string | undefined}[] = [];
  for (const stage of raw) {
    const last = merged[merged.length - 1];
    if (last && last.value === stage.value) last.label += ` / ${stage.label}`;
    else merged.push({...stage});
  }
  return merged;
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
  <section class="value-panel" aria-label="图纸集属性值">
    <header class="panel-head">
      <h2>图纸集属性值 <small>{{ valueCount }} 项</small></h2>
      <div class="metrics" role="status" aria-live="polite">
        <span v-if="dirtyCount" class="flag dirty">未加入草稿 {{ dirtyCount }} 项</span>
        <span v-if="pendingCount" class="flag pending">待写入 {{ pendingCount }} 项</span>
        <span v-if="errorCount" class="flag error">错误 {{ errorCount }} 项</span>
        <span v-if="!dirtyCount && !pendingCount && !errorCount" class="hint">无属性值修改</span>
      </div>
      <div class="head-actions">
        <button type="button" @click="emit('discard')">放弃本区输入</button>
        <button type="button" class="primary" @click="emit('submit')">更新图纸集</button>
      </div>
    </header>
    <div class="panel-body">
      <p class="legend">
        <span class="flag dirty">未加入草稿</span>
        <span class="flag pending">待写入</span>
        <span class="flag error">错误 / 冲突</span>
        <span class="hint">所有自定义属性均为文本，不分组、不分页。</span>
      </p>
      <div class="value-toolbar">
        <input
          type="search"
          aria-label="搜索属性值"
          placeholder="搜索字段名或属性值"
          :value="search"
          @input="emit('update:search', ($event.target as HTMLInputElement).value)"
        >
        <select aria-label="搜索范围" :value="searchMode" @change="emit('update:searchMode', ($event.target as HTMLSelectElement).value as PropertySearchMode)">
          <option value="all">字段名或属性值</option>
          <option value="name">仅字段名</option>
          <option value="value">仅属性值</option>
        </select>
        <label class="only-changed"><input type="checkbox" :checked="changedOnly" @change="emit('update:changedOnly', ($event.target as HTMLInputElement).checked)">仅看修改</label>
        <button type="button" class="link" @click="clearSearch">清除搜索</button>
        <span class="match-count">匹配 {{ matchedKeys.length }} / 共 {{ valueCount }} 项<template v-if="hiddenDirtyCount"> · {{ hiddenDirtyCount }} 项修改被隐藏</template></span>
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
              :aria-label="key === NAME_KEY ? undefined : `属性 ${labelOf(key)}`"
              :aria-invalid="errorOf(key) ? 'true' : undefined"
              :aria-describedby="describedBy(key)"
              @input="onInput(key, $event)"
              @focus="emit('update:activeKey', key)"
            >
            <button type="button" class="link" :aria-label="`展开编辑 ${labelOf(key)}`" @click="openExpand(key)">展开编辑</button>
          </div>
          <div class="field-foot">
            <span :id="statusId(key)" class="flags">
              <span v-if="statusOf(key).dirty" class="flag dirty">未加入草稿</span>
              <span v-if="statusOf(key).pending" class="flag pending">待写入</span>
            </span>
            <span class="spacer"></span>
            <button type="button" class="link" :aria-label="`值对照 ${labelOf(key)}`" @click="compareKey = key">值对照</button>
            <button type="button" class="link" :aria-label="`撤回 ${labelOf(key)}`" :disabled="!statusOf(key).dirty" @click="emit('revertValue', key)">撤回</button>
          </div>
          <p v-if="errorOf(key)" :id="errorId(key)" class="field-error">{{ errorOf(key) }}</p>
          <p v-if="isPinned(key)" class="pinned-note">不再匹配当前搜索 · 暂留编辑 <button type="button" class="link" @click="endEdit">结束编辑</button></p>
        </div>
      </div>
      <p v-if="hasNoMatch" class="empty">没有匹配属性；请清除搜索或关闭“仅看修改”。</p>
      <div class="local-actions">
        <span class="hint">加入草稿：共 {{ dirtyCount }} 项，其中 {{ hiddenDirtyCount }} 项当前未显示 · 尚未写入正式文件</span>
      </div>
    </div>
    <PropertyValueCompareDialog :open="compareKey !== null" :heading="compareHeading" :stages="compareStages" @close="compareKey = null" />
    <div v-if="expandKey" class="modal-mask" @keydown="onExpandKeydown">
      <div ref="expandCard" class="modal-card" role="dialog" aria-modal="true" :aria-label="`展开编辑 · ${labelOf(expandKey)}`" tabindex="-1">
        <h2>展开编辑 · {{ labelOf(expandKey) }}</h2>
        <p class="expand-hint">仅编辑文本输入；显示换行不改变原文，长文本不截断。</p>
        <textarea ref="expandTextarea" v-model="expandedValue" rows="8" aria-label="展开后的属性文本"></textarea>
        <div class="modal-actions">
          <button type="button" @click="closeExpand">取消</button>
          <button type="button" class="primary" @click="applyExpand">应用到输入</button>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.value-panel{background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);margin-bottom:var(--space-4);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:60px;padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.panel-head h2{margin:0;font-size:16px}
.panel-head small{font-weight:400;color:var(--color-text-secondary);font-size:12px}
.metrics{display:flex;gap:var(--space-2);flex-wrap:wrap}
.head-actions{margin-left:auto;display:flex;gap:var(--space-2);flex-wrap:wrap}
.head-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.legend{display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:center;font-size:12px;color:var(--color-text-secondary);margin:0 0 var(--space-3)}
.flag{display:inline-block;font-size:12px;padding:3px 9px;border-radius:var(--radius-full);white-space:nowrap}
.flag.dirty{color:var(--color-warning);background:var(--color-warning-bg)}
.flag.pending{color:var(--color-info);background:var(--color-info-bg)}
.flag.error{color:var(--color-danger);background:var(--color-danger-bg)}
.hint{color:var(--color-text-muted);font-size:12px}
.panel-body{padding:var(--space-4) var(--space-5)}
/* 双列节奏（minmax(240px,360px)）；窄宽度降为一列。长值与名称行整行展示。 */
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
/* 纯文字操作按钮按生产密度基线取 34px 紧凑工具按钮档 */
button.link{min-height:34px;padding:2px 6px;border:1px solid transparent;border-radius:var(--radius-sm);background:none;color:var(--color-accent);white-space:nowrap;font-size:12px}
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
.local-actions{display:flex;gap:var(--space-3);align-items:center;flex-wrap:wrap;border-top:1px solid var(--color-border-subtle);margin-top:var(--space-4);padding-top:var(--space-4)}
/* 展开编辑对话框（复用公共模态原语；textarea 长文本完整显示不截断） */
.expand-hint{margin:0 0 var(--space-3);color:var(--color-text-secondary);font-size:13px;line-height:1.7}
textarea{width:100%;min-height:140px;resize:vertical;padding:8px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
@media (max-width:700px){.value-grid{grid-template-columns:minmax(0,1fr)}}
</style>
