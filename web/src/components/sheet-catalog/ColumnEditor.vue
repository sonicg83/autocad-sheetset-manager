<!-- 输出列编辑器（SPEC-DM-012 §7.2 区域 3）：列名 + 表达式编辑、添加/删除/排序；
     表达式错误定位到具体列并聚焦首个可操作问题（SPEC §13：焦点移到首个问题，
     且不打断正在输入的用户）。光标位置经 selection API 回传状态所有者。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {CatalogDiagnostic, SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

const headerInputs = ref<Record<string, HTMLInputElement | null>>({});
const expressionInputs = ref<Record<string, HTMLTextAreaElement | null>>({});
const region = ref<HTMLElement | null>(null);

function trackCaret(columnId: string, element: HTMLTextAreaElement) {
  props.catalog.trackCaret(columnId, element.selectionStart ?? 0, element.selectionEnd ?? 0);
}

function columnError(columnId: string, header: string): CatalogDiagnostic | null {
  const errors = props.catalog.preview.value?.errors ?? [];
  return errors.find(error => error.columnId === columnId)
    ?? errors.find(error => error.columnId === null && typeof error.params.header === "string" && error.params.header.toLowerCase() === header.toLowerCase())
    ?? null;
}

function errorText(diagnostic: CatalogDiagnostic): string {
  return t(diagnostic.messageKey, diagnostic.params);
}

// 焦点管理：阻断错误首次出现（或换列）时聚焦首个可操作问题（SPEC §13：表达式错误
// 聚焦具体编辑框）；用户正在编辑器内输入时不抢焦点。Task 12 补齐两类缺口：
// 未知字段（FIELD_UNDEFINED）定位到该列表达式输入框（错误在表达式而非列名）；
// 无 column_id 的阻断错误（重名列，诊断只携带 header 参数）按结构化参数定位到
// 最后一个匹配列的列名输入框（后引入的重复列才是需要修正的列）。
const focusedSignature = ref("");
const errorSignature = computed(() => (props.catalog.preview.value?.errors ?? [])
  .map(error => `${error.code}:${error.columnId ?? String(error.params.header ?? "")}`).join("|"));
watch(errorSignature, signature => {
  if (!signature || signature === focusedSignature.value) return;
  const active = document.activeElement;
  if (active instanceof HTMLElement && region.value?.contains(active)) return;
  focusedSignature.value = signature;
  const first = props.catalog.preview.value?.errors?.[0];
  if (!first) return;
  void nextTick(() => {
    if (first.columnId !== null) {
      const target = first.code === "SHEET_CATALOG_EXPRESSION_INVALID" || first.code === "SHEET_CATALOG_FIELD_UNDEFINED"
        ? expressionInputs.value[first.columnId]
        : headerInputs.value[first.columnId] ?? expressionInputs.value[first.columnId];
      target?.focus();
      return;
    }
    const header = typeof first.params.header === "string" ? first.params.header : "";
    if (header === "") return;
    const matches = props.catalog.draft.value.columns.filter(column => column.header.toLowerCase() === header.toLowerCase());
    if (matches.length === 0) return;
    headerInputs.value[matches[matches.length - 1]!.columnId]?.focus();
  });
});

// 字段插入后把光标放回插入点之后
watch(() => props.catalog.caretRequest.value, async request => {
  if (!request) return;
  await nextTick();
  const element = expressionInputs.value[request.columnId];
  if (element) {
    element.focus();
    element.setSelectionRange(request.position, request.position);
  }
  props.catalog.caretRequest.value = null;
});
</script>
<template>
  <section ref="region" class="column-editor panel" :aria-label="$t('extensions.sheetCatalog.editorLabel')">
    <div class="editor-head">
      <h3>{{ $t("extensions.sheetCatalog.editorLabel") }}</h3>
      <button type="button" @click="catalog.addColumn()">{{ $t("extensions.sheetCatalog.addColumn") }}</button>
    </div>
    <ol class="columns">
      <li v-for="(column, index) in catalog.draft.value.columns" :key="column.columnId" class="column-row">
        <div class="column-fields">
          <label>
            <span>{{ $t("extensions.sheetCatalog.columnHeader", {index: index + 1}) }}</span>
            <input
              :ref="element => { headerInputs[column.columnId] = element as HTMLInputElement | null }"
              type="text"
              :aria-label="$t('extensions.sheetCatalog.columnHeader', {index: index + 1})"
              :value="column.header"
              @input="catalog.updateColumn(column.columnId, {header: ($event.target as HTMLInputElement).value})"
            >
          </label>
          <label>
            <span>{{ $t("extensions.sheetCatalog.columnExpression", {index: index + 1}) }}</span>
            <textarea
              :ref="element => { expressionInputs[column.columnId] = element as HTMLTextAreaElement | null }"
              rows="2"
              :aria-label="$t('extensions.sheetCatalog.columnExpression', {index: index + 1})"
              :value="column.expression"
              @input="catalog.updateColumn(column.columnId, {expression: ($event.target as HTMLTextAreaElement).value}); trackCaret(column.columnId, $event.target as HTMLTextAreaElement)"
              @click="trackCaret(column.columnId, $event.target as HTMLTextAreaElement)"
              @keyup="trackCaret(column.columnId, $event.target as HTMLTextAreaElement)"
              @blur="trackCaret(column.columnId, $event.target as HTMLTextAreaElement)"
            ></textarea>
          </label>
        </div>
        <p v-if="columnError(column.columnId, column.header)" class="error column-error" role="alert">{{ errorText(columnError(column.columnId, column.header)!) }}</p>
        <div class="column-actions">
          <button type="button" :disabled="index === 0" :aria-label="$t('extensions.sheetCatalog.moveUp', {index: index + 1})" @click="catalog.moveColumn(column.columnId, -1)">↑</button>
          <button type="button" :disabled="index === catalog.draft.value.columns.length - 1" :aria-label="$t('extensions.sheetCatalog.moveDown', {index: index + 1})" @click="catalog.moveColumn(column.columnId, 1)">↓</button>
          <button type="button" class="danger-text" :aria-label="$t('extensions.sheetCatalog.removeColumn', {index: index + 1})" @click="catalog.removeColumn(column.columnId)">✕</button>
        </div>
      </li>
    </ol>
  </section>
</template>
<style scoped>
.column-editor{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.editor-head{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3)}
.editor-head h3{margin:0;font-size:14px}
.columns{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--space-3)}
.column-row{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);padding:var(--space-3);display:grid;gap:var(--space-2)}
.column-fields{display:grid;grid-template-columns:minmax(120px,1fr) minmax(0,2fr);gap:var(--space-3)}
.column-fields label{display:grid;gap:4px;font-size:13px;color:var(--color-text-secondary);min-width:0}
.column-fields input,.column-fields textarea{padding:8px;border:1px solid var(--color-border-strong);border-radius:5px;min-width:0;font-family:inherit}
.column-fields textarea{font-family:ui-monospace,Consolas,monospace}
.column-error{margin:0;font-size:13px}
.column-actions{display:flex;gap:6px;justify-content:flex-end}
.column-actions button{padding:4px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-muted)}
.danger-text{color:var(--color-danger)}
@media (max-width: 720px){.column-fields{grid-template-columns:1fr}}
</style>
