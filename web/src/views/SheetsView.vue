<script setup lang="ts">
// 标签① 图纸：图纸集/子集/图纸导航、批量新增与新建子集表单、编辑区（受控组件，业务状态仍由 App.vue 持有）
import type {Diagnostic,LayoutSourceType,Placement,Sheet,Subset,Workspace} from "../api/contracts";
import ProjectNavigation from "../components/ProjectNavigation.vue";
import SheetTable from "../components/SheetTable.vue";

type SheetRow={subset:Subset;sheet:Sheet};
export type InsertSheetForm={subsetId:string;sequence:string;direction:Placement;count:string;sourceType:LayoutSourceType;sourceFile:string;sourceLayout:string};
export type InsertSubsetForm={sequence:string;direction:Placement;title:string;initialSheetCount:string;baseTemplateFile:string;templateFile:string;templateLayout:string};

defineProps<{
  workspace:Workspace;
  selected:Subset|null;
  blocking:Diagnostic[];
  selectedSheetIds:string[];
  sheetPropertyNames:string[];
  filteredSheetRows:SheetRow[];
  allSheetRows:SheetRow[];
  visibleSheetRows:SheetRow[];
  pendingSheetIds:Set<string>;
  diagnosticObjectIds:Set<string>;
  allFilteredSelected:boolean;
  insertSheetForm:InsertSheetForm;
  insertSubsetForm:InsertSubsetForm;
  layoutOptions:string[];layoutLoading:boolean;layoutError:string;layoutManual:boolean;
  subsetLayoutOptions:string[];subsetLayoutLoading:boolean;subsetLayoutError:string;subsetLayoutManual:boolean;
}>();
const searchText=defineModel<string>("searchText",{default:""});
const subsetFilter=defineModel<string>("subsetFilter",{default:"all"});
const pathFilter=defineModel<string>("pathFilter",{default:"all"});
const diagnosticFilter=defineModel<string>("diagnosticFilter",{default:"all"});
const pendingFilter=defineModel<string>("pendingFilter",{default:"all"});
const renderLimit=defineModel<number>("renderLimit",{default:80});
const bulkPropertyName=defineModel<string>("bulkPropertyName",{default:""});
const bulkPropertyValue=defineModel<string>("bulkPropertyValue",{default:""});
defineEmits<{
  selectSubset:[id:string];
  toggleFilteredSelection:[];toggleSheet:[id:string];queueBulkSheetProperty:[];
  selectTemplateFile:[];selectSubsetTemplateFile:[];selectBaseTemplateFile:[];
  queueSubsetTitle:[];queueSheetProperties:[sheet:Sheet];queueDelete:[sheet:Sheet];queueDeleteSubset:[];
  queueInsertSheet:[];queueInsertSubset:[];
}>();
</script>
<template>
  <section class="sheets-view" role="tabpanel" id="panel-sheets" aria-label="图纸">
    <div class="sheets-head">
      <h2>图纸集 / 子集 / 图纸</h2>
      <div class="counts"><span>子集 {{workspace.sheet_set.subset_count}}</span><span>图纸 {{workspace.sheet_set.sheet_count}}</span><span>阻断诊断 {{blocking.length}}</span></div>
    </div>

    <section class="panel sheet-browser" aria-label="图纸导航与筛选">
      <div class="section-title"><div><h2>图纸集 / 子集 / 图纸导航</h2><p>派生字段只读；搜索覆盖图号、标题、自定义属性及 DWG 文件名、相对路径和解析路径。</p></div><strong>匹配 {{filteredSheetRows.length}} / 全部 {{allSheetRows.length}} 张</strong></div>
      <div class="filter-grid">
        <label>搜索图纸<input v-model="searchText" placeholder="图号、标题、属性或 DWG" @input="renderLimit=80"></label>
        <label>子集<select v-model="subsetFilter" @change="renderLimit=80"><option value="all">全部子集</option><option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{subset.display_name}}</option></select></label>
        <label>路径状态<select v-model="pathFilter" @change="renderLimit=80"><option value="all">全部</option><option value="resolved">已解析</option><option value="unresolved">未解析</option></select></label>
        <label>诊断状态<select v-model="diagnosticFilter" @change="renderLimit=80"><option value="all">全部</option><option value="blocking">有阻断诊断</option><option value="clean">无阻断诊断</option></select></label>
        <label>待变更状态<select v-model="pendingFilter" @change="renderLimit=80"><option value="all">全部</option><option value="pending">待变更</option><option value="unchanged">未变更</option></select></label>
      </div>
      <div class="bulk-bar"><button :disabled="!filteredSheetRows.length" @click="$emit('toggleFilteredSelection')">{{allFilteredSelected?'取消全选':'全选当前结果'}}</button><span>已选 {{selectedSheetIds.length}}</span><label>既有图纸属性<select v-model="bulkPropertyName"><option value="">请选择</option><option v-for="name in sheetPropertyNames" :key="name" :value="name">{{name}}</option></select></label><label>批量值<input v-model="bulkPropertyValue"></label><button :disabled="!selectedSheetIds.length||!bulkPropertyName" @click="$emit('queueBulkSheetProperty')">批量加入草稿</button></div>
      <SheetTable :rows="visibleSheetRows" :selected-ids="selectedSheetIds" :pending-ids="pendingSheetIds" :diagnostic-ids="diagnosticObjectIds" @toggle="$emit('toggleSheet',$event)" @open-subset="$emit('selectSubset',$event)" />
      <button v-if="visibleSheetRows.length<filteredSheetRows.length" @click="renderLimit+=80">继续加载（尚余 {{filteredSheetRows.length-visibleSheetRows.length}}）</button>
    </section>

    <section class="editor">
      <ProjectNavigation :subsets="workspace.sheet_set.subsets" :selected-id="selected?.id??''" @select="$emit('selectSubset',$event)" />
      <article>
        <section v-if="selected" class="subset-editor"><div class="form-row"><label>当前子集标题<input v-model="selected.title"></label><button @click="$emit('queueSubsetTitle')">加入标题变更</button><button class="danger" @click="$emit('queueDeleteSubset')">删除整个子集</button></div><p class="derived">只读图号范围：{{selected.number_range||'—'}} · 显示名：{{selected.display_name}}</p>
          <table><thead><tr><th>图号</th><th>派生标题</th><th>自定义属性</th><th></th></tr></thead><tbody><tr v-for="sheet in selected.sheets" :key="sheet.id"><td><span>{{sheet.number}}</span></td><td><span>{{sheet.title}}</span></td><td><div class="property-values"><label v-for="(_,name) in sheet.custom_properties" :key="name">{{name}}<input v-model="sheet.custom_properties[name]"></label></div></td><td><button @click="$emit('queueSheetProperties',sheet)">加入属性变更</button><button class="danger" @click="$emit('queueDelete',sheet)">删除</button></td></tr></tbody></table>
        </section>

        <fieldset><legend>批量新增图纸</legend><div class="form-grid">
          <label>目标子集<select v-model="insertSheetForm.subsetId"><option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{subset.display_name}}</option></select></label>
          <label>图纸序号<input v-model="insertSheetForm.sequence" inputmode="numeric"></label><label>图纸方向<select v-model="insertSheetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>新增图纸数量<input v-model="insertSheetForm.count" inputmode="numeric"></label>
          <label>模板来源<select v-model="insertSheetForm.sourceType"><option value="template_layout">DWG/DWT 模板布局</option><option value="existing_snapshot">已有布局</option></select></label><template v-if="insertSheetForm.sourceType==='existing_snapshot'"><label>来源说明<span>来源为目标子集 DWG 的第一个非 Model 布局</span></label></template><template v-else><label>布局模板文件<button type="button" aria-label="选择模板文件" @click="$emit('selectTemplateFile')">选择模板文件</button><span v-if="insertSheetForm.sourceFile">{{insertSheetForm.sourceFile}}</span></label><label>布局模板名称<span v-if="layoutLoading">正在读取布局…</span><template v-else-if="layoutError"><span class="error">{{layoutError}}</span><input v-model="insertSheetForm.sourceLayout"></template><select v-else-if="layoutOptions.length&&!layoutManual" v-model="insertSheetForm.sourceLayout"><option v-for="l in layoutOptions" :value="l">{{l}}</option></select></label></template>
        </div><button @click="$emit('queueInsertSheet')">批量新增图纸</button></fieldset>

        <fieldset><legend>新建子集</legend><div class="form-grid"><label>子集序号<input v-model="insertSubsetForm.sequence" inputmode="numeric"></label><label>子集方向<select v-model="insertSubsetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>子集标题<input v-model="insertSubsetForm.title"></label><label>初始图纸数<input v-model="insertSubsetForm.initialSheetCount" inputmode="numeric"></label><label>基础模板文件<button type="button" aria-label="选择基础模板文件" @click="$emit('selectBaseTemplateFile')">选择基础模板文件</button><span v-if="insertSubsetForm.baseTemplateFile">{{insertSubsetForm.baseTemplateFile}}</span></label><label>布局模板文件<button type="button" aria-label="选择布局模板文件" @click="$emit('selectSubsetTemplateFile')">选择布局模板文件</button><span v-if="insertSubsetForm.templateFile">{{insertSubsetForm.templateFile}}</span></label><label>布局模板名称<span v-if="subsetLayoutLoading">正在读取布局…</span><template v-else-if="subsetLayoutError"><span class="error">{{subsetLayoutError}}</span><input v-model="insertSubsetForm.templateLayout"></template><select v-else-if="subsetLayoutOptions.length&&!subsetLayoutManual" v-model="insertSubsetForm.templateLayout"><option v-for="l in subsetLayoutOptions" :value="l">{{l}}</option></select></label></div><button @click="$emit('queueInsertSubset')">新建子集</button></fieldset>
      </article>
    </section>
  </section>
</template>
<style scoped>
.sheets-view{display:block}
.sheets-head{display:flex;align-items:baseline;justify-content:space-between;gap:var(--space-3);margin-bottom:var(--space-4)}
.sheets-head h2{margin:0;font-size:17px;color:var(--color-text-primary)}
.counts{display:flex;gap:var(--space-4);font-size:13px;color:var(--color-text-secondary)}
.counts span{white-space:nowrap}
.editor{margin-top:var(--space-4)}
</style>
