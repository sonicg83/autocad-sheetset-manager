<!-- 操作区（SPEC-DM-012 §7.2 区域 6）：刷新预览 + 导出 XLSX（唯一高强调操作）。
     导出前经桌面壳原生另存为（一次性授权）；无壳给出可见说明并禁用；取消不变更
     草稿/预览；成功只显示最终路径与"打开所在文件夹"（不显示 Artifact/修订/哈希，
     SPEC §10）；漂移/授权失效/写失败保留编辑并可重试（SPEC §11）。 -->
<script setup lang="ts">
import {useI18n} from "vue-i18n";
import type {SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

// 修订漂移需要先刷新预览再重试；其余失败可直接重试导出（重新取授权）
const needRepreview = () => props.catalog.exportState.errorCode === "REPREVIEW_REQUIRED";
const retryText = () => needRepreview() ? t("extensions.sheetCatalog.exportRepreviewHint") : "";
</script>
<template>
  <section class="catalog-actions panel" :aria-label="$t('extensions.sheetCatalog.actionsLabel')">
    <div class="actions-row">
      <button type="button" :disabled="catalog.previewStatus.value === 'pending'" @click="catalog.requestPreview()">{{ $t("extensions.sheetCatalog.refreshPreview") }}</button>
      <span class="spacer"></span>
      <button type="button" class="primary" :disabled="!catalog.exportReady.value" @click="catalog.exportXlsx()">
        {{ catalog.exportState.phase === "exporting" ? $t("extensions.sheetCatalog.exporting") : $t("extensions.sheetCatalog.exportButton") }}
      </button>
    </div>
    <p v-if="!catalog.hasShell.value" class="notice" role="status">{{ $t("extensions.sheetCatalog.noShellNotice") }}</p>
    <p v-else-if="catalog.exportStale.value" class="hint" role="status">{{ $t("extensions.sheetCatalog.exportStaleHint") }}</p>
    <p v-else-if="catalog.previewStatus.value === 'ready' && catalog.preview.value && !catalog.preview.value.executable" class="hint" role="status">{{ $t("extensions.sheetCatalog.exportNotExecutableHint") }}</p>
    <p v-if="catalog.actionError.value" class="error notice" role="alert">{{ catalog.actionError.value }}</p>
    <div v-if="catalog.exportState.phase === 'success'" class="success" role="status">
      <p class="success-path">
        <strong>{{ $t("extensions.sheetCatalog.exportSuccessTitle") }}</strong>
        <span class="mono">{{ catalog.exportState.outputPath }}</span>
      </p>
      <button type="button" @click="catalog.openExportFolder()">{{ $t("extensions.sheetCatalog.openFolder") }}</button>
    </div>
    <div v-if="catalog.exportState.phase === 'failed' && catalog.exportState.errorText" class="export-error" role="alert">
      <p>{{ catalog.exportState.errorText }}</p>
      <p v-if="retryText()" class="hint">{{ retryText() }}</p>
      <button type="button" @click="catalog.exportXlsx()">{{ $t("extensions.sheetCatalog.exportRetry") }}</button>
    </div>
  </section>
</template>
<style scoped>
.catalog-actions{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.actions-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.spacer{flex:1}
.actions-row button{padding:8px 16px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md)}
.actions-row button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.notice{margin:0;padding:10px 14px;border-radius:6px}
.hint{margin:0;color:var(--color-text-secondary);font-size:13px}
.success{border:1px solid var(--color-success);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.success-path{margin:0;display:flex;flex-direction:column;gap:2px;font-size:14px;min-width:0}
.success-path .mono{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:var(--color-text-secondary);overflow-wrap:anywhere}
.export-error{border:1px solid var(--color-danger);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);display:flex;flex-direction:column;gap:var(--space-2)}
.export-error p{margin:0;font-size:14px}
.export-error button{align-self:flex-start;padding:6px 14px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md)}
</style>
