<script setup lang="ts">
// 标准管理页（PLAN-DM-035 Task 7 装配占位）：应用级表面，不属于工作区标签栏。
// 主从分栏标准库、详情与筛选在 Task 8 落地；本任务只提供页面骨架、返回入口
// 与 PLAN-DM-036 创建入口占位，保证导航与 E2E 契约先行。
import UiButton from "../components/ui/UiButton.vue";
defineEmits<{back: []; openCreateSheetset: []}>();
</script>
<template>
  <section class="standards-page" role="region" :aria-label="$t('standards.title')">
    <div class="standards-header">
      <h2 class="standards-title">{{ $t("standards.title") }}</h2>
      <UiButton variant="secondary" @click="$emit('back')">{{ $t("standards.back") }}</UiButton>
    </div>
    <p class="standards-placeholder">{{ $t("standards.placeholder") }}</p>
    <UiButton variant="secondary" @click="$emit('openCreateSheetset')">{{ $t("standards.createEntry") }}</UiButton>
  </section>
</template>
<style scoped>
/* 900×768 单列顺序（SPEC-DM-016）：标题/返回一行，说明与创建入口依次纵向排布 */
.standards-page{max-width:var(--card-max-width);margin:8vh auto;padding:var(--space-5);display:grid;gap:var(--space-4);justify-items:start}
.standards-header{display:flex;align-items:center;justify-content:space-between;width:100%;gap:var(--space-3)}
.standards-title{font-size:var(--font-page-title);margin:0;color:var(--color-text-primary)}
.standards-placeholder{color:var(--color-text-secondary);font-size:var(--font-label);margin:0;line-height:1.6}
</style>
