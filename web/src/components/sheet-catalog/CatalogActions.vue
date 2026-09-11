<!-- 预览卡底部操作坞（SPEC-DM-012 §7.2 区域 6；PLAN-DM-023 Task 4 收敛）：
     导出 XLSX（唯一高强调操作）+ 一致性/过期/失败/成功反馈。刷新按钮已上提到预览
     卡头（由 CatalogPreview 装配），本组件不再作为与预览平级的独立卡片。
     导出前经桌面壳原生另存为（一次性授权）；无壳给出可见说明并禁用；取消不变更
     草稿/预览；成功只显示最终路径与"打开所在文件夹"（不显示 Artifact/修订/哈希，
     SPEC §10）；漂移/授权失效/写失败保留编辑并可重试（SPEC §11）。 -->
<script setup lang="ts">
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import type {SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

// 修订漂移需要先刷新预览再重试；其余失败可直接重试导出（重新取授权）
const needRepreview = () => props.catalog.exportState.errorCode === "REPREVIEW_REQUIRED";
const retryText = () => needRepreview() ? t("extensions.sheetCatalog.exportRepreviewHint") : "";

// 一致性反馈：无壳 → 过期 → 阻断 → 预览失败 → 与草稿/工作区修订一致
const summaryText = computed(() => {
  if (!props.catalog.hasShell.value) return t("extensions.sheetCatalog.noShellNotice");
  if (props.catalog.exportStale.value) return t("extensions.sheetCatalog.exportStaleHint");
  const preview = props.catalog.preview.value;
  if (props.catalog.previewStatus.value === "ready" && preview && !preview.executable) return t("extensions.sheetCatalog.exportNotExecutableHint");
  if (props.catalog.previewStatus.value === "failed") return t("extensions.sheetCatalog.previewFailedTitle");
  return t("extensions.sheetCatalog.exportConsistentHint");
});
</script>
<template>
  <section class="actions-dock" :aria-label="$t('extensions.sheetCatalog.actionsLabel')">
    <div class="dock-row">
      <span class="dock-summary" role="status">{{ summaryText }}</span>
      <span class="spacer"></span>
      <button type="button" class="primary" :disabled="!catalog.exportReady.value" @click="catalog.exportXlsx()">
        {{ catalog.exportState.phase === "exporting" ? $t("extensions.sheetCatalog.exporting") : $t("extensions.sheetCatalog.exportButton") }}
      </button>
    </div>
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
.actions-dock{display:flex;flex-direction:column;gap:var(--space-2);min-width:0;padding:10px 14px}
.dock-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-width:0}
.dock-summary{color:var(--color-text-secondary);font-size:12px;min-width:0;overflow-wrap:anywhere}
.spacer{flex:1}
.dock-row button{padding:0 var(--space-4);min-height:34px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.dock-row button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.dock-row button.primary:hover:not(:disabled){background:var(--color-accent-hover)}
.notice{margin:0;padding:8px 12px;border-radius:6px}
.hint{margin:0;color:var(--color-text-secondary);font-size:13px}
.success{border:1px solid var(--color-success);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.success-path{margin:0;display:flex;flex-direction:column;gap:2px;font-size:13px;min-width:0}
.success-path .mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--color-text-secondary);overflow-wrap:anywhere}
.success button{padding:0 var(--space-3);min-height:30px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.export-error{border:1px solid var(--color-danger);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);display:flex;flex-direction:column;gap:var(--space-1)}
.export-error p{margin:0;font-size:13px}
.export-error button{align-self:flex-start;padding:0 var(--space-3);min-height:30px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface)}
</style>
