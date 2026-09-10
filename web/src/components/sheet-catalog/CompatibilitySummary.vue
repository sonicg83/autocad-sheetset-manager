<!-- 兼容性摘要（SPEC-DM-012 §7.2 区域 4）：缺少定义为阻断错误（可定位列），
     缺少值为带图纸数量的非阻断警告；全部经后端 message_key + 结构化参数渲染。 -->
<script setup lang="ts">
import {useI18n} from "vue-i18n";
import type {CatalogDiagnostic, SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

function text(diagnostic: CatalogDiagnostic): string {
  return t(diagnostic.messageKey, diagnostic.params);
}
</script>
<template>
  <section class="compatibility panel" :aria-label="$t('extensions.sheetCatalog.compatibilityLabel')">
    <h3>{{ $t("extensions.sheetCatalog.compatibilityLabel") }}</h3>
    <div v-if="(catalog.preview.value?.errors.length ?? 0) > 0" class="blocking" role="alert">
      <h4>{{ $t("extensions.sheetCatalog.blockingTitle") }}</h4>
      <ul>
        <li v-for="(diagnostic, index) in catalog.preview.value?.errors" :key="`e${index}`">{{ text(diagnostic) }}</li>
      </ul>
    </div>
    <p v-else-if="catalog.previewStatus.value === 'ready'" class="ok" role="status">{{ $t("extensions.sheetCatalog.noIssues") }}</p>
    <div v-if="(catalog.preview.value?.warnings.length ?? 0) > 0" class="warnings" role="status">
      <h4>{{ $t("extensions.sheetCatalog.warningTitle") }}</h4>
      <ul>
        <li v-for="(diagnostic, index) in catalog.preview.value?.warnings" :key="`w${index}`">{{ text(diagnostic) }}</li>
      </ul>
    </div>
    <p v-if="catalog.previewStatus.value === 'failed'" class="error notice" role="alert">{{ catalog.previewError.value }}</p>
  </section>
</template>
<style scoped>
.compatibility{display:flex;flex-direction:column;gap:var(--space-2);min-width:0}
.compatibility h3{margin:0;font-size:14px}
.blocking h4,.warnings h4{margin:0 0 4px;font-size:13px;color:var(--color-text-secondary)}
.blocking ul,.warnings ul{margin:0;padding-left:18px;font-size:13px}
.blocking{color:var(--color-danger)}
.warnings{color:var(--color-warning)}
.ok{margin:0;color:var(--color-success);font-size:13px}
</style>
