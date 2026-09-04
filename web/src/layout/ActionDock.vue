<script setup lang="ts">
// 全局底部操作栏（SPEC-DM-006 §4.1/§6.9）：草稿计数芯片 + 草稿栈浮窗（内嵌 DraftActionsPanel）+ 撤销/重做 + 预览/确认写入
// 禁用原因以内联文本 + title 双通道呈现；确认写入仅当 writeNeedsModal 上抛 App 打开发布模态
import {nextTick,onBeforeUnmount,onMounted,ref} from "vue";
import type {DraftAction} from "../api/contracts";
import DraftActionsPanel from "../components/DraftActionsPanel.vue";

const props=defineProps<{
  commandCount:number;actions:DraftAction[];cursor:number;stale:boolean;staleReasons:string[];corrupted:boolean;
  saveStatusText:string;saveFailed:boolean;canPreview:boolean;canWrite:boolean;writeDisabledReason:string;
  writeNeedsModal:boolean;previewing:boolean;writesDisabled:boolean;
}>();
const emit=defineEmits<{preview:[];write:[];undo:[];redo:[];clear:[];remove:[index:number];discard:[];reloadConflict:[];retrySave:[]}>();
const popOpen=ref(false);
const chipRef=ref<HTMLButtonElement|null>(null);
function togglePop(){popOpen.value=!popOpen.value}
// §7.2 抽屉模型：Esc 关闭浮窗并把焦点还给计数芯片（closePop 幂等）
function closePop(){if(!popOpen.value)return;popOpen.value=false;void nextTick(()=>chipRef.value?.focus())}
// 全局 Esc 兜底：焦点在浮窗外时也能关闭（模态遮罩自身 stopPropagation，互不干扰）
function onGlobalKeydown(e:KeyboardEvent){if(e.key==="Escape")closePop()}
// 确认写入：仅当 writeNeedsModal（有效预览可执行）时上抛，其余状态按 §6.9 矩阵禁用
function onWrite(){if(props.writeNeedsModal)emit("write")}
onMounted(()=>window.addEventListener("keydown",onGlobalKeydown));
onBeforeUnmount(()=>window.removeEventListener("keydown",onGlobalKeydown));
</script>
<template>
  <footer class="dock" role="contentinfo">
    <button type="button" class="draft-chip" ref="chipRef" :aria-expanded="popOpen" aria-controls="draft-pop" aria-haspopup="dialog" @click="togglePop">
      草稿 {{cursor}}/{{actions.length}}<span class="arr">▲</span>
    </button>
    <button type="button" class="dock-btn ghost" :disabled="stale||cursor===0" @click="emit('undo')">撤销</button>
    <button type="button" class="dock-btn ghost" :disabled="stale||cursor>=actions.length" @click="emit('redo')">重做</button>
    <span class="spacer"></span>
    <span v-if="writeDisabledReason" class="dock-reason" role="note">{{writeDisabledReason}}</span>
    <button type="button" class="dock-btn primary" :class="{loading:previewing}" :disabled="!canPreview" :title="canPreview?'':writeDisabledReason" @click="emit('preview')">预览变更</button>
    <button type="button" class="dock-btn danger" :disabled="!canWrite" :title="canWrite?'':writeDisabledReason" @click="onWrite">确认写入</button>
    <div v-if="popOpen" id="draft-pop" class="pop" role="dialog" aria-label="草稿动作栈">
      <DraftActionsPanel :actions="actions" :cursor="cursor" :command-count="commandCount" :stale="stale" :stale-reasons="staleReasons" :corrupted="corrupted" :writes-disabled="writesDisabled" :loading="false" @discard="emit('discard')" @reload-conflict="emit('reloadConflict')" @undo="emit('undo')" @redo="emit('redo')" @clear="emit('clear')" @preview="emit('preview')" @remove="emit('remove',$event)" />
      <div class="draft-save-status"><span class="save-status" :class="{error:saveFailed}">{{saveStatusText}}</span><button v-if="saveFailed" type="button" @click="emit('retrySave')">重试</button></div>
    </div>
  </footer>
</template>
<style scoped>
.dock{display:flex;align-items:center;gap:var(--space-4);padding:0 var(--space-4);height:52px;min-height:52px;background:var(--color-bg-surface);border-top:1px solid var(--color-border-subtle);flex-shrink:0;position:sticky;bottom:0;margin-top:auto;z-index:10}
.draft-chip{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 var(--space-3);border-radius:var(--radius-full);background:var(--color-bg-muted);border:none;color:var(--color-text-primary);font-family:inherit;font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap}
.draft-chip .arr{font-size:10px;color:var(--color-text-muted);transition:transform .15s}
.draft-chip[aria-expanded="true"] .arr{transform:rotate(180deg)}
.spacer{flex:1}
.dock-btn{height:34px;padding:0 var(--space-4);border-radius:var(--radius-md);border:1px solid transparent;font-family:inherit;font-size:14px;font-weight:500;cursor:pointer;white-space:nowrap}
.dock-btn.ghost{background:transparent;color:var(--color-text-secondary)}
.dock-btn.ghost:hover:not(:disabled){background:var(--color-bg-muted)}
.dock-btn.primary{background:var(--color-accent);color:var(--color-on-accent)}
.dock-btn.primary:hover:not(:disabled){background:var(--color-accent-hover)}
.dock-btn.danger{background:var(--color-danger);color:var(--color-on-accent)}
.dock-btn.danger:hover:not(:disabled){background:var(--color-danger)}
.dock-btn:disabled{cursor:not-allowed;opacity:.5}
.dock-btn.loading{opacity:.7}
.dock-reason{font-size:12px;color:var(--color-text-muted);max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pop{position:absolute;bottom:100%;left:var(--space-4);width:420px;max-width:calc(100vw - 32px);max-height:300px;overflow:auto;margin-bottom:var(--space-2);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3);padding:var(--space-3);z-index:100}
</style>
