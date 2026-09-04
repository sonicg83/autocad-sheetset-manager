<script setup lang="ts">
// 右缘任务浮层：实施进度 / 修改预览 / 诊断三页签（SPEC-DM-006 §4.1/§4.2/§7.2）
// 受控组件：open/tab 状态由 App.vue 持有（Task 7 toast 抑制与"查看"跳转依赖）；页签行复用 useShellTabs 键盘模型
// 折叠不卸载：面板体 hidden，页签行保留窄条（始终可见触发按钮 §4.3）；收起后任务继续执行
import {ref, watch} from "vue";
import type {CadGroup,CardinalityFrontier,DerivedSubset,Diagnostic,DstValidation,ExecutionEstimate,Job,Preview,RepairPreview,SemanticDiff,SourceBaseline,SubsetOperation} from "../api/contracts";
import {useShellTabs} from "../composables/useShellTabs";
import JobStatusPanel from "../components/JobStatusPanel.vue";
import PreviewPanel from "../components/PreviewPanel.vue";
import RepairStatusPanel from "../components/RepairStatusPanel.vue";

export type OverlayTab="prog"|"prev"|"diag";
const props=defineProps<{
  open:boolean;
  tab:OverlayTab;
  hasBlocking:boolean;
  hasRepair:boolean;
  job:Job|null;
  connectionMode:string;
  preview:Preview|null;
  // PreviewPanel 原样透传
  semanticDiff:SemanticDiff;
  estimate:ExecutionEstimate|null;
  cadValidationDeferred:boolean;
  cardinalityFrontier:CardinalityFrontier|null;
  subsetOperations:SubsetOperation[];
  sourceBaselines:SourceBaseline[];
  derivedSubsets:DerivedSubset[];
  groups:CadGroup[];
  // 诊断列表 + RepairStatusPanel 原样透传
  diagnostics:Diagnostic[];
  dstValidation:DstValidation|null;
  repairPreview:RepairPreview|null;
  isRepairPreviewing:boolean;
  isRepairExecuting:boolean;
}>();
const emit=defineEmits<{
  "update:tab":[tab:OverlayTab];
  fold:[];
  retry:[];
  "preview-repair":[];
  "execute-repair":[];
  "cancel-repair":[];
}>();
const OV_TABS=[
  {id:"prog" as const,label:"实施进度"},
  {id:"prev" as const,label:"修改预览"},
  {id:"diag" as const,label:"诊断"},
];
// 页签行复用 useShellTabs 键盘模型；受控：外部 tab prop 变化时同步激活态，内部激活变化回写外部
const {active,select,onKeydown}=useShellTabs<OverlayTab>(["prog","prev","diag"],"prog");
watch(()=>props.tab,tab=>{if(active.value!==tab)active.value=tab});
watch(active,tab=>{if(props.tab!==tab)emit("update:tab",tab)});
function clickTab(id:OverlayTab){select(id)}
function onTabKeydown(e:KeyboardEvent){onKeydown(e)}
// 诊断完整值读取与复制（SPEC-DM-009 S-04：路径与后端原值一致且可复制）
const copiedCode=ref<string|null>(null);
async function copyText(text:string){
  try{await navigator.clipboard.writeText(text)}
  catch{// 剪贴板不可用时回退到临时文本域 execCommand
    const ta=document.createElement("textarea");
    ta.value=text;ta.setAttribute("readonly","");ta.style.position="fixed";
    document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();
  }
}
async function copyDiag(item:Diagnostic){
  const text=`${item.code}：${item.message}`;
  copiedCode.value=item.code;
  await copyText(text);
  window.setTimeout(()=>{if(copiedCode.value===item.code)copiedCode.value=null},1500);
}
</script>
<template>
  <aside class="task-overlay" :class="{collapsed:!open}" role="complementary" aria-label="任务浮层">
    <div class="ov-tabs" role="tablist" aria-label="任务页签">
      <button v-for="tab in OV_TABS" :key="tab.id" type="button" class="ov-tab" role="tab"
        :id="`ov-tab-${tab.id}`" :aria-selected="active===tab.id" :aria-controls="`ov-panel-${tab.id}`"
        :tabindex="active===tab.id?0:-1"
        :aria-description="tab.id==='diag'&&hasBlocking?'存在阻断诊断，普通发布已让位给修复（§6.9）':undefined"
        :hidden="!open" @click="clickTab(tab.id)" @keydown="onTabKeydown">
        {{tab.label}}<span v-if="tab.id==='diag'&&hasBlocking" class="ov-dot" aria-hidden="true">●</span>
      </button>
      <button type="button" class="ov-fold" :aria-expanded="open" aria-controls="ov-body"
        :aria-label="open?'收起任务浮层':'展开任务浮层'" @click="emit('fold')">{{open?'»':'«'}}</button>
    </div>
    <div class="ov-body" id="ov-body" :hidden="!open">
      <div v-if="active==='prog'" class="ov-panel" id="ov-panel-prog" role="tabpanel" aria-labelledby="ov-tab-prog">
        <JobStatusPanel v-if="job" :job="job" :connection-mode="connectionMode" @retry="emit('retry')" />
      </div>
      <div v-else-if="active==='prev'" class="ov-panel" id="ov-panel-prev" role="tabpanel" aria-labelledby="ov-tab-prev">
        <PreviewPanel v-if="preview" :preview="preview" :semantic-diff="semanticDiff" :estimate="estimate" :cad-validation-deferred="cadValidationDeferred" :cardinality-frontier="cardinalityFrontier" :subset-operations="subsetOperations" :source-baselines="sourceBaselines" :derived-subsets="derivedSubsets" :groups="groups" />
      </div>
      <div v-else class="ov-panel" id="ov-panel-diag" role="tabpanel" aria-labelledby="ov-tab-diag">
        <details v-if="diagnostics.length" class="ov-diagnostics"><summary>诊断（{{diagnostics.length}}）</summary><ul class="diagnostics"><li v-for="item in diagnostics" :key="item.code+item.message" :class="item.severity"><span class="diag-text">{{item.code}}：{{item.message}}</span><button type="button" class="diag-copy" :aria-label="`复制诊断 ${item.code}`" @click="copyDiag(item)">{{copiedCode===item.code?"已复制":"复制"}}</button></li></ul></details>
        <RepairStatusPanel v-if="hasRepair&&dstValidation" :validation="dstValidation" :preview="repairPreview" :previewing="isRepairPreviewing" :executing="isRepairExecuting" @preview-repair="emit('preview-repair')" @execute-repair="emit('execute-repair')" @cancel="emit('cancel-repair')" />
        <p v-if="!diagnostics.length&&!hasRepair" class="ov-empty">无阻断诊断</p>
      </div>
    </div>
  </aside>
</template>
<style scoped>
.task-overlay{width:340px;flex-shrink:0;background:var(--color-bg-surface);border-left:1px solid var(--color-border-subtle);display:flex;flex-direction:column;min-height:0;transition:width .2s}
.task-overlay.collapsed{width:44px}
.task-overlay [hidden]{display:none!important}
.ov-tabs{display:flex;align-items:stretch;border-bottom:1px solid var(--color-border-subtle);flex-shrink:0}
.ov-tab{flex:1;padding:10px 4px;font-size:13px;color:var(--color-text-secondary);border:none;border-bottom:2px solid transparent;background:none;display:flex;align-items:center;justify-content:center;gap:5px;cursor:pointer;font-family:inherit;white-space:nowrap}
.ov-tab:hover:not([hidden]){color:var(--color-text-primary)}
.ov-tab[aria-selected="true"]{color:var(--color-accent);border-bottom-color:var(--color-accent)}
.ov-dot{color:var(--color-danger);font-size:10px}
.ov-fold{width:32px;height:32px;align-self:center;flex-shrink:0;margin-left:auto;border:none;background:none;color:var(--color-text-secondary);cursor:pointer;font-size:15px;font-family:inherit}
.ov-fold:hover{background:var(--color-bg-muted)}
.ov-body{flex:1;overflow:auto;padding:var(--space-4);min-height:0}
.ov-empty{color:var(--color-text-muted);font-size:13px}
.ov-diagnostics summary{cursor:pointer;font-weight:500}
.diagnostics{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--space-2)}
.diagnostics li{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.6;color:var(--color-text-primary)}
.diag-text{flex:1;min-width:0;word-break:break-word}
.diag-copy{flex-shrink:0;border:1px solid var(--color-border-subtle,var(--color-bg-surface-2));background:none;color:var(--color-text-secondary);border-radius:var(--radius-sm,6px);padding:1px 8px;font-size:12px;cursor:pointer;font-family:inherit}
.diag-copy:hover{color:var(--color-text-primary);border-color:var(--color-border,var(--color-bg-surface-2))}
</style>
