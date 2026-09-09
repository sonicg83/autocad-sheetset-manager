<script setup lang="ts">
import {computed,watch,ref,nextTick} from "vue";
import {useI18n} from "vue-i18n";
// reversibility 为稳定语义值（I18N-07）：显示文本经语言包渲染，不把中文枚举作为类型
const props=defineProps<{open:boolean;title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?: "reversible"|"irreversible"}>();
const emit=defineEmits<{confirm:[];cancel:[]}>();
const {t}=useI18n();
const checked=ref(false);const card=ref<HTMLElement|null>(null);const opener=ref<Element|null>(null);
// 稳定值 → 语义键映射（不在模板拼接键）
const REVERSIBILITY_KEYS={reversible:"shell.modal.reversible",irreversible:"shell.modal.irreversible"} as const;
const reversibilityText=computed(()=>props.reversibility?t(REVERSIBILITY_KEYS[props.reversibility]):"");
const checkboxLabel=computed(()=>t("shell.modal.checkbox",{reversibility:reversibilityText.value||t("shell.modal.irreversible")}));
watch(()=>props.open,async open=>{checked.value=false;
  if(open){opener.value=document.activeElement;await nextTick();card.value?.focus();}
  else (opener.value as HTMLElement|null)?.focus?.();});
function onKeydown(e:KeyboardEvent){
  if(e.key==="Escape"){e.stopPropagation();emit("cancel");return}
  if(e.key!=="Tab"||!card.value)return;
  // 焦点困绕：Tab 循环限制在模态内
  const items=Array.from(card.value.querySelectorAll<HTMLElement>("button,input")).filter(el=>!el.hasAttribute("disabled"));
  if(!items.length)return;const first=items[0],last=items[items.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onKeydown">
    <div class="modal-card" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1" ref="card">
      <h2>{{title}} <span v-if="reversibility" class="modal-irr" :class="{danger}">{{reversibilityText}}</span></h2>
      <p class="modal-message">{{message}}</p>
      <ul v-if="impactLines?.length" class="modal-impact"><li v-for="line in impactLines" :key="line" class="mono">{{line}}</li></ul>
      <label v-if="requireCheckbox" class="modal-check"><input type="checkbox" v-model="checked">{{checkboxLabel}}</label>
      <div class="modal-actions">
        <button type="button" @click="emit('cancel')">{{cancelText??$t("shell.modal.cancel")}}</button>
        <button type="button" :class="{danger}" :disabled="Boolean(requireCheckbox)&&!checked" @click="emit('confirm')">{{confirmText||$t("shell.modal.confirm")}}</button>
      </div>
    </div>
  </div>
</template>
