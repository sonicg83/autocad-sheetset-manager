<script setup lang="ts">
import type {Sheet,Subset} from "../api/contracts";
defineProps<{rows:Array<{subset:Subset;sheet:Sheet}>;selectedIds:string[];pendingIds:Set<string>;diagnosticIds:Set<string>}>();
defineEmits<{toggle:[sheetId:string];openSubset:[subsetId:string]}>();
</script>
<template><div class="sheet-table-window" tabindex="0" aria-label="过滤后的图纸表格"><table><thead><tr><th>选择</th><th>子集</th><th>图号</th><th>标题</th><th>DWG</th><th>布局</th><th>状态</th></tr></thead><tbody><tr v-for="row in rows" :key="row.sheet.id"><td><input type="checkbox" :aria-label="`选择图纸 ${row.sheet.number}`" :checked="selectedIds.includes(row.sheet.id)" @change="$emit('toggle',row.sheet.id)"></td><td><button class="link-button" @click="$emit('openSubset',row.subset.id)">{{row.subset.display_name}}</button></td><td>{{row.sheet.number}}</td><td>{{row.sheet.title}}</td><td><span>{{row.sheet.layout.file_name}}</span><small>{{row.sheet.layout.relative_file_name}} · {{row.sheet.layout.resolved_path??'未解析'}}</small></td><td>{{row.sheet.layout.layout_name}}</td><td>{{pendingIds.has(row.sheet.id)?'待变更':diagnosticIds.has(row.sheet.id)?'阻断':'正常'}}</td></tr></tbody></table></div></template>
