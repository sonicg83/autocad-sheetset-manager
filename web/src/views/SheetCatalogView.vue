// 图纸目录页最小边界（PLAN-DM-020 Task 10 / ARCH-DM-006 §7）。
// 只承载已加载扩展的页面状态容器与状态区域：名称/描述经清单 name_key/
// description_key 由宿主 i18n 渲染，生命周期状态按九值登记键呈现；
// 模板编辑、字段浏览与导出交互由 Task 11 的 useSheetCatalog 填充。
// 「停用扩展」是本页状态区域的控制入口：经 App 的全局未提交输入闸门后
// PATCH /api/extensions/{id}/state，停用成功即移除页面入口（ARCH-DM-006 §7）。
<script setup lang="ts">
import {computed} from "vue";
import type {ExtensionSummary} from "../api/contracts";

const props = defineProps<{extension: ExtensionSummary}>();
const emit = defineEmits<{toggleEnabled: [extensionId: string, enabled: boolean]}>();

const statusKey = computed(() => `extensions.status.${props.extension.status}`);
</script>
<template>
  <section class="sheet-catalog" :aria-label="$t(extension.name_key)">
    <header class="catalog-head">
      <h2>{{ $t(extension.name_key) }}</h2>
      <p class="catalog-desc">{{ $t(extension.description_key) }}</p>
      <p class="catalog-meta">v{{ extension.version }} · {{ $t(statusKey) }}</p>
    </header>
    <div class="catalog-status" role="status">
      <p>{{ $t("extensions.page.ready") }}</p>
      <button type="button" @click="emit('toggleEnabled', extension.extension_id, false)">{{ $t("extensions.page.disable") }}</button>
    </div>
  </section>
</template>
<style scoped>
.sheet-catalog{display:flex;flex-direction:column;gap:var(--space-4);min-height:0}
.catalog-head{display:flex;flex-direction:column;gap:var(--space-2)}
.catalog-head h2{margin:0;font-size:18px;color:var(--color-text-primary)}
.catalog-desc{margin:0;color:var(--color-text-secondary);font-size:14px}
.catalog-meta{margin:0;color:var(--color-text-muted);font-size:12px}
.catalog-status{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.catalog-status p{margin:0;color:var(--color-text-secondary);font-size:14px}
</style>
