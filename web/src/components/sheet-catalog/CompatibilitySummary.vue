<!-- 兼容性摘要（SPEC-DM-012 §7.2 区域 4）：缺少定义为阻断错误（可定位列），
     缺少值为带图纸数量的非阻断警告；全部经后端 message_key + 结构化参数渲染。
     PLAN-DM-023 Task 4（V2）：去掉独立 `.panel` 外观，改为嵌在输出列卡内的紧凑整行
     状态带，按 ok / warning / error / 失败 / 检查中取色；region 名称保留，避免牺牲
     导航语义。判定统一来自 catalogCompatibility，不在此复制诊断计算。 -->
<script setup lang="ts">
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import {catalogCompatibility} from "./catalogCompatibility";
import type {CatalogDiagnostic, SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

const compat = computed(() => catalogCompatibility(props.catalog));

const title = computed(() => {
  switch (compat.value.tone) {
    case "ok": return t("extensions.sheetCatalog.noIssues");
    case "warning": return t("extensions.sheetCatalog.warningTitle");
    case "error": return t("extensions.sheetCatalog.blockingTitle");
    case "failed": return t("extensions.sheetCatalog.previewFailedTitle");
    default: return t("extensions.sheetCatalog.previewPending");
  }
});

// 详细正文：阻断错误优先于警告；预览请求失败时显示本地化错误正文
const messages = computed<CatalogDiagnostic[]>(() => {
  if (compat.value.tone === "error") return compat.value.errors;
  if (compat.value.tone === "warning") return compat.value.warnings;
  return [];
});

// 状态不只靠颜色：阻断与失败用 alert，其余用 status
const liveRole = computed(() => (compat.value.tone === "error" || compat.value.tone === "failed" ? "alert" : "status"));

function text(diagnostic: CatalogDiagnostic): string {
  return t(diagnostic.messageKey, diagnostic.params);
}
</script>
<template>
  <section class="compatibility" :class="`tone-${compat.tone}`" :aria-label="$t('extensions.sheetCatalog.compatibilityLabel')">
    <p class="compat-line" :role="liveRole">
      <strong class="compat-title">{{ title }}</strong>
      <template v-if="compat.tone === 'failed'">
        <span class="compat-message">{{ catalog.previewError.value }}</span>
      </template>
      <template v-else>
        <span v-for="(diagnostic, index) in messages" :key="`m${index}`" class="compat-message">{{ text(diagnostic) }}</span>
      </template>
    </p>
  </section>
</template>
<style scoped>
.compatibility{display:flex;min-width:0;border-bottom:1px solid var(--color-border-subtle)}
.compat-line{display:flex;flex-wrap:wrap;gap:2px 12px;margin:0;padding:10px 14px;font-size:13px;line-height:1.6;min-width:0}
.compat-title{flex:0 0 auto;font-weight:600}
.compat-message{min-width:0;overflow-wrap:anywhere}
.tone-ok{background:var(--color-success-bg);color:var(--color-success)}
.tone-warning{background:var(--color-warning-bg);color:var(--color-warning)}
.tone-error,.tone-failed{background:var(--color-danger-bg);color:var(--color-danger)}
.tone-checking{background:var(--color-bg-muted);color:var(--color-text-secondary)}
</style>
