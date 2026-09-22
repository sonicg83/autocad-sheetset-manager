<script setup lang="ts">
// 组合属性编辑模态框（PLAN-DM-038 Task 8 / SPEC-DM-017 §5.3）。
//
// 与 DWG 命名共用 `TokenExpressionEditor` 骨架：左字段浏览器、右单行令牌编辑框、下实时预览。
// 契约：
// - 模态持有独立令牌缓冲：取消丢弃本轮编辑，保存才写回草稿；
// - 宽度与最大高度施加在外层对话框，正文独立滚动，底部「取消/保存组合」不参与滚动；
// - 预览使用示例值并明确标注，不冒充工程结果。
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import TokenExpressionEditor from "./TokenExpressionEditor.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {renderCompositionPreview, type DraftCompositionProperty, type DraftDocument, type DraftSegment} from "../../features/standards/draftModel";
import {compositionTokenFields, type TokenFieldTexts} from "../../features/standards/tokenFields";

const props = defineProps<{
  open: boolean;
  property: DraftCompositionProperty | null;
  document: DraftDocument;
}>();
const emit = defineEmits<{save: [segments: DraftSegment[]]; cancel: []}>();
const {t} = useI18n();

const card = ref<HTMLElement | null>(null);
const segments = ref<DraftSegment[]>([]);

watch(
  () => props.open,
  open => {
    if (!open || props.property === null) return;
    segments.value = props.property.segments.map(segment => ({...segment}));
  },
  {immediate: true},
);

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("cancel");
  },
});

const texts = computed<TokenFieldTexts>(() => ({
  systemLabels: {
    "sheet.number": t("standards.token.system.sheetNumber"),
    "sheet.title": t("standards.token.system.sheetTitle"),
  },
  placeholder: t("standards.token.samplePlaceholder"),
}));

const fields = computed(() =>
  props.property === null ? [] : compositionTokenFields(props.document, props.property.scope, texts.value),
);

const preview = computed(() => {
  if (props.property === null) return {text: "", diagnostics: []};
  return renderCompositionPreview(
    props.document,
    {...props.property, segments: segments.value},
    {
      subsetName: t("standards.token.sample.subsetName"),
      sheetNumber: t("standards.token.sample.sheetNumber"),
      sheetTitle: t("standards.token.sample.sheetTitle"),
      placeholder: t("standards.token.samplePlaceholder"),
    },
  );
});

const sampleRows = computed(() => [
  {label: t("standards.token.system.sheetNumber"), value: t("standards.token.sample.sheetNumber")},
  {label: t("standards.token.system.sheetTitle"), value: t("standards.token.sample.sheetTitle")},
]);

function save(): void {
  emit("save", segments.value.map(segment => ({...segment})));
}
</script>
<template>
  <div v-if="open && property" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card"
      class="composition-dialog"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-label="$t('standards.composition.title')"
      data-testid="composition-dialog"
    >
      <header class="dialog-head">
        <div class="head-text">
          <h2 class="dialog-title">{{ $t("standards.composition.dialogTitle", {name: property.name || property.property_id}) }}</h2>
          <p class="dialog-hint">{{ $t("standards.composition.hint") }}</p>
        </div>
        <span class="scope-badge">{{ property.scope }}</span>
      </header>
      <div class="dialog-body">
        <TokenExpressionEditor
          :segments="segments"
          :fields="fields"
          :label="$t('standards.composition.expression')"
          :preview-label="$t('standards.composition.preview')"
          :preview="preview.text"
          :sample-rows="sampleRows"
          :preview-invalid="preview.diagnostics.length > 0"
          @update:segments="segments = $event"
        />
      </div>
      <footer class="dialog-foot">
        <UiButton variant="secondary" data-testid="cancel-composition" @click="emit('cancel')">
          {{ $t("standards.composition.cancel") }}
        </UiButton>
        <UiButton variant="primary" data-testid="save-composition" @click="save">
          {{ $t("standards.composition.save") }}
        </UiButton>
      </footer>
    </div>
  </div>
</template>
<style scoped>
.composition-dialog{
  display:flex;flex-direction:column;
  width:min(1040px,calc(100vw - 32px));max-height:calc(100vh - 42px);
  overflow:hidden;outline:none;
  background:var(--color-bg-surface);color:var(--color-text-primary);
  border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3);
}
.dialog-head{display:flex;flex:0 0 auto;align-items:flex-start;gap:var(--space-3);padding:var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.head-text{display:grid;gap:var(--space-1);min-width:0}
.dialog-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.dialog-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.scope-badge{flex:0 0 auto;padding:0 var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);font-size:var(--font-label);color:var(--color-text-secondary)}
.dialog-body{flex:1 1 auto;min-height:0;overflow:auto;padding:var(--space-4)}
.dialog-foot{display:flex;flex:0 0 auto;justify-content:flex-end;gap:var(--space-2);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);background:var(--color-bg-muted)}
</style>
