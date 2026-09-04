<script setup lang="ts">
// 非模态通知宿主（SPEC-DM-006 §6.6）：aria-live="polite" 容器；ok 项 role="status"、fail 项 role="alert"；
// 每项含关闭 ✕ 与可选"查看"按钮（emit jump，App 调 openOverlay(tab)）
import type {Toast} from "../../composables/useToast";
defineProps<{toasts:Toast[]}>();
const emit=defineEmits<{dismiss:[id:number];jump:[tab:string]}>();
</script>
<template>
  <div class="toast-host" aria-live="polite">
    <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.type" :role="toast.type==='ok'?'status':'alert'">
      <div class="toast-main">
        <strong>{{toast.title}}</strong>
        <span>{{toast.body}}</span>
      </div>
      <div class="toast-actions">
        <button v-if="toast.jumpTab" type="button" @click="emit('jump',toast.jumpTab)">查看</button>
        <button type="button" class="toast-close" @click="emit('dismiss',toast.id)">✕</button>
      </div>
    </div>
  </div>
</template>
<style scoped>
.toast-host{position:fixed;top:var(--space-5);right:var(--space-5);z-index:1100;display:flex;flex-direction:column;gap:var(--space-2);max-width:360px}
.toast{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-radius:var(--radius-md);box-shadow:var(--shadow-2);border:1px solid var(--color-border-subtle);background:var(--color-bg-surface);color:var(--color-text-primary)}
.toast.ok{border-left:4px solid var(--color-success)}
.toast.fail{border-left:4px solid var(--color-danger)}
.toast-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.toast-main strong{font-size:14px}
.toast-main span{font-size:13px;color:var(--color-text-secondary);overflow-wrap:anywhere}
.toast-actions{display:flex;align-items:center;gap:var(--space-2);flex-shrink:0}
.toast-actions button{padding:4px 10px;font-size:12px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer}
.toast-close{min-width:26px}
@media (prefers-reduced-motion:no-preference){
  .toast{animation:toast-in .18s ease-out}
  @keyframes toast-in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
}
</style>
