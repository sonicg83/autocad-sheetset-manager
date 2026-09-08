<script setup lang="ts">
// 设置中心模态对话框（PLAN-DM-019 任务 10，SPEC-DM-011 SC-02/03/05/06/07/08/09/11/12/14）。
// 容器职责：分区导航、编辑缓冲、即时校验、保存状态机、关闭守卫与焦点管理；
// 单字段渲染拆分至 SettingsFormRow.vue。样式全部组件作用域，仅引用 SPEC-DM-006 令牌。
// <dialog> showModal 提供原生焦点圈闭与 ::backdrop 遮罩（拖放不穿透，SC-14）；
// 关闭确认 ConfirmModal 置于 <dialog> 子树内，使其遮罩能盖住对话框内容。
import {computed,nextTick,ref,watch} from "vue";
import {ApiError} from "../../api/client";
import {fetchAbout} from "../../api/settings";
import type {AboutInfo,SettingsItem,SettingsValue} from "../../api/settings";
import {getShellBridge,selectSettingsPath,shellReady} from "../../api/shell";
import {useConfirm} from "../../composables/useConfirm";
import {useSettings} from "../../composables/useSettings";
import ConfirmModal from "../ui/ConfirmModal.vue";
import SettingsFormRow from "./SettingsFormRow.vue";

export type SettingsToast={type:"ok"|"fail";title:string;body:string};
const props=defineProps<{
  open:boolean;
  // SC-13 保存反馈复用宿主 useToast（ToastHost 挂在 App.vue）
  pushToast:(toast:SettingsToast)=>void;
}>();
const emit=defineEmits<{close:[]}>();

const {snapshot,loading,load,save}=useSettings();
const {state:confirmState,confirmAction,resolve:resolveConfirm}=useConfirm();

const dialogEl=ref<HTMLDialogElement|null>(null);
const section=ref<"general"|"about">("general");
const about=ref<AboutInfo|null>(null);
const aboutFailed=ref(false);
const edits=ref<Record<string,SettingsValue>>({}); // key → 编辑缓冲；删除键=回退到快照值
const pendingUnset=ref<string[]>([]); // 恢复继承标记：点击不落盘，随下次保存经 unset 提交
const fieldErrors=ref<Record<string,string>>({}); // 即时校验 + 422 逐字段回显
const saving=ref(false);
const savedVisible=ref(false);
const conflictNotice=ref(""); // 409：配置已被其他窗口修改（输入保留，快照已刷新）
const saveFailedNotice=ref(""); // 其他保存失败（网络/5xx）：内存值不替换
const loadFailed=ref(false);
let savedTimer:ReturnType<typeof setTimeout>|null=null;
let opener:HTMLElement|null=null; // 触发按钮（齿轮），关闭时归还焦点

// ---- 打开/关闭生命周期 ----
watch(()=>props.open,async open=>{
  if(open){
    opener=document.activeElement instanceof HTMLElement?document.activeElement:null;
    section.value="general";edits.value={};pendingUnset.value=[];fieldErrors.value={};
    conflictNotice.value="";saveFailedNotice.value="";loadFailed.value=false;about.value=null;aboutFailed.value=false;
    dialogEl.value?.showModal();
    await loadSettings();
  }else if(dialogEl.value?.open){
    dialogEl.value.close();
  }
});

async function loadSettings(){
  loadFailed.value=false;
  try{
    await load();
    await nextTick();
    focusFirstField();
  }catch{
    loadFailed.value=true; // 快照为 null，面板降级为"加载失败 + 重试"
  }
}

function focusFirstField(){
  dialogEl.value?.querySelector<HTMLElement>(".panel input, .panel button")?.focus();
}

async function tryClose(){
  if(confirmState.open)return; // 关闭确认自身打开时，Esc 归确认模态处理
  if(!hasUnsaved.value){close();return}
  // SC-08：有未保存修改不静默丢弃——确认"放弃修改并关闭 / 留在此处"
  const discard=await confirmAction({
    title:"有未保存的修改",
    message:"关闭将放弃本次全部未保存修改，已保存的配置不受影响。",
    confirmText:"放弃修改并关闭",
    cancelText:"留在此处",
  });
  if(discard)close();
}

function close(){
  dialogEl.value?.close();
  emit("close");
  opener?.focus(); // SC-09：焦点归还触发按钮
}

// 点击遮罩（::backdrop 命中 dialog 元素自身）等同取消
function onBackdropClick(event:MouseEvent){
  if(event.target===dialogEl.value)void tryClose();
}

function onCancel(event:Event){
  event.preventDefault(); // 接管 Esc：走关闭守卫而非直接关闭
  void tryClose();
}

// ---- 编辑缓冲与校验 ----
const items=computed(()=>snapshot.value?.items??[]);
const groups=computed(()=>{
  const result:{category:string;items:SettingsItem[]}[]=[];
  for(const item of items.value){
    const group=result.find(entry=>entry.category===item.category);
    if(group)group.items.push(item);
    else result.push({category:item.category,items:[item]});
  }
  return result; // 注册表顺序即首次出现顺序（后端稳定排序）
});
const schemaBlocked=computed(()=>snapshot.value?.schemaBlocked??false);

function localError(item:SettingsItem):string|undefined{
  if(item.control==="int"&&item.key in edits.value){
    const value=edits.value[item.key];
    if(value===""||typeof value!=="number"||!Number.isInteger(value))return "必须为整数";
    if(item.min!==undefined&&value<item.min||item.max!==undefined&&value>item.max)return `必须在 ${item.min}–${item.max} 之间`;
  }
  if(item.control==="path"&&typeof edits.value[item.key]==="string"&&/[<>"|?*]/.test(edits.value[item.key] as string))return "含有路径非法字符";
  return undefined;
}
function rowError(item:SettingsItem):string|undefined{
  return fieldErrors.value[item.key]??localError(item);
}
const hasValidationError=computed(()=>items.value.some(item=>rowError(item)!==undefined));
const hasUnsaved=computed(()=>items.value.some(item=>item.key in edits.value&&String(edits.value[item.key])!==String(item.value??""))||pendingUnset.value.length>0);
const saveDisabled=computed(()=>saving.value||schemaBlocked.value||!hasUnsaved.value||hasValidationError.value);

function onUpdate(key:string,value:SettingsValue){
  edits.value[key]=value;
  delete fieldErrors.value[key];
  // 编辑中的键不再随 unset 提交（后端 set+unset 同键时 unset 生效，会丢弃编辑）
  pendingUnset.value=pendingUnset.value.filter(item=>item!==key);
}
function onClear(key:string){onUpdate(key,null)} // nullable path 清除=写 null
function onUnset(key:string){
  if(pendingUnset.value.includes(key)){
    pendingUnset.value=pendingUnset.value.filter(item=>item!==key);
    return;
  }
  // 标记恢复继承时丢弃同键编辑缓冲：与 onUpdate 移除 pendingUnset 对称，
  // 避免 set+unset 同键提交（后端 unset 生效会静默丢弃用户编辑）
  delete edits.value[key];
  pendingUnset.value=[...pendingUnset.value,key];
}
async function onBrowse(key:string){
  const item=items.value.find(entry=>entry.key===key);
  if(!item)return;
  const filter=item.fileFilter?.includes("exe")?"exe":item.fileFilter?.includes("dll")?"dll":"folder";
  const result=await selectSettingsPath(filter); // undefined=桥不可用（按钮已禁用）/null=取消/string=路径
  if(typeof result==="string")onUpdate(key,result);
}

// ---- 保存状态机（SC-07）----
async function onSave(){
  const firstError=items.value.find(item=>rowError(item)!==undefined);
  if(firstError){jumpToError(firstError.key);return}
  const set:Record<string,unknown>={};
  for(const item of items.value){
    if(!(item.key in edits.value))continue;
    if(String(edits.value[item.key])===String(item.value??""))continue;
    const value=edits.value[item.key];
    // 空串/纯空白路径=清空覆盖，写 null（与后端规整规则一致）
    set[item.key]=item.control==="path"&&typeof value==="string"&&!value.trim()?null:value;
  }
  if(!Object.keys(set).length&&!pendingUnset.value.length)return;
  saving.value=true;conflictNotice.value="";saveFailedNotice.value="";
  try{
    await save(set,[...pendingUnset.value]);
    edits.value={};pendingUnset.value=[];fieldErrors.value={};
    showSaved();
    // SC-13：编号规则/并发相关配置变更后，追加预览重算提示
    const previewKeys=["enable_add_number_suffix","number_suffix_type","cad_max_parallel"];
    const recalc=Object.keys(set).some(key=>previewKeys.includes(key));
    props.pushToast({type:"ok",title:"已保存",body:recalc?"相关预览将按新配置重算":"设置已更新"});
  }catch(error){
    if(error instanceof ApiError&&error.status===422){
      fieldErrors.value=error.fields??{};
      const key=Object.keys(fieldErrors.value)[0];
      if(key)jumpToError(key); // SC-06：焦点落到第一个错误字段
    }else if(error instanceof ApiError&&error.status===409){
      conflictNotice.value="配置已被其他窗口修改，已刷新为最新配置，请核对后重试";
      await load(); // 输入缓冲保留，仅刷新快照与修订号
    }else{
      saveFailedNotice.value=error instanceof Error?error.message:"保存失败，请重试";
    }
  }finally{
    saving.value=false;
  }
}

function jumpToError(key:string){
  const input=dialogEl.value?.querySelector<HTMLElement>(`[data-key="${key}"]`);
  input?.scrollIntoView({block:"center"});
  input?.focus();
}

function showSaved(){
  savedVisible.value=true;
  if(savedTimer)clearTimeout(savedTimer);
  savedTimer=setTimeout(()=>{savedVisible.value=false},2500);
}

// ---- 诊断横幅（SC-12）----
const DIAG_TEXTS:Record<string,string>={
  SETTINGS_FILE_MISSING:"用户配置文件不存在，本次会话按默认值运行",
  SETTINGS_FILE_CORRUPT:"用户配置文件无法读取（已备份），本次会话按默认值运行",
};
const diagLines=computed(()=>{
  const lines:string[]=[];
  // schema 过新时后端 diagnostics 为空（resolver 降级分支），只读态由 schema_blocked 驱动
  if(schemaBlocked.value)lines.push("设置文件 schema 版本与当前程序不兼容，已进入只读模式，不能保存。（诊断码 SETTINGS_SCHEMA_NEWER）");
  for(const entry of snapshot.value?.diagnostics??[]){
    // 诊断元素为"机器码"或后端附带的中文说明；已知机器码映射为友好文案
    lines.push(DIAG_TEXTS[entry]!==undefined?`${DIAG_TEXTS[entry]}。（诊断码 ${entry}）`:entry);
  }
  return lines;
});

// ---- 关于分区（SC-11）----
async function showAbout(){
  section.value="about";
  if(about.value||aboutFailed.value)return;
  try{
    about.value=await fetchAbout();
  }catch{
    aboutFailed.value=true;
  }
}
function openExternal(url:string){
  // 本期范围：浏览器开发态 window.open；桌面壳外链增强登记在 Task 12，不在对话框加桥方法
  if(getShellBridge()){
    props.pushToast({type:"ok",title:"外部链接",body:"桌面版暂不支持在系统浏览器打开链接，请复制地址访问"});
    return;
  }
  window.open(url,"_blank","noopener");
}

// 浏览按钮可用性随桥就绪响应式更新（浏览器开发态/桥缺失 → 禁用）
const browseDisabled=computed(()=>{
  if(!shellReady.value)return true;
  const bridge=getShellBridge();
  return bridge===null||typeof bridge.select_file!=="function";
});
</script>
<template>
  <!-- dragover/drop 就地拦截并阻止冒泡：壳侧 drop 监听挂 document（shell.py），
       showModal 只挡命中测试不挡事件冒泡，不 stop 会在对话框背后打开工作区（SC-14） -->
  <dialog ref="dialogEl" class="settings-dialog" aria-labelledby="settings-title" @cancel="onCancel" @click="onBackdropClick" @dragover.prevent.stop @drop.prevent.stop>
    <div class="dlg">
      <div class="dlg-head">
        <h2 id="settings-title">设置</h2>
        <span v-if="snapshot" class="rev-pill">配置修订 r{{snapshot.configRevision}}</span>
        <span class="spacer"></span>
        <button type="button" class="icon-btn" aria-label="关闭设置" :disabled="saving" @click="tryClose">✕</button>
      </div>
      <p v-if="loading&&!snapshot" class="loading" role="status">正在加载设置…</p>
      <div v-else-if="loadFailed" class="dlg-body">
        <div class="panel load-failed">
          <p>设置加载失败，请检查服务是否可用。</p>
          <button type="button" @click="loadSettings">重试</button>
        </div>
      </div>
      <template v-else-if="snapshot">
        <div v-if="diagLines.length" class="diag" :class="{readonly:schemaBlocked}" role="alert">
          <p v-for="line in diagLines" :key="line">{{line}}</p>
        </div>
        <div class="dlg-body">
          <nav class="sections" role="tablist" aria-label="设置分区">
            <button type="button" role="tab" :aria-selected="section==='general'" @click="section='general'">常规配置</button>
            <button type="button" role="tab" :aria-selected="section==='about'" @click="showAbout">关于</button>
          </nav>
          <div class="panel">
            <template v-if="section==='general'">
              <div v-for="group in groups" :key="group.category" class="group">
                <div class="group-title">{{group.category}}</div>
                <SettingsFormRow
                  v-for="item in group.items" :key="item.key" :item="item"
                  :edit-value="edits[item.key]" :error="rowError(item)"
                  :pending-unset="pendingUnset.includes(item.key)"
                  :browse-disabled="browseDisabled" :disabled="schemaBlocked"
                  @update="onUpdate" @clear="onClear" @unset="onUnset" @browse="onBrowse"
                />
              </div>
            </template>
            <template v-else>
              <div class="about-block">
                <h3>应用</h3>
                <p v-if="about">DST Manager <strong>v{{about.version}}</strong></p>
                <p v-else-if="aboutFailed" class="f-hint">关于信息加载失败。</p>
                <p v-else class="f-hint" role="status">正在加载…</p>
              </div>
              <div class="about-block">
                <h3>开源协议（MIT）</h3>
                <div v-if="about" class="license">{{about.license.text}}</div>
                <div v-else-if="aboutFailed" class="f-hint">关于信息加载失败。</div>
              </div>
              <div class="about-block">
                <h3>项目主页 / 反馈</h3>
                <p v-if="about" class="link-line">
                  <button type="button" class="link-btn" @click="openExternal(about.homepage)">项目主页</button>
                  <button type="button" class="link-btn" @click="openExternal(about.feedbackUrl)">问题反馈</button>
                </p>
                <p v-else-if="!aboutFailed" class="f-hint" role="status">正在加载…</p>
              </div>
            </template>
          </div>
        </div>
        <div class="dlg-foot">
          <span v-if="conflictNotice" class="foot-notice warn" role="alert">{{conflictNotice}}</span>
          <span v-else-if="saveFailedNotice" class="foot-notice error" role="alert">{{saveFailedNotice}}</span>
          <span v-if="savedVisible" class="saved-pill" role="status">已保存</span>
          <span class="spacer"></span>
          <button type="button" :disabled="saving" @click="tryClose">取消</button>
          <button type="button" class="primary" :disabled="saveDisabled" @click="onSave">{{saving?"保存中…":"保存"}}</button>
        </div>
      </template>
    </div>
    <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  </dialog>
</template>
<style scoped>
.settings-dialog{padding:0;width:760px;max-width:calc(100vw - 32px);height:min(620px,86vh);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);background:var(--color-bg-surface);color:var(--color-text-primary);box-shadow:var(--shadow-3)}
.settings-dialog::backdrop{background:rgba(16,24,40,.55)}
.dlg{display:flex;flex-direction:column;height:100%}
.dlg-head{display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border-subtle);flex-shrink:0}
.dlg-head h2{margin:0;font-size:16px}
.rev-pill{font-size:12px;padding:2px 10px;border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary)}
.spacer{flex:1}
.icon-btn{border:0;background:transparent;color:var(--color-text-secondary);cursor:pointer;font-size:14px;min-width:32px;min-height:32px;border-radius:var(--radius-md)}
.icon-btn:hover:not(:disabled){background:var(--color-bg-muted)}
.loading{margin:var(--space-5);color:var(--color-text-secondary)}
.load-failed{display:flex;flex-direction:column;gap:var(--space-3);align-items:flex-start}
.load-failed button{padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);cursor:pointer}
.diag{border:1px solid var(--color-warning);background:var(--color-warning-bg);color:var(--color-warning);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);font-size:12px;line-height:1.8;margin:var(--space-3) var(--space-4) 0;flex-shrink:0}
.diag p{margin:0}
.diag.readonly{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.dlg-body{display:flex;flex:1;min-height:0}
.sections{width:150px;flex-shrink:0;border-right:1px solid var(--color-border-subtle);padding:var(--space-2);display:flex;flex-direction:column;gap:var(--space-1)}
.sections button{border:0;background:transparent;text-align:left;color:var(--color-text-secondary);padding:9px var(--space-3);border-radius:var(--radius-md);cursor:pointer;font-size:13px}
.sections button[aria-selected="true"]{background:var(--color-info-bg);color:var(--color-accent);font-weight:600}
.panel{flex:1;overflow:auto;padding:var(--space-3) var(--space-4)}
.group{margin-bottom:var(--space-2)}
.group-title{font-weight:600;font-size:13px;border-left:3px solid var(--color-accent);padding-left:var(--space-2);margin:var(--space-3) 0 var(--space-2)}
.about-block{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);margin-bottom:var(--space-3)}
.about-block h3{margin:0 0 var(--space-2);font-size:13px}
.about-block p{margin:0}
.license{font-size:12px;line-height:1.7;color:var(--color-text-secondary);white-space:pre-wrap;background:var(--color-bg-canvas);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);max-height:200px;overflow:auto}
.link-line{display:flex;gap:var(--space-2)}
.dlg-foot{display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);flex-shrink:0}
.foot-notice{font-size:12px;line-height:1.6}
.foot-notice.warn{color:var(--color-warning)}
.foot-notice.error{color:var(--color-danger)}
.saved-pill{font-size:12px;color:var(--color-success)}
.dlg-foot button{padding:9px var(--space-4);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:14px}
.dlg-foot button:disabled{cursor:not-allowed;opacity:.5}
.dlg-foot button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
</style>
