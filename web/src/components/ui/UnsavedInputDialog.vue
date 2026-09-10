<script setup lang="ts">
// 未提交输入保护三选一模态（SPEC-DM-015 任务 5，SPEC-DM-009 §6.2）。
// 独立实现，复用公共可访问模态样式与焦点管理（modal-card，焦点困绕、Esc=留在此处）；
// 不改 useConfirm 的 boolean 强确认协议。失效上下文禁止「加入草稿后继续」。
//
// PLAN-DM-022 修订：由「页面内联遮罩」改为原生 <dialog showModal>。原因是闸门会与
// 其他模态重叠——从设置中心停用扩展时设置对话框是 top layer 的 showModal 模态，
// 内联遮罩既渲染在它之下又被它 inert，用户看到弹框却点不动（变相卡死）。原生模态
// 自带 top layer，会稳定叠在更下层模态之上；遮罩（::backdrop）、焦点圈闭与 Esc 归属
// 一并交给平台：Esc 只作用于最上层对话框，不会顺带触发下层窗口的关闭。
// 不写 role/aria-modal：原生模态自带 dialog 角色与模态语义，而本元素常驻 DOM
//（关窗即 display:none），显式属性会让 e2e 通用的 [role="dialog"][aria-modal="true"]
// 选择器同时命中隐藏的闸门与真正打开的确认模态（多元素命中）。
import {ref, watch} from "vue";

const props = defineProps<{
  open: boolean;
  summary: string;   // 当前未提交内容描述（如「图纸 001 属性编辑」）
  canSave: boolean;  // 失效上下文禁止加入草稿
}>();
const emit = defineEmits<{saveAndContinue: []; discard: []; stay: []}>();
const dialogEl = ref<HTMLDialogElement | null>(null);
const card = ref<HTMLElement | null>(null);
const opener = ref<Element | null>(null);

watch(() => props.open, (open) => {
  const dialog = dialogEl.value;
  if (open) {
    if (dialog === null || dialog.open) return;
    opener.value = document.activeElement;
    dialog.showModal();
    card.value?.focus();
    return;
  }
  if (dialog?.open) dialog.close();
  (opener.value as HTMLElement | null)?.focus?.();
});

function onKeydown(e: KeyboardEvent) {
  // Esc 不再在此处理：原生模态的关闭请求（cancel）自带「只作用于最上层」语义，
  // 由模板的 @cancel 映射为「留在此处」。此处只保留 Tab 焦点困绕。
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
  <dialog
    ref="dialogEl" class="gate-dialog"
    :aria-label="$t('shell.unsaved.title')"
    @cancel.prevent="emit('stay')" @keydown="onKeydown"
  >
    <div class="modal-card" tabindex="-1" ref="card">
      <h2>{{ $t("shell.unsaved.title") }}</h2>
      <p class="modal-message">{{ $t("shell.unsaved.message", { summary }) }}</p>
      <div class="modal-actions">
        <button type="button" @click="emit('stay')">{{ $t("shell.unsaved.stay") }}</button>
        <button type="button" @click="emit('discard')">{{ $t("shell.unsaved.discard") }}</button>
        <button type="button" class="primary" :disabled="!canSave" @click="emit('saveAndContinue')">{{ $t("shell.unsaved.saveAndContinue") }}</button>
      </div>
    </div>
  </dialog>
</template>
<style scoped>
.modal-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
</style>
