<!-- 输出列编辑器（SPEC-DM-012 §7.2 区域 3）：列名 + 表达式编辑、添加/删除/排序；
     表达式错误定位到具体列并聚焦首个可操作问题（SPEC §13：焦点移到首个问题，
     且不打断正在输入的用户）。光标位置经 selection API 回传状态所有者。
     PLAN-DM-023 Task 3（V1/V5/V8）：恢复冻结 Demo 的紧凑表格式——`.columns-head`
     与 `.column-row` 共用同一组 grid 轨道，每行同时显示顺序、列名、表达式、状态和
     操作；列区自身限高滚动，列数增长不撑高页面。表头放进同一个滚动容器并 sticky，
     保证出现纵向滚动条时表头与数据行宽度始终一致（对齐误差为 0）。
     A1（用户已接受差异）：操作列继续使用 ↑ / ↓ / ✕ 图标按钮与完整 aria-label，
     因此该轨道（112px）比冻结 Demo 的 188px 文字按钮列更窄。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import {SHEET_CATALOG_MAX_COLUMNS, type CatalogDiagnostic, type SheetCatalogController} from "../../composables/useSheetCatalog";
import CompatibilitySummary from "./CompatibilitySummary.vue";
import {catalogCompatibility} from "./catalogCompatibility";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

// 兼容徒标与摘要正文同源（PLAN-DM-023 Task 4）：判定只在 catalogCompatibility 一处
const compat = computed(() => catalogCompatibility(props.catalog));
const badgeText = computed(() => {
  switch (compat.value.tone) {
    case "ok": return t("extensions.sheetCatalog.compatBadgeExecutable");
    case "warning": return t("extensions.sheetCatalog.compatBadgeWarning", {count: compat.value.warnings.length});
    case "checking": return t("extensions.sheetCatalog.compatBadgeChecking");
    default: return t("extensions.sheetCatalog.compatBadgeBlocked");
  }
});
const badgeClass = computed(() => (compat.value.tone === "ok" ? "good" : compat.value.tone === "warning" ? "warn" : compat.value.tone === "checking" ? "checking" : "bad"));

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

// 每行只解析一次诊断：顺序/表达式/状态单元格共用同一结果（不复制后端校验规则，
// 状态完全来自服务端诊断，前端不重新判定有效或需修正）。
const rows = computed(() => props.catalog.draft.value.columns.map((column, index) => ({
  column,
  index,
  error: columnError(column.columnId, column.header),
})));

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
      <span class="compat-badge" :class="badgeClass">{{ badgeText }}</span>
      <span class="spacer"></span>
      <span class="column-count">{{ $t("extensions.sheetCatalog.columnCount", {count: catalog.draft.value.columns.length, limit: SHEET_CATALOG_MAX_COLUMNS}) }}</span>
    </div>
    <!-- 兼容性摘要嵌在输出列卡内（V2）：详细正文紧随卡头，不再作为独立全宽卡片 -->
    <CompatibilitySummary :catalog="catalog" />
    <div class="columns">
      <div class="columns-head">
        <span>{{ $t("extensions.sheetCatalog.columnsHeadOrder") }}</span>
        <span>{{ $t("extensions.sheetCatalog.columnsHeadHeader") }}</span>
        <span>{{ $t("extensions.sheetCatalog.columnsHeadExpression") }}</span>
        <span>{{ $t("extensions.sheetCatalog.columnsHeadStatus") }}</span>
        <span>{{ $t("extensions.sheetCatalog.columnsHeadActions") }}</span>
      </div>
      <ol class="column-list">
        <li
          v-for="row in rows" :key="row.column.columnId" class="column-row"
          :class="{'is-error': row.error !== null}"
        >
          <span class="order-cell">{{ row.index + 1 }}</span>
          <input
            :ref="element => { headerInputs[row.column.columnId] = element as HTMLInputElement | null }"
            type="text"
            :aria-label="$t('extensions.sheetCatalog.columnHeader', {index: row.index + 1})"
            :value="row.column.header"
            @input="catalog.updateColumn(row.column.columnId, {header: ($event.target as HTMLInputElement).value})"
          >
          <div class="expression-cell">
            <textarea
              :ref="element => { expressionInputs[row.column.columnId] = element as HTMLTextAreaElement | null }"
              rows="2"
              :aria-label="$t('extensions.sheetCatalog.columnExpression', {index: row.index + 1})"
              :value="row.column.expression"
              @input="catalog.updateColumn(row.column.columnId, {expression: ($event.target as HTMLTextAreaElement).value}); trackCaret(row.column.columnId, $event.target as HTMLTextAreaElement)"
              @click="trackCaret(row.column.columnId, $event.target as HTMLTextAreaElement)"
              @keyup="trackCaret(row.column.columnId, $event.target as HTMLTextAreaElement)"
              @blur="trackCaret(row.column.columnId, $event.target as HTMLTextAreaElement)"
            ></textarea>
            <p v-if="row.error" class="error column-error" role="alert">{{ errorText(row.error) }}</p>
          </div>
          <span class="status-cell">
            <span class="status-badge" :class="row.error ? 'bad' : 'good'">{{ row.error ? $t("extensions.sheetCatalog.columnStatusInvalid") : $t("extensions.sheetCatalog.columnStatusValid") }}</span>
          </span>
          <div class="row-actions">
            <button type="button" :disabled="row.index === 0" :aria-label="$t('extensions.sheetCatalog.moveUp', {index: row.index + 1})" @click="catalog.moveColumn(row.column.columnId, -1)">↑</button>
            <button type="button" :disabled="row.index === catalog.draft.value.columns.length - 1" :aria-label="$t('extensions.sheetCatalog.moveDown', {index: row.index + 1})" @click="catalog.moveColumn(row.column.columnId, 1)">↓</button>
            <button type="button" class="danger-text" :aria-label="$t('extensions.sheetCatalog.removeColumn', {index: row.index + 1})" @click="catalog.removeColumn(row.column.columnId)">✕</button>
          </div>
        </li>
      </ol>
    </div>
    <div class="editor-foot">
      <button type="button" @click="catalog.addColumn()">{{ $t("extensions.sheetCatalog.addColumn") }}</button>
      <span class="syntax-hint">{{ $t("extensions.sheetCatalog.expressionSyntaxHint") }}</span>
    </div>
  </section>
</template>
<style scoped>
.column-editor{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden}
/* 卡片自身不设内边距：状态带、表头行与操作脚各自铺满，与冻结 Demo 的分区一致 */
.column-editor.panel{padding:0}
.editor-head{display:flex;align-items:center;gap:var(--space-2);padding:11px 14px;min-width:0}
.editor-head h3{margin:0;font-size:14px}
.editor-head .spacer{flex:1}
.compat-badge{font-size:12px;padding:3px 9px;border-radius:999px;white-space:nowrap}
.compat-badge.good{color:var(--color-success);background:var(--color-success-bg)}
.compat-badge.warn{color:var(--color-warning);background:var(--color-warning-bg)}
.compat-badge.bad{color:var(--color-danger);background:var(--color-danger-bg)}
.compat-badge.checking{color:var(--color-text-secondary);background:var(--color-bg-muted)}
.column-count{color:var(--color-text-muted);font-size:12px;white-space:nowrap}
.columns{overflow:auto;min-height:0;flex:1;max-height:330px}
/* 表头与数据行共用同一组 grid 轨道：任何一处的列宽改动都必须同步两处 */
.columns-head,.column-row{display:grid;grid-template-columns:34px minmax(110px,.62fr) minmax(250px,1.8fr) 92px 112px;gap:8px}
.columns-head{position:sticky;top:0;z-index:1;padding:8px 12px;background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:12px}
.column-list{list-style:none;margin:0;padding:0}
.column-row{padding:9px 12px;border-bottom:1px solid var(--color-border-subtle);align-items:start}
.column-row.is-error{background:var(--color-danger-bg)}
.order-cell{padding-top:9px;color:var(--color-text-secondary);font-size:12px;text-align:center}
.column-row input{width:100%;min-width:0;padding:7px 8px;border:1px solid var(--color-border-strong);border-radius:5px;font:inherit;font-size:13px;background:var(--color-bg-surface);color:var(--color-text-primary)}
.expression-cell{display:grid;gap:4px;min-width:0}
.column-row textarea{width:100%;min-width:0;min-height:52px;padding:7px 8px;border:1px solid var(--color-border-strong);border-radius:5px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.5;resize:vertical;background:var(--color-bg-surface);color:var(--color-text-primary)}
.column-error{margin:0;font-size:12px;line-height:1.5;color:var(--color-danger)}
.status-cell{padding-top:8px}
.status-badge{font-size:12px;padding:3px 8px;border-radius:999px;white-space:nowrap}
.status-badge.good{color:var(--color-success);background:var(--color-success-bg)}
.status-badge.bad{color:var(--color-danger);background:var(--color-danger-bg)}
.row-actions{display:flex;gap:4px;justify-content:flex-end;padding-top:2px}
.row-actions button{width:30px;min-height:30px;border:1px solid var(--color-border-strong);border-radius:6px;background:var(--color-bg-surface);font-size:13px;line-height:1}
.row-actions button:hover:not(:disabled){background:var(--color-bg-muted)}
.row-actions button.danger-text{color:var(--color-danger)}
.editor-foot{display:flex;align-items:center;gap:var(--space-3);padding:10px 14px;flex-wrap:wrap;min-width:0}
.editor-foot button{padding:0 var(--space-3);min-height:32px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.editor-foot button:hover{background:var(--color-bg-muted)}
.syntax-hint{color:var(--color-text-muted);font-size:12px;min-width:0}
@media (max-width: 720px){
  .columns-head{display:none}
  .column-row{grid-template-columns:28px minmax(0,1fr);gap:7px}
  .column-row > *:not(.order-cell){grid-column:2}
  .order-cell{padding-top:2px}
  .row-actions{justify-content:flex-start}
  .status-cell{padding-top:0}
}
</style>
