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
import UiButton from "../ui/UiButton.vue";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

// 修订漂移需要先刷新预览再重试；其余失败可直接重试导出（重新取授权）。
// 两个码的出路相同：REPREVIEW_REQUIRED 是预览摘要/修订漂移，EXTENSION_SETTINGS_CHANGED
// 是预览之后扩展设置已变（后端 409）。后者若只按通用失败处理，用户点"重试导出"
// 仍会重复提交同一份预览修订，后端必然再次 409——死循环且没有可见出路。
const REPREVIEW_ERROR_CODES = ["REPREVIEW_REQUIRED", "EXTENSION_SETTINGS_CHANGED"];
const needRepreview = () => REPREVIEW_ERROR_CODES.includes(props.catalog.exportState.errorCode);
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
      <UiButton variant="primary" :disabled="!catalog.exportReady.value" @click="catalog.exportXlsx()">
        {{ catalog.exportState.phase === "exporting" ? $t("extensions.sheetCatalog.exporting") : $t("extensions.sheetCatalog.exportButton") }}
      </UiButton>
    </div>
    <p v-if="catalog.actionError.value" class="error notice" role="alert">{{ catalog.actionError.value }}</p>
    <div v-if="catalog.exportState.phase === 'success'" class="success" role="status">
      <p class="success-path">
        <strong>{{ $t("extensions.sheetCatalog.exportSuccessTitle") }}</strong>
        <span class="mono">{{ catalog.exportState.outputPath }}</span>
      </p>
      <UiButton @click="catalog.openExportFolder()">{{ $t("extensions.sheetCatalog.openFolder") }}</UiButton>
    </div>
    <div v-if="catalog.exportState.phase === 'failed' && catalog.exportState.errorText" class="export-error" role="alert">
      <p>{{ catalog.exportState.errorText }}</p>
      <p v-if="retryText()" class="hint">{{ retryText() }}</p>
      <UiButton class="retry" @click="catalog.exportXlsx()">{{ $t("extensions.sheetCatalog.exportRetry") }}</UiButton>
    </div>
  </section>
</template>
<style scoped>
.actions-dock{display:flex;flex-direction:column;gap:var(--space-2);min-width:0;padding:10px 14px}
.dock-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-width:0}
.dock-summary{color:var(--color-text-secondary);font-size:var(--font-caption);min-width:0;overflow-wrap:anywhere}
.spacer{flex:1}
.notice{margin:0;padding:8px 12px;border-radius:var(--radius-sm)}
.hint{margin:0;color:var(--color-text-secondary);font-size:var(--font-label)}
.success{border:1px solid var(--color-success);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.success-path{margin:0;display:flex;flex-direction:column;gap:2px;font-size:var(--font-label);min-width:0}
.success-path .mono{font-family:var(--font-mono);font-size:var(--font-caption);color:var(--color-text-secondary);overflow-wrap:anywhere}
.export-error{border:1px solid var(--color-danger);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);display:flex;flex-direction:column;gap:var(--space-1)}
.export-error p{margin:0;font-size:var(--font-label)}
/* 重试按钮在纵向错误箱里不拉伸（UiButton 只承担外观，布局仍归本页） */
.export-error .retry{align-self:flex-start}
</style>
