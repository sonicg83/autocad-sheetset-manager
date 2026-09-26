<script setup lang="ts">
// 任务状态面板（PLAN-DM-021 Task 8，I18N-12）：SSE/任务 payload 保持稳定状态码，
// 状态码 → 语义键只在展示层映射，未知码回退原码；错误码、DWG 名与后端消息保持原样；
// 起止时间经 Intl 按生效语言格式化。
import {useI18n} from "vue-i18n";
import UiButton from "./ui/UiButton.vue";
import type {Job} from "../api/contracts";
import {formatDateTime} from "../i18n/format";
defineProps<{job:Job;connectionMode:string}>();
defineEmits<{retry:[]}>();
const {t}=useI18n();
const STATUS_KEYS:Record<string,string>={QUEUED:"jobs.status.queued",RUNNING:"jobs.status.running",SUCCEEDED:"jobs.status.succeeded",FAILED:"jobs.status.failed",ROLLED_BACK:"jobs.status.rolledBack",BLOCKED_FILE_LOCK:"jobs.status.blockedFileLock",NEEDS_REVIEW:"jobs.status.needsReview",PENDING:"jobs.status.pending",SKIPPED:"jobs.status.skipped"};
function statusLabel(status:string){const key=STATUS_KEYS[status];return key?t(key):status}
const CAD_OPERATION_KEYS:Record<string,string>={rename_only:"common.cadOperation.renameOnly",rebuild:"common.cadOperation.rebuild",none:"common.cadOperation.none"};
function cadOperationLabel(operation?:string|null){if(!operation)return t("common.cadOperation.missing");const key=CAD_OPERATION_KEYS[operation];return key?t(key):t("common.cadOperation.unknown",{operation})}
</script>
<template><section class="job-detail">
  <div class="job"><b>{{ job.id?$t("jobs.job.title",{id:job.id}):$t("jobs.job.noChange") }}</b><span>{{statusLabel(job.status)}} · {{job.progress??100}}% · {{ $t("jobs.job.attempt",{attempt:job.attempt??0}) }}</span><small>{{ connectionMode==="polling"?$t("jobs.connection.polling"):$t("jobs.connection.sse") }}</small><span v-if="job.error_code" class="error">{{job.error_code}}</span><UiButton v-if="['FAILED','ROLLED_BACK','BLOCKED_FILE_LOCK','NEEDS_REVIEW'].includes(job.status)" variant="secondary" @click="$emit('retry')">{{ $t("jobs.job.retry") }}</UiButton></div>
  <p v-if="job.error_detail" class="error">{{ $t("jobs.job.errorDetail",{detail:job.error_detail}) }}</p>
  <p v-if="job.suggestion">{{job.suggestion}}</p>
  <table v-if="job.files?.length"><thead><tr><th>{{ $t("jobs.files.dwg") }}</th><th>{{ $t("jobs.files.operation") }}</th><th>{{ $t("jobs.files.status") }}</th><th class="num-col">{{ $t("jobs.files.progress") }}</th><th>{{ $t("jobs.files.started") }}</th><th>{{ $t("jobs.files.finished") }}</th><th class="num-col">{{ $t("jobs.files.duration") }}</th><th>{{ $t("jobs.files.error") }}</th></tr></thead><tbody><template v-for="file in job.files" :key="file.target_path"><tr><td>{{file.target_path}}</td><td>{{cadOperationLabel(file.cad_operation)}}</td><td>{{statusLabel(file.status)}}</td><td class="num-col">{{file.progress}}</td><td>{{file.started_at?formatDateTime(file.started_at):'-'}}</td><td>{{file.finished_at?formatDateTime(file.finished_at):'-'}}</td><td class="num-col">{{file.duration_ms!=null?file.duration_ms:'-'}}</td><td class="error">{{file.error_code}}</td></tr><tr v-if="file.log_summary"><td colspan="8" class="log-cell"><details><summary>{{ $t("jobs.files.logSummary") }}</summary><pre>{{file.log_summary}}</pre></details></td></tr></template></tbody></table>
</section></template>
<style scoped>
/* PLAN-DM-043 Task 5：普通单元格消费 44px 基础档与单档令牌化 padding，对齐显式声明 */
.job-detail th,.job-detail td{height:var(--sheet-table-row-height);padding:var(--space-2);border-bottom:1px solid var(--color-border-subtle);text-align:left;vertical-align:middle}
.job-detail th{vertical-align:middle}
/* 进度/耗时是可比较数值列：右对齐 + tabular-nums，单位写在表头（SPEC-DM-006 §6.4） */
.job-detail .num-col{text-align:right;font-variant-numeric:tabular-nums;vertical-align:middle}
/* 跨列日志详情：多行文本格取顶端对齐，按内容增高且可换行阅读 */
.job-detail .log-cell{vertical-align:top}
.job-detail .log-cell pre{margin:var(--space-1) 0 0;white-space:pre-wrap;word-break:break-word}
</style>
