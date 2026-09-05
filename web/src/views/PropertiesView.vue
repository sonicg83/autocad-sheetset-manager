<script setup lang="ts">
// 标签② 属性：图纸集名称与自定义属性（PLAN-DM-016 任务 2 最小接线）。
// 输入只写会话缓冲（propertyInput，来自 usePropertiesWorkspace），不直接修改 workspace props；
// 提交/撤回经 emit 由 App 调用组合式函数。分区面板重建在任务 3/4 进行。
import {computed} from "vue";
import type {CsvPreview,PropertyDefinition,PropertyType,Workspace} from "../api/contracts";
import type {PropertyBuffer,ValueKey} from "../features/properties/types";
import PropertyPanel from "../components/PropertyPanel.vue";
const props=defineProps<{
  workspace:Workspace;
  propertyInput:PropertyBuffer|null;
  propertyErrors:Partial<Record<ValueKey,string>>;
  propertySummaryError:string;
  propertyForm:{type:PropertyType;name:string;defaultValue:string};
  hasCsv:boolean;csvPreview:CsvPreview|null;csvExecutable:boolean;
  repairWritesDisabled:boolean;
}>();
defineEmits<{
  setPropertyValue:[key:string,value:string];submitValues:[];revertValue:[key:string];
  queuePropertyDefinition:[];queueDeleteProperty:[definition:PropertyDefinition];
  readCsv:[event:Event];previewCsv:[];importCsv:[];
}>();
// 值列表保持缓冲的读取顺序（不排序、不补造）；失效/错误文案按字段身份读取
const valueNames=computed(()=>Object.keys(props.propertyInput?.values??{}));
function fieldError(name:string):string|undefined{return props.propertyErrors[`sheetset:${name}` as ValueKey]}
</script>
<template>
  <section class="properties-view" role="tabpanel" id="panel-properties" aria-label="属性">
    <p v-if="propertySummaryError" class="error notice" role="alert">{{propertySummaryError}}</p>
    <section class="panel summary summary-name">
      <label for="sheetset-name">图纸集</label>
      <input id="sheetset-name" :value="propertyInput?.name" :aria-invalid="propertyErrors['@name']?'true':undefined" aria-describedby="property-name-error" @input="$emit('setPropertyValue','@name',($event.target as HTMLInputElement).value)">
      <span v-if="propertyErrors['@name']" id="property-name-error" class="field-error">{{propertyErrors['@name']}}</span>
      <button @click="$emit('submitValues')">更新图纸集</button>
    </section>
    <details v-if="valueNames.length" open><summary>图纸集自定义属性</summary><div class="form-grid"><label v-for="name in valueNames" :key="name">{{name}}<input :aria-label="`属性 ${name}`" :aria-invalid="fieldError(name)?'true':undefined" :value="propertyInput?.values[name]" @input="$emit('setPropertyValue',`sheetset:${name}`,($event.target as HTMLInputElement).value)"><span v-if="fieldError(name)" class="field-error">{{fieldError(name)}}</span><button type="button" class="revert" @click="$emit('revertValue',`sheetset:${name}`)">撤回 {{name}}</button></label></div><button @click="$emit('submitValues')">加入属性值变更</button></details>
    <PropertyPanel :workspace-id="workspace.id" :definitions="workspace.sheet_set.property_definitions" :form="propertyForm" :has-csv="hasCsv" :csv-preview="csvPreview" :csv-executable="csvExecutable" :writes-disabled="repairWritesDisabled" @delete-definition="$emit('queueDeleteProperty',$event)" @add-definition="$emit('queuePropertyDefinition')" @read-csv="$emit('readCsv',$event)" @preview-csv="$emit('previewCsv')" @import-csv="$emit('importCsv')" />
  </section>
</template>
<style scoped>
.properties-view{display:block}
.summary-name{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;margin-bottom:var(--space-4)}
.summary-name input{flex:1;min-width:220px}
.summary-name button{white-space:nowrap}
.field-error{color:var(--color-danger);font-size:13px}
.form-grid .revert{align-self:center;white-space:nowrap}
</style>
