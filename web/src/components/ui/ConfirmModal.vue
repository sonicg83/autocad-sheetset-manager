<script setup lang="ts">
import {watch,ref,nextTick} from "vue";
const props=defineProps<{open:boolean;title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?: "可撤销"|"不可逆"}>();
const emit=defineEmits<{confirm:[];cancel:[]}>();
const checked=ref(false);const card=ref<HTMLElement|null>(null);const opener=ref<Element|null>(null);
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
      <h2>{{title}} <span v-if="reversibility" class="modal-irr" :class="{danger}">{{reversibility}}</span></h2>
      <p class="modal-message">{{message}}</p>
      <ul v-if="impactLines?.length" class="modal-impact"><li v-for="line in impactLines" :key="line" class="mono">{{line}}</li></ul>
      <label v-if="requireCheckbox" class="modal-check"><input type="checkbox" v-model="checked">我已了解本次操作{{reversibility??"不可逆"}}，并已核对受影响内容清单</label>
      <div class="modal-actions">
        <button type="button" @click="emit('cancel')">{{cancelText??"取消"}}</button>
        <button type="button" :class="{danger}" :disabled="Boolean(requireCheckbox)&&!checked" @click="emit('confirm')">{{confirmText}}</button>
      </div>
    </div>
  </div>
</template>
