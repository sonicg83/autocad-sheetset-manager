<script setup lang="ts">
// 图纸属性分页编辑器（PLAN-DM-015 任务 5，SPEC-DM-009 §6.1）。
// 桌面端每行三列、每页 6 个属性、属性名称搜索；页脚显示总属性数/页码/跨页已修改数。
// 编辑缓冲副本由 useSheetEditor 持有（本组件只呈现与转发，不直接改工作区对象）；
// 「加入草稿」提交该图纸全部属性页，失败保留输入并呈现行内错误与可聚焦摘要；
// 未给字段路径的错误只进摘要，不编造字段归因；「取消」明确丢弃当前缓冲。
// PLAN-DM-034：无跨页修改时「加入草稿」为可聚焦的语义禁用（UiButton ariaDisabled +
// onSubmit 守卫双保险）；dirty 字段比较当前值与草稿投影基准，琥珀提示在输入附近并经
// aria-describedby 关联，错误状态优先于 dirty。页脚「取消/加入草稿」迁移到 UiButton，
// 分页与错误跳转按钮不在本任务迁移。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import type {PropertyEditContext} from "../../features/sheets/types";
import {PROPERTY_PAGE_SIZE} from "../../composables/useSheetEditor";

const props = defineProps<{context: PropertyEditContext}>();
const {t} = useI18n();
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
  if (props.context.invalid) return t("sheets.operation.statusInvalid");
  if (hasError.value) return t("sheets.editor.statusFailed");
  if (modifiedCount.value > 0) return t("sheets.editor.statusDraft");
  return t("sheets.editor.statusClean");
});

function fieldId(name: string) { return `prop-${props.context.objectId}-${name}`; }
// dirty 一律比较当前值与可信基准（草稿投影），不用「曾编辑」标志：改回基准即清除。
function isDirty(name: string) { return (props.context.values[name] ?? "") !== (props.context.original[name] ?? ""); }
function fieldErrorId(name: string) { return `${fieldId(name)}-error`; }
function fieldStatusId(name: string) { return `${fieldId(name)}-status`; }
// 字段状态文字（dirty 提示 / 行内错误）经 aria-describedby 与输入关联。
function describedBy(name: string) {
  const ids = [isDirty(name) ? fieldStatusId(name) : "", props.context.errors[name] ? fieldErrorId(name) : ""].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}
function onInput(name: string, event: Event) { emit("setValue", name, (event.target as HTMLInputElement).value); }
function onPage(delta: number) { emit("setPage", page.value + delta); }
// 提交守卫（PLAN-DM-034）：编程调用也造不出空草稿——跨页无修改或上下文失效时直接返回。
function onSubmit() {
  if (modifiedCount.value === 0 || props.context.invalid) return;
  emit("submit");
}
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
  <section class="sheet-property-editor" :aria-label="$t('sheets.editor.aria', {subject: context.subject})">
    <header class="editor-head">
      <h3>{{ $t("sheets.editor.title", {subject: context.subject}) }}</h3>
      <span class="editor-head-hint">{{ $t("sheets.editor.headHint") }}</span>
      <label class="editor-search">{{ $t("sheets.editor.searchLabel") }}<input :value="context.search" :aria-label="$t('sheets.editor.searchLabel')" @input="(e) => emit('setSearch', (e.target as HTMLInputElement).value)"></label>
    </header>

    <div v-if="hasError" ref="summaryEl" class="error-summary" tabindex="-1" role="alert" :aria-label="$t('sheets.editor.summaryAria')">
      <p class="summary-title">{{ $t("sheets.editor.summaryTitle") }}</p>
      <p v-if="context.summaryError" class="summary-message">{{ context.summaryError }}</p>
      <button v-for="name in fieldErrorNames" :key="name" type="button" class="summary-jump" @click="onJumpError(name)">{{ name }}：{{ context.errors[name] }}</button>
    </div>

    <div class="editor-grid">
      <div v-for="name in pageNames" :key="name" class="prop-field" :class="{invalid: context.errors[name], 'is-dirty': isDirty(name)}">
        <label :for="fieldId(name)">{{ $t("sheets.editor.propLabel", {name}) }}</label>
        <input
          :id="fieldId(name)"
          :value="context.values[name] ?? ''"
          :aria-invalid="context.errors[name] ? 'true' : undefined"
          :aria-describedby="describedBy(name)"
          @input="(e) => onInput(name, e)"
        >
        <span v-if="isDirty(name)" :id="fieldStatusId(name)" class="field-status">{{ $t("sheets.editor.statusDraft") }}</span>
        <span v-if="context.errors[name]" :id="fieldErrorId(name)" class="field-error">{{ context.errors[name] }}</span>
      </div>
    </div>

    <footer class="editor-footer">
      <span class="editor-counts"><span>{{ $t("sheets.editor.totalItems", {count: context.propertyNames.length}) }}</span> · <span>{{ $t("sheets.editor.pageInfo", {page: page + 1, total: totalPages}) }}</span> · <span>{{ $t("sheets.editor.modifiedCount", {count: modifiedCount}) }}</span></span>
      <button type="button" :disabled="page === 0" @click="onPage(-1)">{{ $t("sheets.editor.prevPage") }}</button>
      <button type="button" :disabled="page >= totalPages - 1" @click="onPage(1)">{{ $t("sheets.editor.nextPage") }}</button>
      <span class="editor-status" role="status">{{ statusText }}</span>
      <span class="editor-spacer"></span>
      <UiButton variant="secondary" @click="emit('cancel')">{{ $t("sheets.editor.cancel") }}</UiButton>
      <UiButton
        variant="primary"
        :disabled="context.invalid"
        :aria-disabled="modifiedCount === 0"
        :title="context.invalid ? $t('sheets.editor.invalidTooltip') : undefined"
        @click="onSubmit"
      >{{ $t("sheets.editor.addToDraft") }}</UiButton>
    </footer>
  </section>
</template>
<style scoped>
.sheet-property-editor{padding:var(--space-4);display:flex;flex-direction:column;gap:var(--space-3);background:var(--color-info-bg)}
.editor-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.editor-head h3{margin:0;font-size:var(--font-panel-title)}
.editor-head-hint{color:var(--color-text-secondary);font-size:var(--font-caption)}
.sheet-property-editor input{height:var(--control-height-form);min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.sheet-property-editor input:hover:not(:disabled){border-color:var(--color-accent)}
.sheet-property-editor input:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.editor-search{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:var(--font-label)}
.editor-search input{width:var(--sheet-property-search-width)}
/* 桌面端三列；窄视口逐级收为两列和一列。 */
.editor-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--space-3)}
.prop-field{display:flex;flex-direction:column;gap:4px;border:1px solid transparent;border-radius:var(--radius-md)}
.prop-field label{font-size:var(--font-label);color:var(--color-text-secondary)}
.prop-field input{width:100%;box-sizing:border-box}
/* dirty 用现有琥珀令牌标出「未加入草稿」；invalid 必须写在 dirty 之后，红色错误优先。 */
.prop-field.is-dirty{border-color:var(--color-warning);background:var(--color-warning-bg)}
.prop-field.is-dirty input{border-color:var(--color-warning)}
.prop-field.invalid{border-color:var(--color-danger);background:var(--color-danger-bg)}
.prop-field.invalid input{border-color:var(--color-danger)}
.field-status{color:var(--color-warning);font-size:var(--font-caption)}
.field-error{color:var(--color-danger);font-size:var(--font-caption)}
.error-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);border-radius:var(--radius-md,8px);padding:var(--space-3);display:flex;flex-direction:column;gap:var(--space-2);outline:none}
.error-summary:focus-visible{outline:2px solid var(--color-focus)}
.summary-title{font-weight:600;margin:0;color:var(--color-danger)}
.summary-message{margin:0;font-size:var(--font-label)}
.summary-jump{align-self:flex-start;color:var(--color-danger);background:none;border:none;cursor:pointer;font-size:var(--font-label);padding:0;text-decoration:underline;text-align:left}
.editor-footer{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:var(--font-label);border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3)}
.editor-counts{color:var(--color-text-secondary)}
.editor-status{color:var(--color-text-secondary)}
.editor-spacer{flex:1}
@container (max-width:900px){.editor-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@container (max-width:620px){.editor-grid{grid-template-columns:minmax(0,1fr)}}
</style>
