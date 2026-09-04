<script setup lang="ts">
// 标签② 属性：图纸集名称与自定义属性（属性卡）+ 属性定义/CSV 导入（PropertyPanel）
import type {CsvPreview,PropertyDefinition,PropertyType,Workspace} from "../api/contracts";
import PropertyPanel from "../components/PropertyPanel.vue";
defineProps<{
  workspace:Workspace;
  propertyForm:{type:PropertyType;name:string;defaultValue:string};
  hasCsv:boolean;csvPreview:CsvPreview|null;csvExecutable:boolean;
  repairWritesDisabled:boolean;
}>();
defineEmits<{
  queueSheetSet:[];queuePropertyDefinition:[];queueDeleteProperty:[definition:PropertyDefinition];
  readCsv:[event:Event];previewCsv:[];importCsv:[];
}>();
</script>
<template>
  <section class="properties-view" role="tabpanel" id="panel-properties" aria-label="属性">
    <section class="panel summary summary-name">
      <label for="sheetset-name">图纸集</label>
      <input id="sheetset-name" v-model="workspace.sheet_set.name">
      <button @click="$emit('queueSheetSet')">更新图纸集</button>
    </section>
    <details v-if="Object.keys(workspace.sheet_set.custom_properties).length"><summary>图纸集自定义属性</summary><div class="form-grid"><label v-for="(_,name) in workspace.sheet_set.custom_properties" :key="name">{{name}}<input v-model="workspace.sheet_set.custom_properties[name]"></label></div><button @click="$emit('queueSheetSet')">加入属性值变更</button></details>
    <PropertyPanel :workspace-id="workspace.id" :definitions="workspace.sheet_set.property_definitions" :form="propertyForm" :has-csv="hasCsv" :csv-preview="csvPreview" :csv-executable="csvExecutable" :writes-disabled="repairWritesDisabled" @delete-definition="$emit('queueDeleteProperty',$event)" @add-definition="$emit('queuePropertyDefinition')" @read-csv="$emit('readCsv',$event)" @preview-csv="$emit('previewCsv')" @import-csv="$emit('importCsv')" />
  </section>
</template>
<style scoped>
.properties-view{display:block}
.summary-name{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;margin-bottom:var(--space-4)}
.summary-name input{flex:1;min-width:220px}
.summary-name button{white-space:nowrap}
</style>
