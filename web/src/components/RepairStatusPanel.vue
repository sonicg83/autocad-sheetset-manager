<script setup lang="ts">
// DST 修复状态面板（PLAN-DM-021 Task 8，I18N-07/12）：验证状态码 → 语义键展示，未知码回退原码；
// 修复码、节点路径与后端消息保持原样；数量插值，分隔符取自语言包。
import {useI18n} from "vue-i18n";
import type {DstValidation,RepairPreview} from "../api/contracts";
defineProps<{validation:DstValidation;preview:RepairPreview|null;previewing:boolean;executing:boolean}>();
defineEmits<{previewRepair:[];executeRepair:[];cancel:[]}>();
const {t}=useI18n();
const STATUS_KEYS:Record<string,string>={REPAIRED:"shell.repair.statusRepaired",INVALID_REPAIR_REQUIRED:"shell.repair.statusNeedsRepair",INVALID_UNRECOVERABLE:"shell.repair.statusUnrecoverable"};
function statusLabel(status:string){const key=STATUS_KEYS[status];return key?t(key):status}
function attrs(value:Record<string,string|null>){const separator=t("shell.repair.attrSeparator");return Object.entries(value).map(([key,item])=>`${key}=${item??'∅'}`).join(separator)||"—"}
</script>
<template><section class="panel repair" :class="`repair-${validation.status}`">
  <h2>{{ $t("shell.repair.title",{status:statusLabel(validation.status)}) }}</h2>
  <p v-if="validation.status==='REPAIRED'" class="warning">{{ $t("shell.repair.repairedWarning") }}</p>
  <p v-if="validation.status==='INVALID_REPAIR_REQUIRED'||validation.status==='INVALID_UNRECOVERABLE'" class="error">{{ $t("shell.repair.invalidError") }}</p>
  <details v-if="validation.actions.length"><summary>{{ $t("shell.repair.actionsSummary",{count:validation.actions.length},validation.actions.length) }}</summary><ul class="repair-actions"><li v-for="(action,index) in validation.actions" :key="index"><b>{{action.code}}</b> · {{action.confidence}} · {{action.object_id??'—'}}<br><span class="attr-diff">{{action.node_path}}</span><br><span class="attr-diff">{{ $t("shell.repair.before",{value:attrs(action.before)}) }}</span><br><span class="attr-diff">{{ $t("shell.repair.after",{value:attrs(action.after)}) }}</span><br>{{action.message}}</li></ul></details>
  <details v-if="validation.blocking_issues.length"><summary>{{ $t("shell.repair.blockingSummary",{count:validation.blocking_issues.length},validation.blocking_issues.length) }}</summary><ul class="diagnostics"><li v-for="issue in validation.blocking_issues" :key="issue.code+issue.message" :class="issue.severity"><b>{{issue.code}}</b>{{ $t("shell.preview.diagSeparator") }}{{issue.message}}</li></ul></details>
  <div v-if="validation.status==='REPAIRED'" class="link-actions"><button :disabled="previewing||executing" @click="$emit('previewRepair')">{{ $t("shell.repair.previewAndConfirm") }}</button><template v-if="preview"><span class="derived">{{ $t("shell.repair.previewSummary",{count:preview.actions?.length??0,digest:preview.preview_digest?.slice(0,16)},preview.actions?.length??0) }}</span><button class="primary" :disabled="executing||!preview.executable" @click="$emit('executeRepair')">{{ $t("shell.repair.confirmPublish") }}</button><button :disabled="executing" @click="$emit('cancel')">{{ $t("shell.repair.cancelConfirm") }}</button></template></div>
</section></template>
