<script setup lang="ts">
import type {DraftAction} from "../api/contracts";
defineProps<{actions:DraftAction[];cursor:number;commandCount:number;stale:boolean;staleReasons:string[];corrupted:boolean;writesDisabled:boolean;loading:boolean}>();
defineEmits<{discard:[];reloadConflict:[];undo:[];redo:[];clear:[];preview:[];remove:[index:number]}>();
</script>
<template>
  <div v-if="corrupted" class="notice">损坏草稿已隔离，未覆盖原文件。</div>
  <div v-if="stale" class="notice error">草稿已过期（{{staleReasons.join('、')}}），不会自动 rebase。可查看旧动作并丢弃后手工重做。<button v-if="staleReasons.includes('DRAFT_VERSION_CONFLICT')" @click="$emit('reloadConflict')">放弃本地冲突动作并重新加载</button><button v-else @click="$emit('discard')">丢弃过期草稿</button></div>
  <div class="toolbar"><span>待处理 {{commandCount}} · 动作 {{cursor}}/{{actions.length}}</span><button :disabled="stale||cursor===0" @click="$emit('undo')">撤销</button><button :disabled="stale||cursor>=actions.length" @click="$emit('redo')">重做</button><button :disabled="stale||!actions.length" @click="$emit('clear')">清空</button><button :disabled="stale||!commandCount||writesDisabled||loading" @click="$emit('preview')">预览变更</button></div>
  <ol v-if="actions.length" class="draft-actions"><li v-for="(action,index) in actions" :key="action.id" :class="{derived:index>=cursor}"><span>{{action.label}} · {{action.commands.length}} 条命令</span><button :disabled="stale" @click="$emit('remove',index)">移除</button></li></ol>
</template>
