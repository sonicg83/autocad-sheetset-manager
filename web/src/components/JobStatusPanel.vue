<script setup lang="ts">
import type {Job} from "../api/contracts";
defineProps<{job:Job;connectionMode:string}>();
defineEmits<{retry:[]}>();
function cadOperationLabel(operation?:string|null){if(operation==="rename_only")return "批量改名布局";if(operation==="rebuild")return "清除并重建布局";if(operation==="none")return "无需 CAD 操作";if(!operation)return "未提供 CAD 操作";return `未知 CAD 操作：${operation}`}
</script>
<template><section class="job-detail">
  <div class="job"><b>任务 {{job.id??'（无变更）'}}</b><span>{{job.status}} · {{job.progress??100}}% · 第 {{job.attempt??0}} 次</span><small>{{connectionMode}}</small><span v-if="job.error_code" class="error">{{job.error_code}}</span><button v-if="['FAILED','ROLLED_BACK','BLOCKED_FILE_LOCK','NEEDS_REVIEW'].includes(job.status)" @click="$emit('retry')">安全重试</button></div>
  <p v-if="job.suggestion">{{job.suggestion}}</p>
  <table v-if="job.files?.length"><thead><tr><th>DWG</th><th>操作</th><th>状态</th><th>进度</th><th>开始</th><th>结束</th><th>耗时</th><th>错误</th></tr></thead><tbody><template v-for="file in job.files" :key="file.target_path"><tr><td>{{file.target_path}}</td><td>{{cadOperationLabel(file.cad_operation)}}</td><td>{{file.status}}</td><td>{{file.progress}}%</td><td>{{file.started_at??'-'}}</td><td>{{file.finished_at??'-'}}</td><td>{{file.duration_ms??'-'}} ms</td><td class="error">{{file.error_code}}</td></tr><tr v-if="file.log_summary"><td colspan="8"><details><summary>Core Console 输出日志</summary><pre>{{file.log_summary}}</pre></details></td></tr></template></tbody></table>
</section></template>
