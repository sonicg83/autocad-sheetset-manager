<script setup lang="ts">
// XLSX 辅助输入对话框（SPEC-DM-018 §5；PLAN-DM-036 Task 8）。
// 模板来自草稿固定的标准版本（后端按该版本生成，前端不拼模板）。导入是**全量覆盖**：
// 草稿已有用户输入时先说明「将覆盖项目属性、项目路径和全部图纸组」，用户确认后才上传；
// 取消不发任何写请求。失败时草稿与预览零变化，诊断按工作表/行/列定位并可读呈现。
// 前端不解析公式、不执行宏或外部链接，也不把 Data Validation 当作合法性证明。
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import type {ConfirmOptions} from "../../composables/useConfirm";
import type {CreationImportDiagnostic} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{
  store: CreationStore;
  open: boolean;
  confirmAction: (options: ConfirmOptions) => Promise<boolean>;
}>();
const emit = defineEmits<{close: []}>();
const {t, te} = useI18n();

const card = ref<HTMLElement | null>(null);
const file = ref<File | null>(null);
const succeeded = ref(false);

const templateUrl = computed(() => props.store.templateUrl());
const canImport = computed(() => file.value !== null && !props.store.importPending);

watch(
  () => props.open,
  open => {
    if (open) return;
    // 关闭即复位：文件选择与上一次的成功/失败呈现不得跨次残留
    file.value = null;
    succeeded.value = false;
    props.store.clearImportState();
  },
);

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("close");
  },
});

/** 诊断文案：已知码走创建域诊断语言包（与后端 `diagnostics[].code` 一一对应），未知码回退后端文本。 */
function diagnosticText(item: CreationImportDiagnostic): string {
  const key = `creation.diagnostic.${item.code}`;
  return te(key) ? t(key) : item.message;
}

function locationText(item: CreationImportDiagnostic): string {
  if (item.sheet !== "" && item.row !== null && item.column !== null) {
    return t("creation.xlsx.location", {sheet: item.sheet, row: item.row, column: item.column});
  }
  if (item.sheet !== "" && item.row !== null) {
    return t("creation.xlsx.locationRow", {row: item.row});
  }
  if (item.sheet !== "") return t("creation.xlsx.locationSheet", {sheet: item.sheet});
  if (item.row !== null && item.column !== null) {
    return t("creation.xlsx.locationCell", {row: item.row, column: item.column});
  }
  if (item.row !== null) return t("creation.xlsx.locationRow", {row: item.row});
  return t("creation.xlsx.locationNone");
}

function pickFile(event: Event): void {
  succeeded.value = false;
  props.store.clearImportState();
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

async function startImport(): Promise<void> {
  const picked = file.value;
  if (picked === null) return;
  if (props.store.hasInput()) {
    // 全量覆盖提醒：取消则保留草稿，且不发任何写请求
    const confirmed = await props.confirmAction({
      title: t("creation.xlsx.overwriteTitle"),
      message: t("creation.xlsx.overwriteMessage"),
      confirmText: t("creation.xlsx.overwriteConfirm"),
      cancelText: t("creation.xlsx.cancel"),
      danger: true,
    });
    if (!confirmed) return;
  }
  succeeded.value = await props.store.importWorkbook(picked);
  if (succeeded.value) file.value = null;
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card" class="modal-card xlsx-card" role="dialog" aria-modal="true"
      :aria-label="t('creation.xlsx.title')" tabindex="-1"
    >
      <h2>{{ t("creation.xlsx.title") }}</h2>
      <p class="xlsx-lead">{{ t("creation.xlsx.lead") }}</p>
      <div class="xlsx-row">
        <a
          class="xlsx-download" data-testid="creation-xlsx-template"
          :href="templateUrl" download
        >{{ t("creation.xlsx.download") }}</a>
        <span class="xlsx-note" data-testid="creation-xlsx-filename">
          {{ file === null ? t("creation.xlsx.noFile") : file.name }}
        </span>
      </div>
      <label class="xlsx-file-label" for="creation-xlsx-file">{{ t("creation.xlsx.fileLabel") }}</label>
      <input
        id="creation-xlsx-file" class="xlsx-file" type="file" accept=".xlsx"
        data-testid="creation-xlsx-file" @change="pickFile"
      >
      <p class="xlsx-boundary">{{ t("creation.xlsx.boundary") }}</p>
      <p v-if="succeeded" class="xlsx-status success" role="status">{{ t("creation.xlsx.success") }}</p>
      <template v-else-if="store.importMessage !== '' || store.importDiagnostics.length > 0">
        <p class="xlsx-status error" role="alert">{{ t("creation.xlsx.failed") }}</p>
        <p v-if="store.importMessage !== ''" class="xlsx-detail">{{ store.importMessage }}</p>
        <section v-if="store.importDiagnostics.length > 0" class="diagnostics" data-testid="creation-xlsx-diagnostics">
          <h3>{{ t("creation.xlsx.diagnosticsTitle", {count: store.importDiagnostics.length}) }}</h3>
          <ul>
            <li v-for="(item, index) in store.importDiagnostics" :key="`${item.code}-${index}`">
              <span class="location">{{ locationText(item) }}</span>
              <span class="message">{{ diagnosticText(item) }}</span>
            </li>
          </ul>
        </section>
      </template>
      <div class="modal-actions">
        <UiButton variant="secondary" @click="emit('close')">{{ t("creation.xlsx.cancel") }}</UiButton>
        <UiButton variant="primary" :disabled="!canImport" :loading="store.importPending" @click="startImport">
          {{ store.importPending ? t("creation.xlsx.importing") : t("creation.xlsx.import") }}
        </UiButton>
      </div>
    </div>
  </div>
</template>
<style scoped>
.xlsx-card{display:grid;gap:var(--space-3)}
.xlsx-lead{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.xlsx-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.xlsx-download{color:var(--color-accent);font-size:var(--font-label)}
.xlsx-note{color:var(--color-text-muted);font-size:var(--font-caption)}
.xlsx-file-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.xlsx-file{font-size:var(--font-label);color:var(--color-text-primary)}
.xlsx-boundary{margin:0;color:var(--color-text-muted);font-size:var(--font-caption);line-height:1.6}
.xlsx-status{margin:0;font-size:var(--font-label)}
.xlsx-status.success{color:var(--color-success)}
.xlsx-status.error{color:var(--color-danger)}
.xlsx-detail{margin:0;color:var(--color-text-secondary);font-size:var(--font-caption);line-height:1.6;word-break:break-word}
.diagnostics{display:grid;gap:var(--space-2)}
.diagnostics h3{margin:0;font-size:var(--font-card-title);color:var(--color-text-primary)}
.diagnostics ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2)}
.diagnostics li{display:grid;gap:2px;padding:var(--space-2);background:var(--color-danger-bg);border-radius:var(--radius-md)}
.diagnostics .location{font-size:var(--font-caption);color:var(--color-text-secondary)}
.diagnostics .message{font-size:var(--font-label);color:var(--color-danger)}
</style>
