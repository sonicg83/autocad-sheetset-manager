<script setup lang="ts">
// 任务状态面板（PLAN-DM-021 Task 8，I18N-12）：SSE/任务 payload 保持稳定状态码，
// 状态码 → 语义键只在展示层映射，未知码回退原码；错误码、DWG 名与后端消息保持原样；
// 起止时间经 Intl 按生效语言格式化。
import {useI18n} from "vue-i18n";
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
  <div class="job"><b>{{ job.id?$t("jobs.job.title",{id:job.id}):$t("jobs.job.noChange") }}</b><span>{{statusLabel(job.status)}} · {{job.progress??100}}% · {{ $t("jobs.job.attempt",{attempt:job.attempt??0}) }}</span><small>{{ connectionMode==="polling"?$t("jobs.connection.polling"):$t("jobs.connection.sse") }}</small><span v-if="job.error_code" class="error">{{job.error_code}}</span><button v-if="['FAILED','ROLLED_BACK','BLOCKED_FILE_LOCK','NEEDS_REVIEW'].includes(job.status)" @click="$emit('retry')">{{ $t("jobs.job.retry") }}</button></div>
  <p v-if="job.suggestion">{{job.suggestion}}</p>
  <table v-if="job.files?.length"><thead><tr><th>{{ $t("jobs.files.dwg") }}</th><th>{{ $t("jobs.files.operation") }}</th><th>{{ $t("jobs.files.status") }}</th><th>{{ $t("jobs.files.progress") }}</th><th>{{ $t("jobs.files.started") }}</th><th>{{ $t("jobs.files.finished") }}</th><th>{{ $t("jobs.files.duration") }}</th><th>{{ $t("jobs.files.error") }}</th></tr></thead><tbody><template v-for="file in job.files" :key="file.target_path"><tr><td>{{file.target_path}}</td><td>{{cadOperationLabel(file.cad_operation)}}</td><td>{{statusLabel(file.status)}}</td><td>{{file.progress}}%</td><td>{{file.started_at?formatDateTime(file.started_at):'-'}}</td><td>{{file.finished_at?formatDateTime(file.finished_at):'-'}}</td><td>{{file.duration_ms!=null?$t("jobs.files.durationMs",{value:file.duration_ms}):'-'}}</td><td class="error">{{file.error_code}}</td></tr><tr v-if="file.log_summary"><td colspan="8"><details><summary>{{ $t("jobs.files.logSummary") }}</summary><pre>{{file.log_summary}}</pre></details></td></tr></template></tbody></table>
</section></template>
