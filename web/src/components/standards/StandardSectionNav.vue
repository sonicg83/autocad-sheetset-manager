<script setup lang="ts">
// 编辑分区导航（PLAN-DM-035 Task 9 / SPEC-DM-016 §6.1）：分区顺序由 EDITOR_SECTIONS 固定。
// 切换分区只改视图——草稿缓冲由 StandardEditor 持有，子组件共享同一缓冲，因此切换不丢输入。
// 用原生 button + aria-current 表达当前分区，不假装成 tab 角色（没有 tabpanel 语义就不该用）。
import type {EditorSectionId} from "../../features/standards/draftModel";

const props = defineProps<{
  active: EditorSectionId;
  sections: Array<{id: EditorSectionId; labelKey: string; count?: number}>;
}>();
const emit = defineEmits<{select: [id: EditorSectionId]}>();
</script>
<template>
  <nav class="section-nav" :aria-label="$t('standards.editor.sectionsRegion')" data-testid="standard-section-nav">
    <ul class="section-list">
      <li v-for="(section, index) in props.sections" :key="section.id">
        <button
          type="button"
          class="section-button"
          :class="{active: section.id === props.active}"
          :aria-current="section.id === props.active ? 'true' : undefined"
          :data-testid="`editor-section-${section.id}`"
          @click="emit('select', section.id)"
        >
          <span class="section-order" aria-hidden="true">{{ index + 1 }}</span>
          <span class="section-label">{{ $t(section.labelKey) }}</span>
          <span v-if="section.count" class="section-count">{{ section.count }}</span>
        </button>
      </li>
    </ul>
  </nav>
</template>
<style scoped>
.section-nav{min-width:0}
.section-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.section-button{width:100%;display:flex;align-items:center;gap:var(--space-2);text-align:left;min-height:var(--min-tap-height);padding:var(--space-2) var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);color:var(--color-text-primary);cursor:pointer}
.section-button:hover{border-color:var(--color-border-strong)}
.section-button.active{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.section-order{color:var(--color-text-muted);font-size:var(--font-label)}
.section-count{font-size:var(--font-label);color:var(--color-text-secondary);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);padding:0 var(--space-2)}
/* 窄视口（PLAN-DM-039 Task 3，对照 SPEC-DM-017 编辑器 Demo）：分区导航改为单行水平滚动，
   按钮保持完整可访问名称与最小点击高度，不截短成只剩序号。 */
@media (max-width: 780px){
  .section-nav{overflow-x:auto}
  .section-list{grid-auto-flow:column;grid-auto-columns:max-content;gap:var(--space-2)}
  .section-button{width:auto;white-space:nowrap}
}
</style>
