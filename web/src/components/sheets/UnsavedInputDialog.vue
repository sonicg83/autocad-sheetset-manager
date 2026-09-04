<script setup lang="ts">
// 未提交输入保护三选一模态（SPEC-DM-015 任务 5，SPEC-DM-009 §6.2）。
// 独立实现，复用公共可访问模态样式与焦点管理（modal-mask/modal-card，焦点困绕、Esc=留在此处）；
// 不改 useConfirm 的 boolean 强确认协议。失效上下文禁止「加入草稿后继续」。
import {nextTick, ref, watch} from "vue";

const props = defineProps<{
  open: boolean;
  summary: string;   // 当前未提交内容描述（如「图纸 001 属性编辑」）
  canSave: boolean;  // 失效上下文禁止加入草稿
}>();
const emit = defineEmits<{saveAndContinue: []; discard: []; stay: []}>();
const card = ref<HTMLElement | null>(null);
const opener = ref<Element | null>(null);

watch(() => props.open, async (open) => {
  if (open) {
    opener.value = document.activeElement;
    await nextTick();
    card.value?.focus();
  } else {
    (opener.value as HTMLElement | null)?.focus?.();
  }
});

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") { e.stopPropagation(); emit("stay"); return; }
  if (e.key !== "Tab" || !card.value) return;
  // 焦点困绕：Tab 循环限制在模态内
  const items = Array.from(card.value.querySelectorAll<HTMLElement>("button")).filter((el) => !el.hasAttribute("disabled"));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onKeydown">
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="未提交输入" tabindex="-1" ref="card">
      <h2>未提交输入</h2>
      <p class="modal-message">{{ summary }} 有未保存的修改。仅存于内存缓冲不会跨会话保留；加入草稿后才可重开恢复。加入草稿会更新草稿投影并使之前的预览失效，需重新预览。</p>
      <div class="modal-actions">
        <button type="button" @click="emit('stay')">留在此处</button>
        <button type="button" @click="emit('discard')">放弃输入</button>
        <button type="button" class="primary" :disabled="!canSave" @click="emit('saveAndContinue')">加入草稿后继续</button>
      </div>
    </div>
  </div>
</template>
<style scoped>
.modal-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
</style>
