<script setup lang="ts">
// 标签② 属性：属性字段定义面板 + 图纸集属性值面板（PLAN-DM-016 任务 3/4，SPEC-DM-010 §3）。
// 内容区从上到下为「属性字段定义」「图纸集属性值」两个独立面板；本视图只组合与转发，
// 不直接改 workspace props、不编排 API 命令：值编辑经 usePropertiesWorkspace，定义增删
// 经 emit 交给 App 既有命令簿门禁（queuePropertyDefinition/queueDeleteProperty）。
import type {CsvPreview,PropertyDefinition,PropertyType,Workspace} from "../api/contracts";
import type {PropertyBuffer,PropertySearchMode,ValueKey,ValueStatus} from "../features/properties/types";
import PropertyDefinitionPanel from "../components/properties/PropertyDefinitionPanel.vue";
import PropertyValuePanel from "../components/properties/PropertyValuePanel.vue";
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
    <PropertyDefinitionPanel
      :definitions="workspace.sheet_set.property_definitions"
      :form="propertyForm"
      :workspace-id="workspace.id"
      :has-csv="hasCsv" :csv-preview="csvPreview" :csv-executable="csvExecutable" :writes-disabled="repairWritesDisabled"
      @add-definition="$emit('queuePropertyDefinition')"
      @delete-definition="definition=>$emit('queueDeleteProperty',definition)"
      @read-csv="$emit('readCsv',$event)" @preview-csv="$emit('previewCsv')" @import-csv="$emit('importCsv')"
    />
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
  </section>
</template>
<style scoped>
.properties-view{display:block}
</style>
