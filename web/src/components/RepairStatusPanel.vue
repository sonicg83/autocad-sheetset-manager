<script setup lang="ts">
import type {DstValidation,RepairPreview} from "../api/contracts";
defineProps<{validation:DstValidation;preview:RepairPreview|null;previewing:boolean;executing:boolean}>();
defineEmits<{previewRepair:[];executeRepair:[];cancel:[]}>();
function statusLabel(status:string){return {REPAIRED:"已修复（待确认）",INVALID_REPAIR_REQUIRED:"需要人工修复",INVALID_UNRECOVERABLE:"不可恢复"}[status]??status}
function attrs(value:Record<string,string|null>){return Object.entries(value).map(([key,item])=>`${key}=${item??'∅'}`).join("；")||"—"}
</script>
<template><section class="panel repair" :class="`repair-${validation.status}`">
  <h2>DST 修复状态：{{statusLabel(validation.status)}}</h2>
  <p v-if="validation.status==='REPAIRED'" class="warning">检测到可修复的元数据缺失，已在本机内存中修复；必须先确认并发布独立修复修订，普通编辑发布已被禁用。</p>
  <p v-if="validation.status==='INVALID_REPAIR_REQUIRED'||validation.status==='INVALID_UNRECOVERABLE'" class="error">存在阻断问题；当前只读，所有写入操作已禁用。请先修复 DST 后重新打开。</p>
  <details v-if="validation.actions.length"><summary>修复明细（{{validation.actions.length}}）</summary><ul class="repair-actions"><li v-for="(action,index) in validation.actions" :key="index"><b>{{action.code}}</b> · {{action.confidence}} · {{action.object_id??'—'}}<br><span class="attr-diff">{{action.node_path}}</span><br><span class="attr-diff">前：{{attrs(action.before)}}</span><br><span class="attr-diff">后：{{attrs(action.after)}}</span><br>{{action.message}}</li></ul></details>
  <details v-if="validation.blocking_issues.length"><summary>阻断原因（{{validation.blocking_issues.length}}）</summary><ul class="diagnostics"><li v-for="issue in validation.blocking_issues" :key="issue.code+issue.message" :class="issue.severity"><b>{{issue.code}}</b>：{{issue.message}}</li></ul></details>
  <div v-if="validation.status==='REPAIRED'" class="link-actions"><button :disabled="previewing||executing" @click="$emit('previewRepair')">预览并确认修复</button><template v-if="preview"><span class="derived">修复 {{preview.actions?.length??0}} 项 · 摘要 {{preview.preview_digest?.slice(0,16)}}</span><button class="primary" :disabled="executing||!preview.executable" @click="$emit('executeRepair')">确认发布修复修订</button><button :disabled="executing" @click="$emit('cancel')">取消确认</button></template></div>
</section></template>
