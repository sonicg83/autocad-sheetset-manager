<script setup lang="ts">
// PLAN-DM-021 Task 8（I18N-07/08）：静态文本走语义键；修订 ID/哈希/路径与协议 action 保持原样；
// 时间经 Intl 按生效语言格式化（formatDateTime），不在调用点拼接可翻译片段
import {useI18n} from "vue-i18n";
import type {RestorePreview,Revision} from "../api/contracts";
import {formatDateTime} from "../i18n/format";
defineProps<{revisions:Revision[];restorePreview:RestorePreview|null;executing:boolean}>();
defineEmits<{preview:[revision:Revision];restore:[]}>();
const {t}=useI18n();
</script>
<template><section class="panel preview"><h2>{{ $t("revisions.panel.title") }}</h2><table><thead><tr><th>{{ $t("revisions.panel.time") }}</th><th>{{ $t("revisions.panel.revision") }}</th><th>{{ $t("revisions.panel.resultSummary") }}</th><th></th></tr></thead><tbody><tr v-for="revision in revisions" :key="revision.id"><td>{{formatDateTime(revision.created_at)}}</td><td>{{revision.id.slice(0,16)}}</td><td>{{revision.before_hash.slice(0,8)}} → {{revision.result_hash.slice(0,8)}}</td><td><button :disabled="executing" @click="$emit('preview',revision)">{{ $t("revisions.panel.previewRestore") }}</button></td></tr></tbody></table><div v-if="restorePreview"><h3>{{ $t("revisions.panel.confirmTitle") }}</h3><ul><li v-for="file in restorePreview.files" :key="file.path" :class="{error:file.conflict}">{{file.action}} {{file.path}} <span v-if="file.conflict">{{ $t("revisions.panel.fileConflict") }}</span></li></ul><button class="primary" :disabled="executing||!restorePreview.executable" @click="$emit('restore')">{{ $t("revisions.panel.restoreAsNew") }}</button></div></section></template>
