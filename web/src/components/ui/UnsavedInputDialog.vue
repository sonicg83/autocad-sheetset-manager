<script setup lang="ts">
// 未提交输入保护三选一模态（SPEC-DM-009 §6.2「未提交输入保护」；实现见 PLAN-DM-016 任务 2「会话缓冲、提交生命周期与统一输入保护」）。
// 独立实现，复用公共可访问模态样式与焦点管理（modal-card，焦点困绕、Esc=留在此处）；
// 不改 useConfirm 的 boolean 强确认协议。失效上下文禁止「加入草稿后继续」。
//
// SPEC-DM-011 修订「启停交互改进」：由「页面内联遮罩」改为原生 <dialog showModal>。原因是闸门会与
// 其他模态重叠——从设置中心停用扩展时设置对话框是 top layer 的 showModal 模态，
// 内联遮罩既渲染在它之下又被它 inert，用户看到弹框却点不动（变相卡死）。原生模态
// 自带 top layer，会稳定叠在更下层模态之上；遮罩（::backdrop）、焦点圈闭与 Esc 归属
// 一并交给平台：Esc 只作用于最上层对话框，不会顺带触发下层窗口的关闭。
// 不写 role/aria-modal：原生模态自带 dialog 角色与模态语义，而本元素常驻 DOM
//（关窗即 display:none），显式属性会让 e2e 通用的 [role="dialog"][aria-modal="true"]
// 选择器同时命中隐藏的闸门与真正打开的确认模态（多元素命中）。
import {ref, watch} from "vue";
import {useDialogFocus} from "./dialogFocus";

const props = defineProps<{
  open: boolean;
  summary: string;   // 当前未提交内容描述（如「图纸 001 属性编辑」）
  canSave: boolean;  // 失效上下文禁止加入草稿
  // 直接保存页面（如标准草稿编辑器）可覆盖正文与主操作文案：默认文案是草稿流语义
  // （“加入草稿后继续”），直接保存流需要“保存并离开”，但三选一结构与门禁语义同一。
  message?: string;
  saveLabel?: string;
}>();
const emit = defineEmits<{saveAndContinue: []; discard: []; stay: []}>();
const dialogEl = ref<HTMLDialogElement | null>(null);
const card = ref<HTMLElement | null>(null);
const opener = ref<Element | null>(null);

// 原生模态生命周期（showModal/close）留在本组件，而且**必须先于焦点工具运行**：打开时焦点工具
// 需要一个已经 showModal 的容器（否则对话框还没进 top layer，内部元素无法聚焦）；关闭时需要
// 一个已经 close 的容器（否则模态仍让页面处于 inert，归还焦点会被浏览器拒绝）。两个 watch 都是
// post flush，回调按注册顺序执行，所以本 watch 必须写在 useDialogFocus 之前。
watch(() => props.open, (open) => {
  const dialog = dialogEl.value;
  if (open) {
    if (dialog === null || dialog.open) return;
    // 必须早于 showModal：原生模态会把焦点移进对话框，之后再读 activeElement 拿到的就不是开启控件
    opener.value = document.activeElement;
    dialog.showModal();
    return;
  }
  if (dialog?.open) dialog.close();
});

// 焦点管理统一交给 dialogFocus.ts（Task 9 Step 3）：Tab 圈闭不再手写。
// Esc 仍不在此处理——原生模态的关闭请求（cancel）自带「只作用于最上层」语义，由模板的 @cancel
// 映射为「留在此处」；工具在没有 onEscape 时对 Escape 完全无操作（不阻止默认、不停止传播）。
const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  // 保持既有落点：打开时聚焦对话框本身（而不是首个按钮），不属于行为变化。
  initialFocus: card,
  // 显式交还上面捕获的 opener：工具内部的 opener 是在 showModal 之后读的 activeElement，
  // 那时焦点已进对话框，不能作为归还目标。
  returnFocus: () => opener.value as HTMLElement | null,
});
</script>
<template>
  <dialog
    ref="dialogEl" class="gate-dialog"
    :aria-label="$t('shell.unsaved.title')"
    @cancel.prevent="emit('stay')" @keydown="onDialogKeydown"
  >
    <div class="modal-card" tabindex="-1" ref="card">
      <h2>{{ $t("shell.unsaved.title") }}</h2>
      <p class="modal-message">{{ message ?? $t("shell.unsaved.message", { summary }) }}</p>
      <div class="modal-actions">
        <button type="button" @click="emit('stay')">{{ $t("shell.unsaved.stay") }}</button>
        <button type="button" @click="emit('discard')">{{ $t("shell.unsaved.discard") }}</button>
        <button type="button" class="primary" :disabled="!canSave" @click="emit('saveAndContinue')">{{ saveLabel ?? $t("shell.unsaved.saveAndContinue") }}</button>
      </div>
    </div>
  </dialog>
</template>
<style scoped>
.modal-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
</style>
