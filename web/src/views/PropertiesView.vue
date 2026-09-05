<script setup lang="ts">
// 标签② 属性：图纸集属性值面板 + 属性定义面板（PLAN-DM-016 任务 3）。
// 值编辑交给 PropertyValuePanel：本视图只组合与转发，不直接改 workspace props、不编排 API 命令；
// 提交/撤回/搜索/活动字段经 emit 由 App 调用 usePropertiesWorkspace。定义面板重建在任务 4/5 进行。
import type {CsvPreview,PropertyDefinition,PropertyType,Workspace} from "../api/contracts";
import type {PropertyBuffer,PropertySearchMode,ValueKey,ValueStatus} from "../features/properties/types";
import PropertyValuePanel from "../components/properties/PropertyValuePanel.vue";
import PropertyPanel from "../components/PropertyPanel.vue";
const props=defineProps<{
  workspace:Workspace;
  propertyInput:PropertyBuffer|null;
  propertyBase:PropertyBuffer|null;
  propertyDraft:PropertyBuffer|null;
  propertyStatusOf:(key:ValueKey)=>ValueStatus;
  propertyErrors:Partial<Record<ValueKey,string>>;
  propertySummaryError:string;
  propertyMatchedKeys:ValueKey[];
  propertyHiddenDirtyCount:number;
  propertySearch:string;
  propertySearchMode:PropertySearchMode;
  propertyChangedOnly:boolean;
  propertyActiveKey:ValueKey|null;
  propertyForm:{type:PropertyType;name:string;defaultValue:string};
  hasCsv:boolean;csvPreview:CsvPreview|null;csvExecutable:boolean;
  repairWritesDisabled:boolean;
}>();
defineEmits<{
  setPropertyValue:[key:ValueKey,value:string];submitValues:[];revertValue:[key:ValueKey];
  "update:propertySearch":[value:string];"update:propertySearchMode":[value:PropertySearchMode];
  "update:propertyChangedOnly":[value:boolean];"update:propertyActiveKey":[key:ValueKey|null];
  discardPropertyInput:[];
  queuePropertyDefinition:[];queueDeleteProperty:[definition:PropertyDefinition];
  readCsv:[event:Event];previewCsv:[];importCsv:[];
}>();
</script>
<template>
  <section class="properties-view" role="tabpanel" id="panel-properties" aria-label="属性">
    <p v-if="propertySummaryError" class="error notice" role="alert">{{propertySummaryError}}</p>
    <PropertyValuePanel
      v-if="propertyInput&&propertyBase&&propertyDraft"
      :input="propertyInput" :base="propertyBase" :draft="propertyDraft"
      :status-of="propertyStatusOf" :errors="propertyErrors"
      :matched-keys="propertyMatchedKeys" :hidden-dirty-count="propertyHiddenDirtyCount"
      :search="propertySearch" :search-mode="propertySearchMode" :changed-only="propertyChangedOnly"
      :active-key="propertyActiveKey"
      @set-value="(key,value)=>$emit('setPropertyValue',key,value)"
      @revert-value="key=>$emit('revertValue',key)"
      @submit="$emit('submitValues')"
      @discard="$emit('discardPropertyInput')"
      @update:search="value=>$emit('update:propertySearch',value)"
      @update:search-mode="value=>$emit('update:propertySearchMode',value)"
      @update:changed-only="value=>$emit('update:propertyChangedOnly',value)"
      @update:active-key="key=>$emit('update:propertyActiveKey',key)"
    />
    <PropertyPanel :workspace-id="workspace.id" :definitions="workspace.sheet_set.property_definitions" :form="propertyForm" :has-csv="hasCsv" :csv-preview="csvPreview" :csv-executable="csvExecutable" :writes-disabled="repairWritesDisabled" @delete-definition="$emit('queueDeleteProperty',$event)" @add-definition="$emit('queuePropertyDefinition')" @read-csv="$emit('readCsv',$event)" @preview-csv="$emit('previewCsv')" @import-csv="$emit('importCsv')" />
  </section>
</template>
<style scoped>
.properties-view{display:block}
</style>
