<script setup lang="ts">
import type {RestorePreview,Revision} from "../api/contracts";
defineProps<{revisions:Revision[];restorePreview:RestorePreview|null;executing:boolean}>();
defineEmits<{preview:[revision:Revision];restore:[]}>();
</script>
<template><section class="panel preview"><h2>永久修订</h2><table><thead><tr><th>时间</th><th>修订</th><th>结果摘要</th><th></th></tr></thead><tbody><tr v-for="revision in revisions" :key="revision.id"><td>{{new Date(revision.created_at).toLocaleString()}}</td><td>{{revision.id.slice(0,16)}}</td><td>{{revision.before_hash.slice(0,8)}} → {{revision.result_hash.slice(0,8)}}</td><td><button :disabled="executing" @click="$emit('preview',revision)">恢复预览</button></td></tr></tbody></table><div v-if="restorePreview"><h3>恢复确认</h3><ul><li v-for="file in restorePreview.files" :key="file.path" :class="{error:file.conflict}">{{file.action}} {{file.path}} <span v-if="file.conflict">（当前文件冲突）</span></li></ul><button class="primary" :disabled="executing||!restorePreview.executable" @click="$emit('restore')">恢复为新修订</button></div></section></template>
