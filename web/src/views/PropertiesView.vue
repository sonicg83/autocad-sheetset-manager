<script setup lang="ts">
// 标签② 属性：属性字段定义面板 + CSV 导入导出面板 + 图纸集属性值面板（PLAN-DM-016 任务 6 组合，SPEC-DM-010 §3）。
// 内容区从上到下固定为「属性字段定义」「属性导入导出」「图纸集属性值」三张独立语义卡片；
// 折叠/查询/页码/导入区开关为工作区会话态（usePropertiesWorkspace），本视图只组合、转发与协调：
// - 错误摘要：提交失败后集中展示摘要与字段错误，点击字段项展开值面板并聚焦对应输入；
// - 「新增图纸集字段」入口：展开定义面板并打开新增区（作用域预置为图纸集）。
// 不直接改 workspace props、不编排 API 命令：值编辑经 usePropertiesWorkspace，定义增删
// 经 emit 交给 App 既有命令簿门禁（queuePropertyDefinition/queueDeleteProperty），
// CSV 读取/预览/确认经 App 的 useCsvImport（渐进面板 + 门禁 + 强确认）。
import {computed, nextTick, ref} from "vue";
import type {CsvPreview,PropertyDefinition,Workspace} from "../api/contracts";
import type {DefinitionScopeFilter} from "../features/properties/model";
import type {PropertyBuffer,PropertySearchMode,ValueKey,ValueStatus} from "../features/properties/types";
import PropertyDefinitionPanel from "../components/properties/PropertyDefinitionPanel.vue";
import PropertyCsvPanel from "../components/properties/PropertyCsvPanel.vue";
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
  propertyDefinitionForm:{type:"sheet"|"sheetset";name:string;defaultValue:string};
  propertyDefinitionsCollapsed:boolean;
  propertyValuesCollapsed:boolean;
  propertyCsvCollapsed:boolean;
  propertyCsvOpen:boolean;
  propertyDefinitionsQuery:string;
  propertyDefinitionsScope:DefinitionScopeFilter;
  propertyDefinitionsPage:number;
  hasCsv:boolean;csvPreview:CsvPreview|null;csvExecutable:boolean;
  repairWritesDisabled:boolean;
}>();
const emit=defineEmits<{
  setPropertyValue:[key:ValueKey,value:string];submitValues:[];revertValue:[key:ValueKey];
  "update:propertySearch":[value:string];"update:propertySearchMode":[value:PropertySearchMode];
  "update:propertyChangedOnly":[value:boolean];"update:propertyActiveKey":[key:ValueKey|null];
  "update:propertyDefinitionsCollapsed":[value:boolean];"update:propertyValuesCollapsed":[value:boolean];
  "update:propertyCsvCollapsed":[value:boolean];"update:propertyCsvOpen":[value:boolean];"update:propertyDefinitionsQuery":[value:string];
  "update:propertyDefinitionsScope":[value:DefinitionScopeFilter];"update:propertyDefinitionsPage":[value:number];
  discardPropertyInput:[];
  queuePropertyDefinition:[];queueDeleteProperty:[definition:PropertyDefinition];
  readCsv:[event:Event];previewCsv:[];importCsv:[];
}>();

// —— 错误摘要（SPEC-DM-010 §5.2）：摘要 + 字段错误项，点击展开值面板并聚焦字段 ——
function labelOf(key:ValueKey):string{return key==="@name"?"图纸集名称":key.slice("sheetset:".length)}
const fieldErrorEntries=computed<[ValueKey,string][]>(()=>Object.entries(props.propertyErrors) as [ValueKey,string][]);
async function jumpToError(key:ValueKey){
  if(props.propertyValuesCollapsed)emit("update:propertyValuesCollapsed",false);
  await nextTick();
  document.getElementById(`prop-value-${key}`)?.focus();
}

// —— 「新增 sheetset 字段」入口：展开定义面板并打开新增区（作用域预置为图纸集）——
const definitionPanel=ref<InstanceType<typeof PropertyDefinitionPanel>|null>(null);
async function addSheetsetField(){
  if(props.propertyDefinitionsCollapsed)emit("update:propertyDefinitionsCollapsed",false);
  await nextTick();
  void definitionPanel.value?.openAdd("sheetset");
}
</script>
<template>
  <section class="properties-view" role="tabpanel" id="panel-properties" aria-label="属性">
    <div v-if="propertySummaryError" class="error-summary" role="alert">
      <p class="error-summary-title">{{ propertySummaryError }}</p>
      <button v-for="[key,message] in fieldErrorEntries" :key="key" type="button" class="error-summary-jump" @click="jumpToError(key)">{{ labelOf(key) }}：{{ message }}</button>
    </div>
    <PropertyDefinitionPanel
      :definitions="workspace.sheet_set.property_definitions"
      :form="propertyDefinitionForm"
      :collapsed="propertyDefinitionsCollapsed"
      :query="propertyDefinitionsQuery"
      :scope-filter="propertyDefinitionsScope"
      :page="propertyDefinitionsPage"
      ref="definitionPanel"
      @add-definition="$emit('queuePropertyDefinition')"
      @delete-definition="definition=>$emit('queueDeleteProperty',definition)"
      @update:collapsed="value=>$emit('update:propertyDefinitionsCollapsed',value)"
      @update:query="value=>$emit('update:propertyDefinitionsQuery',value)"
      @update:scope-filter="value=>$emit('update:propertyDefinitionsScope',value)"
      @update:page="value=>$emit('update:propertyDefinitionsPage',value)"
    />
    <PropertyCsvPanel
      :workspace-id="workspace.id"
      :has-csv="hasCsv" :csv-preview="csvPreview" :csv-executable="csvExecutable" :writes-disabled="repairWritesDisabled"
      :collapsed="propertyCsvCollapsed" :csv-open="propertyCsvOpen"
      @read-csv="$emit('readCsv',$event)" @preview-csv="$emit('previewCsv')" @import-csv="$emit('importCsv')"
      @update:collapsed="value=>$emit('update:propertyCsvCollapsed',value)"
      @update:csv-open="value=>$emit('update:propertyCsvOpen',value)"
    />
    <PropertyValuePanel
      v-if="propertyInput&&propertyBase&&propertyDraft"
      :input="propertyInput" :base="propertyBase" :draft="propertyDraft"
      :status-of="propertyStatusOf" :errors="propertyErrors"
      :matched-keys="propertyMatchedKeys" :hidden-dirty-count="propertyHiddenDirtyCount"
      :search="propertySearch" :search-mode="propertySearchMode" :changed-only="propertyChangedOnly"
      :active-key="propertyActiveKey"
      :collapsed="propertyValuesCollapsed"
      @set-value="(key,value)=>$emit('setPropertyValue',key,value)"
      @revert-value="key=>$emit('revertValue',key)"
      @submit="$emit('submitValues')"
      @discard="$emit('discardPropertyInput')"
      @update:search="value=>$emit('update:propertySearch',value)"
      @update:search-mode="value=>$emit('update:propertySearchMode',value)"
      @update:changed-only="value=>$emit('update:propertyChangedOnly',value)"
      @update:active-key="key=>$emit('update:propertyActiveKey',key)"
      @update:collapsed="value=>$emit('update:propertyValuesCollapsed',value)"
      @add-sheetset-field="addSheetsetField"
    />
  </section>
</template>
<style scoped>
/* 三张独立语义卡片：定义在上、CSV 居中、值在下；16px 卡片间距（--space-4），卡片间不留旧 margin 叠加 */
.properties-view{display:flex;flex-direction:column;gap:var(--space-4);min-width:0}
/* 错误摘要：摘要文案 + 字段错误跳转项（展开目标面板并聚焦字段） */
.error-summary{background:var(--color-danger-bg);border:1px solid var(--color-danger);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);display:flex;flex-direction:column;gap:var(--space-1)}
.error-summary-title{margin:0;color:var(--color-danger);font-weight:600}
.error-summary-jump{align-self:flex-start;color:var(--color-danger);text-decoration:underline;text-align:left;font-size:13px;min-height:36px;padding:2px var(--space-2);border:1px solid transparent;border-radius:var(--radius-sm);background:transparent}
.error-summary-jump:hover{background:var(--color-bg-surface)}
</style>
