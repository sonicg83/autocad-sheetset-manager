<script setup lang="ts">
// 图纸属性分页编辑器（PLAN-DM-015 任务 5，SPEC-DM-009 §6.1）。
// 桌面端每行三列、每页 6 个属性、属性名称搜索；页脚显示总属性数/页码/跨页已修改数。
// 编辑缓冲副本由 useSheetEditor 持有（本组件只呈现与转发，不直接改工作区对象）；
// 「加入草稿」提交该图纸全部属性页，失败保留输入并呈现行内错误与可聚焦摘要；
// 未给字段路径的错误只进摘要，不编造字段归因；「取消」明确丢弃当前缓冲。
import {computed, nextTick, ref, watch} from "vue";
import type {PropertyEditContext} from "../../features/sheets/types";
import {PROPERTY_PAGE_SIZE} from "../../composables/useSheetEditor";

const props = defineProps<{context: PropertyEditContext}>();
const emit = defineEmits<{
  setValue: [name: string, value: string];
  setPage: [page: number];
  setSearch: [query: string];
  submit: [];
  cancel: [];
  jumpError: [name: string];
}>();

// —— 派生视图：搜索/翻页只改变展示，不丢输入、不自动提交 ——
const filtered = computed(() => {
  const query = props.context.search.trim().toLocaleLowerCase();
  return query
    ? props.context.propertyNames.filter((name) => name.toLocaleLowerCase().includes(query))
    : [...props.context.propertyNames];
});
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / PROPERTY_PAGE_SIZE)));
const page = computed(() => Math.min(props.context.page, totalPages.value - 1));
const pageNames = computed(() => filtered.value.slice(page.value * PROPERTY_PAGE_SIZE, (page.value + 1) * PROPERTY_PAGE_SIZE));
const modifiedCount = computed(() =>
  props.context.propertyNames.filter((name) => (props.context.values[name] ?? "") !== (props.context.original[name] ?? "")).length,
);
const hasError = computed(() => props.context.summaryError !== "" || Object.keys(props.context.errors).length > 0);
const fieldErrorNames = computed(() => props.context.propertyNames.filter((name) => props.context.errors[name]));

const statusText = computed(() => {
  if (props.context.invalid) return "编辑上下文已失效（基准已刷新或对象已消失），禁止提交";
  if (hasError.value) return "加入草稿失败，可修正后重试";
  if (modifiedCount.value > 0) return "尚未加入草稿（仅本会话保留）";
  return "暂无修改";
});

function fieldId(name: string) { return `prop-${props.context.objectId}-${name}`; }
function onInput(name: string, event: Event) { emit("setValue", name, (event.target as HTMLInputElement).value); }
function onPage(delta: number) { emit("setPage", page.value + delta); }
// 错误摘要跳转到对应页和字段：清搜索并定位后聚焦
async function onJumpError(name: string) {
  emit("jumpError", name);
  await nextTick();
  document.getElementById(fieldId(name))?.focus();
}

// 提交失败后聚焦可聚焦摘要（仅在由无错转为有错时，避免标签切回时抢焦点）
const summaryEl = ref<HTMLElement | null>(null);
let hadError = false;
watch(() => hasError.value, (now) => {
  if (now && !hadError) void nextTick(() => summaryEl.value?.focus());
  hadError = now;
});
</script>
<template>
  <section class="sheet-property-editor" :aria-label="`属性编辑 ${context.subject}`">
    <header class="editor-head">
      <h3>属性编辑 · {{ context.subject }}</h3>
      <span class="editor-head-hint">图号、派生标题、范围和文件/布局派生名不可编辑</span>
      <label class="editor-search">搜索属性<input :value="context.search" :aria-label="`搜索属性`" @input="(e) => emit('setSearch', (e.target as HTMLInputElement).value)"></label>
    </header>

    <div v-if="hasError" ref="summaryEl" class="error-summary" tabindex="-1" role="alert" aria-label="加入草稿错误摘要">
      <p class="summary-title">无法加入草稿：</p>
      <p v-if="context.summaryError" class="summary-message">{{ context.summaryError }}</p>
      <button v-for="name in fieldErrorNames" :key="name" type="button" class="summary-jump" @click="onJumpError(name)">{{ name }}：{{ context.errors[name] }}</button>
    </div>

    <div class="editor-grid">
      <div v-for="name in pageNames" :key="name" class="prop-field" :class="{invalid: context.errors[name]}">
        <label :for="fieldId(name)">属性 {{ name }}</label>
        <input
          :id="fieldId(name)"
          :value="context.values[name] ?? ''"
          :aria-invalid="context.errors[name] ? 'true' : undefined"
          @input="(e) => onInput(name, e)"
        >
        <span v-if="context.errors[name]" class="field-error">{{ context.errors[name] }}</span>
      </div>
    </div>

    <footer class="editor-footer">
      <span class="editor-counts"><span>共 {{ context.propertyNames.length }} 项</span> · <span>第 {{ page + 1 }} / {{ totalPages }} 页</span> · <span>已修改 {{ modifiedCount }} 项</span></span>
      <button type="button" :disabled="page === 0" @click="onPage(-1)">上一页</button>
      <button type="button" :disabled="page >= totalPages - 1" @click="onPage(1)">下一页</button>
      <span class="editor-status" role="status">{{ statusText }}</span>
      <span class="editor-spacer"></span>
      <button type="button" class="danger" @click="emit('cancel')">取消</button>
      <button type="button" :disabled="context.invalid" :title="context.invalid ? '编辑上下文已失效，禁止提交' : ''" @click="emit('submit')">加入草稿</button>
    </footer>
  </section>
</template>
<style scoped>
.sheet-property-editor{padding:var(--space-4);display:flex;flex-direction:column;gap:var(--space-3);background:var(--color-info-bg)}
.editor-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.editor-head h3{margin:0;font-size:15px}
.editor-head-hint{color:var(--color-text-secondary);font-size:12px}
.sheet-property-editor input{height:38px;min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.sheet-property-editor input:hover:not(:disabled){border-color:var(--color-accent)}
.sheet-property-editor input:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.editor-search{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:13px}
.editor-search input{width:180px}
/* 桌面端三列；窄视口逐级收为两列和一列。 */
.editor-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--space-3)}
.prop-field{display:flex;flex-direction:column;gap:4px}
.prop-field label{font-size:13px;color:var(--color-text-secondary)}
.prop-field input{width:100%;box-sizing:border-box}
.prop-field.invalid input{border-color:var(--color-danger)}
.field-error{color:var(--color-danger);font-size:12px}
.error-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);border-radius:var(--radius-md,8px);padding:var(--space-3);display:flex;flex-direction:column;gap:var(--space-2);outline:none}
.error-summary:focus-visible{outline:2px solid var(--color-focus)}
.summary-title{font-weight:600;margin:0;color:var(--color-danger)}
.summary-message{margin:0;font-size:13px}
.summary-jump{align-self:flex-start;color:var(--color-danger);background:none;border:none;cursor:pointer;font-size:13px;padding:0;text-decoration:underline;text-align:left}
.editor-footer{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:13px;border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3)}
.editor-counts{color:var(--color-text-secondary)}
.editor-status{color:var(--color-text-secondary)}
.editor-spacer{flex:1}
@container (max-width:900px){.editor-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@container (max-width:620px){.editor-grid{grid-template-columns:minmax(0,1fr)}}
</style>
