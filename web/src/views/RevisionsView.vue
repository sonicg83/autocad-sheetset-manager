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
      <!-- 空状态卡（§6.5 说明 + 下一步动作，动作即提示去标签①发起变更，不设跳转按钮以免打断） -->
      <div v-else class="empty-card">
        <h2 class="empty-title">暂无修订历史</h2>
        <p class="empty-desc">发布首个变更后，此处会记录每个可恢复的修订版本。</p>
        <p class="empty-action">前往「图纸」标签发起首个变更，发布后即可在此恢复。</p>
      </div>
    </template>
  </section>
</template>
<style scoped>
.revisions-view{display:block}
.empty-card{padding:var(--space-6);text-align:center;background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.empty-title{margin:0 0 var(--space-2);font-size:16px;color:var(--color-text-primary)}
.empty-desc{margin:0 0 var(--space-2);color:var(--color-text-secondary)}
.empty-action{margin:0;color:var(--color-text-muted);font-size:13px}
</style>
