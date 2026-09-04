<script setup lang="ts">
// 标签③ 修订历史：永久修订列表与恢复为新修订（受控组件，业务状态仍由 App.vue 持有）
import type {RestorePreview,Revision} from "../api/contracts";
import RevisionHistoryPanel from "../components/RevisionHistoryPanel.vue";
defineProps<{revisions:Revision[];restorePreview:RestorePreview|null;executing:boolean;isWorkspaceLoading:boolean}>();
defineEmits<{preview:[revision:Revision];restore:[]}>();
</script>
<template>
  <section class="revisions-view" role="tabpanel" id="panel-revisions" aria-label="修订历史">
    <template v-if="!isWorkspaceLoading">
      <RevisionHistoryPanel v-if="revisions.length" :revisions="revisions" :restore-preview="restorePreview" :executing="executing" @preview="$emit('preview',$event)" @restore="$emit('restore')" />
      <p v-else class="empty">暂无修订历史</p>
    </template>
  </section>
</template>
<style scoped>
.revisions-view{display:block}
.empty{padding:var(--space-5);text-align:center;color:var(--color-text-muted);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
</style>
