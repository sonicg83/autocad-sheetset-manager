<script setup lang="ts">
import {computed,watch,ref} from "vue";
import {useI18n} from "vue-i18n";
import {useDialogFocus} from "./dialogFocus";
// reversibility 为稳定语义值（I18N-07）：显示文本经语言包渲染，不把中文枚举作为类型
const props=defineProps<{open:boolean;title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?: "reversible"|"irreversible";confirmDisabled?:boolean}>();
const emit=defineEmits<{confirm:[];cancel:[]}>();
const {t}=useI18n();
const checked=ref(false);const card=ref<HTMLElement|null>(null);
// 稳定值 → 语义键映射（不在模板拼接键）
const REVERSIBILITY_KEYS={reversible:"shell.modal.reversible",irreversible:"shell.modal.irreversible"} as const;
const reversibilityText=computed(()=>props.reversibility?t(REVERSIBILITY_KEYS[props.reversibility]):"");
const checkboxLabel=computed(()=>t("shell.modal.checkbox",{reversibility:reversibilityText.value||t("shell.modal.irreversible")}));
// 打开/关闭时重置勾选。与焦点无关，所以留在本组件（原来它与焦点逻辑挤在同一个 watch 里）。
watch(()=>props.open,()=>{checked.value=false;});
// 焦点管理统一交给 dialogFocus.ts（Task 9 Step 3）：打开送焦点、Tab 圈闭、关闭归还都不再手写。
// · `initialFocus: card`：保持既有落点（打开时聚焦对话框本身，而不是首个按钮），不属于行为变化。
// · `onEscape`：原 `onKeydown` 的 Escape 分支要 stopPropagation 并 emit("cancel")；工具自己不阻止、
//   不停止传播，把原始事件交给回调，所以这段语义在这里原样表达。
const {onDialogKeydown}=useDialogFocus({
  open:()=>props.open,
  container:card,
  initialFocus:card,
  onEscape:event=>{event.stopPropagation();emit("cancel");},
});
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onDialogKeydown">
    <div class="modal-card" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1" ref="card">
      <h2>{{title}} <span v-if="reversibility" class="modal-irr">{{reversibilityText}}</span></h2>
      <p class="modal-message">{{message}}</p>
      <ul v-if="impactLines?.length" class="modal-impact"><li v-for="line in impactLines" :key="line" class="mono">{{line}}</li></ul>
      <label v-if="requireCheckbox" class="modal-check"><input type="checkbox" v-model="checked">{{checkboxLabel}}</label>
      <div class="modal-actions">
        <button type="button" @click="emit('cancel')">{{cancelText??$t("shell.modal.cancel")}}</button>
        <button type="button" :class="{'modal-danger': danger}" :disabled="confirmDisabled || (Boolean(requireCheckbox)&&!checked)" @click="emit('confirm')">{{confirmText||$t("shell.modal.confirm")}}</button>
      </div>
    </div>
  </div>
</template>
