<script setup lang="ts">
import type {CsvPreview,PropertyDefinition,PropertyType} from "../api/contracts";
defineProps<{workspaceId:string;definitions:PropertyDefinition[];form:{type:PropertyType;name:string;defaultValue:string};hasCsv:boolean;csvPreview:CsvPreview|null;csvExecutable:boolean;writesDisabled:boolean}>();
defineEmits<{deleteDefinition:[definition:PropertyDefinition];addDefinition:[];readCsv:[event:Event];previewCsv:[];importCsv:[]}>();
</script>
<template><section class="panel property-panel">
  <div class="section-title"><div><h2>属性定义</h2><p>属性定义与结构变更需分批预览和执行。</p></div><div class="link-actions"><a href="/api/custom-properties/template" download>下载 CSV 模板</a><a :href="`/api/workspaces/${workspaceId}/custom-properties/export`" download>导出当前属性</a></div></div>
  <table><thead><tr><th>作用域</th><th>名称</th><th>默认值</th><th></th></tr></thead><tbody><tr v-for="definition in definitions" :key="definition.type+definition.name"><td>{{definition.type}}</td><td>{{definition.name}}</td><td>{{definition.default_value||'（空）'}}</td><td><button class="danger" @click="$emit('deleteDefinition',definition)">删除 {{definition.name}}</button></td></tr></tbody></table>
  <div class="form-row"><label>属性作用域<select v-model="form.type"><option value="sheet">图纸</option><option value="sheetset">图纸集</option></select></label><label>属性名称<input v-model="form.name"></label><label>默认值<input v-model="form.defaultValue"></label><button @click="$emit('addDefinition')">加入属性定义</button></div>
  <div class="csv-flow"><label>属性 CSV 文件<input type="file" accept=".csv,text/csv" @change="$emit('readCsv',$event)"></label><button :disabled="!hasCsv" @click="$emit('previewCsv')">预览 CSV 导入</button><button class="primary" :disabled="writesDisabled||!csvExecutable" @click="$emit('importCsv')">确认导入</button></div>
  <div v-if="csvPreview" class="csv-preview"><h3>CSV 合并预览</h3><ul><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`">第 {{change.line}} 行 · {{change.action}} · {{change.type}} · {{change.name}}</li></ul><ul class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">第 {{item.line}} 行 · </span><b>{{item.code}}</b>：{{item.message}}</li></ul></div>
</section></template>
