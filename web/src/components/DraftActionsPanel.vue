<script setup lang="ts">
// 草稿动作栈面板（PLAN-DM-021 Task 8，I18N-12）：动作标签只持久化稳定 label_key（+命名 params），
// 本组件在渲染期翻译为当前生效语言；旧版本草稿的本地化 label 仅迁移窗口内回退展示。
// 过期原因等稳定 code 保持原样；列表分隔符取自语言包，不在模板写死全角标点。
import {useI18n} from "vue-i18n";
import type {DraftAction} from "../api/contracts";
defineProps<{actions:DraftAction[];cursor:number;commandCount:number;stale:boolean;staleReasons:string[];corrupted:boolean;writesDisabled:boolean;loading:boolean}>();
defineEmits<{discard:[];reloadConflict:[];undo:[];redo:[];clear:[];preview:[];remove:[index:number]}>();
const {t}=useI18n();
function actionLabel(action:DraftAction){return action.label_key?t(action.label_key,action.params??{}):(action.label??"")}
</script>
<template>
  <div v-if="corrupted" class="notice">{{ $t("shell.draft.corrupted") }}</div>
  <div v-if="stale" class="notice error">{{ $t("shell.draft.staleMessage",{reasons:staleReasons.join(t("common.listSeparator"))}) }}<button v-if="staleReasons.includes('DRAFT_VERSION_CONFLICT')" @click="$emit('reloadConflict')">{{ $t("shell.draft.reloadConflict") }}</button><button v-else @click="$emit('discard')">{{ $t("shell.draft.discardStale") }}</button></div>
  <div class="toolbar"><span>{{ $t("shell.draft.pendingSummary",{count:commandCount,cursor,total:actions.length}) }}</span><button :disabled="stale||cursor===0" @click="$emit('undo')">{{ $t("shell.dock.undo") }}</button><button :disabled="stale||cursor>=actions.length" @click="$emit('redo')">{{ $t("shell.dock.redo") }}</button><button :disabled="stale||!actions.length" @click="$emit('clear')">{{ $t("shell.draft.clear") }}</button><button :disabled="stale||!commandCount||writesDisabled||loading" @click="$emit('preview')">{{ $t("shell.dock.preview") }}</button></div>
  <ol v-if="actions.length" class="draft-actions"><li v-for="(action,index) in actions" :key="action.id" :class="{derived:index>=cursor}"><span>{{actionLabel(action)}} · {{ $t("shell.draft.commandCount",{count:action.commands.length},action.commands.length) }}</span><button :disabled="stale" @click="$emit('remove',index)">{{ $t("shell.draft.remove") }}</button></li></ol>
</template>
