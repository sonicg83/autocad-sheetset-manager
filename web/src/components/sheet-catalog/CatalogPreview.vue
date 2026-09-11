<!-- 预览表（SPEC-DM-012 §7.2 区域 5）：最多 20 行真实数据 + 总图纸数；宽列只在
     受控内容区横向滚动（overflow-x 限制在表容器），不造成整页横向溢出（SPEC §13）。
     PLAN-DM-023 Task 4（V3）：刷新预览上提到卡头，导出与反馈由 CatalogActions 作为
     卡底操作坞内嵌；卡片按冻结 Demo 压缩到 min-height:250px，表区吃掉剩余高度并
     自身滚动，因此 1440×1000 首屏同时可见预览标题、前几行数据与导出按钮。 -->
<script setup lang="ts">
import type {SheetCatalogController} from "../../composables/useSheetCatalog";
import CatalogActions from "./CatalogActions.vue";

defineProps<{catalog: SheetCatalogController}>();
</script>
<template>
  <section class="catalog-preview panel" :aria-label="$t('extensions.sheetCatalog.previewLabel')">
    <div class="preview-head">
      <h3>{{ $t("extensions.sheetCatalog.previewLabel") }}</h3>
      <span v-if="catalog.preview.value" class="total">{{ $t("extensions.sheetCatalog.previewTotal", {total: catalog.preview.value.totalRows}) }}<template v-if="catalog.preview.value.rows.length > 0">{{ " " + $t("extensions.sheetCatalog.previewShown", {shown: catalog.preview.value.rows.length}) }}</template></span>
      <span v-if="catalog.previewStatus.value === 'pending'" class="pending" role="status">{{ $t("extensions.sheetCatalog.previewPending") }}</span>
      <span class="spacer"></span>
      <button type="button" :disabled="catalog.previewStatus.value === 'pending'" @click="catalog.requestPreview()">{{ $t("extensions.sheetCatalog.refreshPreview") }}</button>
    </div>
    <p v-if="catalog.previewStatus.value === 'ready' && catalog.preview.value?.totalRows === 0" class="empty" role="status">{{ $t("extensions.sheetCatalog.previewEmptySheets") }}</p>
    <div v-if="catalog.preview.value && catalog.preview.value.rows.length > 0" class="table-window">
      <table>
        <thead>
          <tr>
            <th v-for="column in catalog.draft.value.columns" :key="column.columnId" scope="col">{{ column.header }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in catalog.preview.value.rows" :key="rowIndex">
            <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <!-- 导出与反馈作为预览卡底操作坞（V3：编辑→预览→导出保持同屏闭环） -->
    <CatalogActions :catalog="catalog" />
  </section>
</template>
<style scoped>
.catalog-preview{display:flex;flex-direction:column;gap:0;min-width:0;min-height:250px;flex:1 1 auto;overflow:hidden}
.catalog-preview.panel{padding:0}
.preview-head{display:flex;align-items:center;gap:var(--space-2);padding:11px 14px;flex-wrap:wrap;min-width:0;border-bottom:1px solid var(--color-border-subtle)}
.preview-head h3{margin:0;font-size:14px}
.preview-head .spacer{flex:1}
.total{color:var(--color-text-secondary);font-size:12px}
.pending{color:var(--color-text-muted);font-size:12px}
.preview-head button{padding:0 var(--space-3);min-height:30px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.preview-head button:hover:not(:disabled){background:var(--color-bg-muted)}
.empty{margin:0;padding:var(--space-5) var(--space-4);color:var(--color-text-muted);font-size:13px}
/* 横向滚动限制在受控表容器内；纵向吃掉卡片剩余高度并自身滚动 */
.table-window{overflow:auto;flex:1;min-height:0;max-height:300px;border-bottom:1px solid var(--color-border-subtle);max-width:100%}
.table-window table{min-width:100%}
.table-window td{white-space:nowrap}
</style>
