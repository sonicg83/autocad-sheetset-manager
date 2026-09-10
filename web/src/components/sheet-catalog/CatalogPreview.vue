<!-- 预览表（SPEC-DM-012 §7.2 区域 5）：最多 20 行真实数据 + 总图纸数；宽列只在
     受控内容区横向滚动（overflow-x 限制在表容器），不造成整页横向溢出（SPEC §13）。 -->
<script setup lang="ts">
import type {SheetCatalogController} from "../../composables/useSheetCatalog";

defineProps<{catalog: SheetCatalogController}>();
</script>
<template>
  <section class="catalog-preview panel" :aria-label="$t('extensions.sheetCatalog.previewLabel')">
    <div class="preview-head">
      <h3>{{ $t("extensions.sheetCatalog.previewLabel") }}</h3>
      <span v-if="catalog.preview.value" class="total">{{ $t("extensions.sheetCatalog.previewTotal", {total: catalog.preview.value.totalRows}) }}<template v-if="catalog.preview.value.rows.length > 0">{{ " " + $t("extensions.sheetCatalog.previewShown", {shown: catalog.preview.value.rows.length}) }}</template></span>
      <span v-if="catalog.previewStatus.value === 'pending'" role="status">{{ $t("extensions.sheetCatalog.previewPending") }}</span>
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
  </section>
</template>
<style scoped>
.catalog-preview{display:flex;flex-direction:column;gap:var(--space-2);min-width:0;overflow:hidden}
.preview-head{display:flex;align-items:baseline;gap:var(--space-3);flex-wrap:wrap}
.preview-head h3{margin:0;font-size:14px}
.total{color:var(--color-text-secondary);font-size:13px}
.empty{margin:0;color:var(--color-text-muted);font-size:13px}
/* 横向滚动限制在受控表容器内 */
.table-window{overflow-x:auto;border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);max-width:100%}
.table-window table{min-width:100%}
.table-window td{white-space:nowrap}
</style>
