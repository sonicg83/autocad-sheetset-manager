<script setup lang="ts">
// 令牌表达式编辑原语（PLAN-DM-038 Task 8 / SPEC-DM-017 §5.3、§6.2）。
//
// 组合属性与 DWG 命名共用同一骨架：左侧字段浏览器、右侧单行令牌编辑框、下方示例预览。
//
// 契约：
// - 固定文本直接输入；字段必须从浏览器插入为**不可拆分**令牌；
// - 令牌原子性：左右方向键与退格按令牌整体移动/删除，不会把令牌拆成字符；
// - 用户输入的 `{...}` 一律是固定文本，不解析为字段（没有 JSON/脚本/公式入口）；
// - 序列化始终是结构化 `DraftSegment[]`，组件只发出新数组，不持有草稿缓冲；
// - 预览文本由调用方渲染（真实求值仍在后端），本组件只负责展示与「示例」标注。
import {computed, nextTick, ref, watch} from "vue";
import {nextInstanceId} from "../ui/instanceId";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UiInput from "../ui/UiInput.vue";
import type {DraftSegment} from "../../features/standards/draftModel";
import type {TokenField} from "../../features/standards/tokenFields";

const props = defineProps<{
  segments: DraftSegment[];
  fields: TokenField[];
  /** 编辑框可见 label 与提示。 */
  label: string;
  hint?: string;
  previewLabel: string;
  preview: string;
  sampleRows?: Array<{label: string; value: string}>;
  /** 预览无效时的提示（前端只提示，发布仍以后端码为准）。 */
  previewInvalid?: boolean;
}>();
const emit = defineEmits<{"update:segments": [segments: DraftSegment[]]}>();
const {t} = useI18n();

const root = ref<HTMLElement | null>(null);
// 固定文字输入框的可见 label：编辑框标题即它的标签（点击标题聚焦到输入框）。
const literalId = nextInstanceId("token-literal");
const literalInput = ref<{focus: () => void} | null>(null);
/** 插入位置（0..segments.length），与片段数组一一对应；初始落在末尾（输入即追加）。 */
const caret = ref(props.segments.length);
const pending = ref("");
const search = ref("");

watch(
  () => props.segments.length,
  length => {
    if (caret.value > length) caret.value = length;
  },
);

const groups = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  const matched = props.fields.filter(
    field =>
      query === ""
      || field.label.toLocaleLowerCase().includes(query)
      || field.id.toLocaleLowerCase().includes(query),
  );
  const order: Array<TokenField["group"]> = ["subset", "sheet", "property"];
  return order
    .map(group => ({group, fields: matched.filter(field => field.group === group)}))
    .filter(entry => entry.fields.length > 0);
});

/** 令牌显示文本：属性/系统字段用字段名，固定文本原样显示。 */
function segmentLabel(segment: DraftSegment): string {
  if (segment.literal !== undefined) return segment.literal;
  const id = segment.property_id ?? segment.system_field ?? "";
  return props.fields.find(field => field.id === id)?.label ?? id;
}

/** 令牌显示文本：字段令牌带花括号，固定文本原样显示。 */
function segmentText(segment: DraftSegment): string {
  if (segment.literal !== undefined) return segmentLabel(segment);
  return ["{", segmentLabel(segment), "}"].join("");
}

function emitSegments(next: DraftSegment[]): void {
  emit("update:segments", next);
}

function insert(segment: DraftSegment): void {
  const next = [...props.segments];
  const position = Math.min(Math.max(caret.value, 0), next.length);
  next.splice(position, 0, segment);
  emitSegments(next);
  caret.value = position + 1;
}

function insertField(field: TokenField): void {
  // 先提交未落盘的固定文本，保证「先输入的文字在光标之前」的直觉顺序。
  if (pending.value !== "") commitLiteral();
  insert(
    field.system
      ? field.format === undefined
        ? {system_field: field.id}
        : {system_field: field.id, format: field.format}
      : {property_id: field.id},
  );
  void nextTick(() => literalInput.value?.focus());
}

function commitLiteral(): void {
  const text = pending.value;
  if (text === "") return;
  pending.value = "";
  insert({literal: text});
}

function removeAt(index: number): void {
  const next = [...props.segments];
  if (index < 0 || index >= next.length) return;
  next.splice(index, 1);
  emitSegments(next);
  caret.value = Math.max(0, Math.min(caret.value, next.length) - (index < caret.value ? 1 : 0));
}

function onLiteralInput(value: string): void {
  pending.value = value;
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter") {
    event.preventDefault();
    commitLiteral();
    return;
  }
  if (pending.value !== "") return;
  if (event.key === "Backspace" && caret.value > 0) {
    event.preventDefault();
    removeAt(caret.value - 1);
    return;
  }
  if (event.key === "ArrowLeft" && caret.value > 0) {
    event.preventDefault();
    caret.value -= 1;
    return;
  }
  if (event.key === "ArrowRight" && caret.value < props.segments.length) {
    event.preventDefault();
    caret.value += 1;
  }
}

function clearAll(): void {
  pending.value = "";
  caret.value = 0;
  emitSegments([]);
}
</script>
<template>
  <div ref="root" class="token-editor" data-testid="token-editor">
    <aside class="field-browser" :aria-label="$t('standards.token.browserLabel')">
      <h3 class="browser-title">{{ $t("standards.token.browserTitle") }}</h3>
      <UiInput v-model="search" :label="$t('standards.token.search')" data-testid="token-search" />
      <div v-for="entry in groups" :key="entry.group" class="field-group">
        <p class="field-group-title">{{ $t(`standards.token.group.${entry.group}`) }}</p>
        <div class="field-buttons">
          <UiButton
            v-for="field in entry.fields"
            :key="field.id"
            variant="secondary"
            size="compact"
            :data-testid="`token-field-${field.id}`"
            @click="insertField(field)"
          >{{ field.label }} · {{ field.sample }}</UiButton>
        </div>
      </div>
    </aside>
    <div class="editor-stack">
      <div class="editor-card">
        <label class="editor-label" :for="literalId">{{ label }}</label>
        <p v-if="hint" class="editor-hint">{{ hint }}</p>
        <div
          class="token-line"
          role="group"
          :aria-label="label"
          data-testid="token-line"
          @click="caret = segments.length"
        >
          <template v-for="(segment, index) in segments" :key="`${index}-${segmentLabel(segment)}`">
            <span v-if="caret === index" class="token-caret" data-testid="token-caret" aria-hidden="true"></span>
            <span
              class="token"
              :class="{'token--literal': segment.literal !== undefined}"
              tabindex="-1"
              :data-testid="`token-${index}`"
              :title="$t('standards.token.removeHint')"
              @click.stop="caret = index + 1"
              @dblclick.stop="removeAt(index)"
            >{{ segmentText(segment) }}</span>
          </template>
          <span v-if="caret === segments.length" class="token-caret" data-testid="token-caret" aria-hidden="true"></span>
          <input
            :id="literalId"
            class="literal-input"
            :value="pending"
            :placeholder="$t('standards.token.literalPlaceholder')"
            data-testid="token-literal"
            @input="onLiteralInput(($event.target as HTMLInputElement).value)"
            @keydown="onKeydown"
            @blur="commitLiteral"
          >
        </div>
        <div class="editor-actions">
          <span class="small-note">{{ $t("standards.token.hint") }}</span>
          <UiButton variant="secondary" size="compact" data-testid="token-clear" @click="clearAll">
            {{ $t("standards.token.clear") }}
          </UiButton>
        </div>
      </div>
      <div class="preview-card">
        <div class="preview-head">
          <strong>{{ previewLabel }}</strong>
          <span class="preview-badge" :class="{'preview-badge--invalid': previewInvalid}" data-testid="token-preview-state">
            {{ previewInvalid ? $t("standards.token.previewInvalid") : $t("standards.token.previewSample") }}
          </span>
        </div>
        <p class="preview-content" data-testid="token-preview">{{ preview }}</p>
        <div v-if="sampleRows && sampleRows.length > 0" class="sample-values" data-testid="token-samples">
          <div v-for="row in sampleRows" :key="row.label" class="sample-row">
            <span class="sample-label">{{ row.label }}</span>
            <code class="sample-value">{{ row.value }}</code>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.token-editor{display:grid;grid-template-columns:minmax(200px,260px) minmax(0,1fr);gap:var(--space-4);align-items:start;min-width:0}
.field-browser{display:grid;gap:var(--space-2);align-content:start}
.browser-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.field-group{display:grid;gap:var(--space-1)}
.field-group-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.field-buttons{display:flex;flex-wrap:wrap;gap:var(--space-1)}
.editor-stack{display:grid;gap:var(--space-3);min-width:0}
.editor-card,.preview-card{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.editor-label{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.editor-hint{margin:0;font-size:var(--font-label);color:var(--color-text-muted)}
.token-line{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-1);min-height:var(--input-height);padding:var(--space-1) var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);cursor:text}
.token{display:inline-flex;align-items:center;padding:0 var(--space-2);border:1px solid var(--color-accent);border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-primary);font-size:var(--font-label);white-space:nowrap;user-select:none}
.token--literal{border-color:var(--color-border-strong);color:var(--color-text-secondary)}
.token-caret{display:inline-block;height:var(--space-4);border-left:1px solid var(--color-accent)}
.literal-input{flex:1 1 20%;border:0;outline:none;background:transparent;color:var(--color-text-primary);font-family:var(--font-ui);font-size:var(--input-font-size);height:var(--input-height)}
.editor-actions{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.small-note{flex:1 1 auto;min-width:var(--standards-hint-min-width);font-size:var(--font-label);color:var(--color-text-muted)}
.preview-head{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2)}
.preview-badge{padding:0 var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);font-size:var(--font-label);color:var(--color-text-secondary)}
.preview-badge--invalid{border-color:var(--color-danger);color:var(--color-danger)}
.preview-content{margin:0;padding:var(--space-2);border:1px dashed var(--color-border-strong);border-radius:var(--radius-md);font-family:var(--font-mono);font-size:var(--input-font-size);color:var(--color-text-primary);overflow-wrap:anywhere}
.sample-values{display:grid;gap:var(--space-1)}
.sample-row{display:flex;align-items:center;gap:var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.sample-label{width:20%}
.sample-value{font-family:var(--font-mono);color:var(--color-text-primary)}
@media (max-width: 780px){
  .token-editor{grid-template-columns:minmax(0,1fr)}
}
</style>
