<!-- 预览表（SPEC-DM-012 §7.2 区域 5）：最多 20 行真实数据 + 过滤后的总行数；命中过滤
     时在同一卡头追加可见「已过滤 N 张图纸」（R14：不新增布局区域，filtered_rows=0 时不出现，
     SPEC §8.1）。总数与过滤提示始终来自同一份预览（M6），进行中状态只额外显示
     「正在更新预览…」，不隐藏或改写已经展示的那组数字。宽列只在受控内容区横向滚动（overflow-x 限制在表容器），不造成整页横向
     溢出（SPEC §13）。
     PLAN-DM-023 Task 4（V3）：刷新预览上提到卡头，导出与反馈由 CatalogActions 作为
     卡底操作坞内嵌；卡片按冻结 Demo 压缩到 min-height:250px，表区吃掉剩余高度并
     自身滚动，因此 1440×1000 首屏同时可见预览标题、前几行数据与导出按钮。 -->
<script setup lang="ts">
import {computed} from "vue";
import type {SheetCatalogController} from "../../composables/useSheetCatalog";
import CatalogActions from "./CatalogActions.vue";
import UiButton from "../ui/UiButton.vue";

const props = defineProps<{catalog: SheetCatalogController}>();
// 过滤计数与总数文案同源：两者都取自当前展示的那份预览。只让 ready 态生效会让进行中
// （或失败但保留旧预览）时出现"输出 24 张图纸"却没有"已过滤 1 张图纸"的自相矛盾（M6）。
const filteredCount = computed(() => props.catalog.preview.value?.filteredRows ?? 0);
</script>
<template>
  <section class="catalog-preview panel" :aria-label="$t('extensions.sheetCatalog.previewLabel')">
    <div class="preview-head">
      <h3>{{ $t("extensions.sheetCatalog.previewLabel") }}</h3>
      <!-- 存在过滤时 total_rows 已是过滤后的输出行数：说"共 N 张图纸"会误导，改说"输出 N 张图纸"；
           被排除的数量在紧邻的位置以正文呈现（不只靠颜色或工具提示） -->
      <span v-if="catalog.preview.value" class="total">{{ filteredCount > 0 ? $t("extensions.sheetCatalog.previewTotalFiltered", {total: catalog.preview.value.totalRows}) : $t("extensions.sheetCatalog.previewTotal", {total: catalog.preview.value.totalRows}) }}<template v-if="catalog.preview.value.rows.length > 0">{{ " " + $t("extensions.sheetCatalog.previewShown", {shown: catalog.preview.value.rows.length}) }}</template></span>
      <span v-if="filteredCount > 0" class="filtered" role="status" data-testid="catalog-preview-filtered">{{ $t("extensions.sheetCatalog.previewFiltered", {count: filteredCount}) }}</span>
      <span v-if="catalog.previewStatus.value === 'pending'" class="pending" role="status">{{ $t("extensions.sheetCatalog.previewPending") }}</span>
      <span class="spacer"></span>
      <UiButton :disabled="catalog.previewStatus.value === 'pending'" @click="catalog.requestPreview()">{{ $t("extensions.sheetCatalog.refreshPreview") }}</UiButton>
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
.catalog-preview{display:flex;flex-direction:column;gap:0;min-width:0;min-height:var(--catalog-preview-min-height);flex:1 1 auto;overflow:hidden}
.catalog-preview.panel{padding:0}
.preview-head{display:flex;align-items:center;gap:var(--space-2);padding:11px 14px;flex-wrap:wrap;min-width:0;border-bottom:1px solid var(--color-border-subtle)}
/* 14px 卡标题借用组件层 --button-font-size：语义层没有 14px 非控件档位（收口责任 K） */
.preview-head h3{margin:0;font-size:var(--button-font-size)}
.preview-head .spacer{flex:1}
.total{color:var(--color-text-secondary);font-size:var(--font-caption)}
/* 已过滤 N 张图纸：预览卡头内的正文提示（R14），与总数同排但用中性强调色 */
.filtered{color:var(--color-text-muted);font-size:var(--font-caption);white-space:nowrap}
.pending{color:var(--color-text-muted);font-size:var(--font-caption)}
.empty{margin:0;padding:var(--space-5) var(--space-4);color:var(--color-text-muted);font-size:var(--font-label)}
/* 横向滚动限制在受控表容器内；纵向吃掉卡片剩余高度并自身滚动 */
.table-window{overflow:auto;flex:1;min-height:0;max-height:var(--catalog-preview-table-max-height);border-bottom:1px solid var(--color-border-subtle);max-width:100%}
.table-window table{min-width:100%}
.table-window td{white-space:nowrap}
</style>
