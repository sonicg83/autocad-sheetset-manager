<script setup lang="ts">
// 设置中心模态对话框（PLAN-DM-019 任务 10，SPEC-DM-011 SC-02/03/05/06/07/08/09/11/12/14）。
// 容器职责：分区导航、编辑缓冲、即时校验、保存状态机、关闭守卫与焦点管理；
// 单字段渲染拆分至 SettingsFormRow.vue，关于分区呈现拆分至 AboutSection.vue。样式全部组件作用域，
// 仅引用 SPEC-DM-006 令牌。
// <dialog> showModal 提供原生焦点圈闭与 ::backdrop 遮罩（拖放不穿透，SC-14）；
// 关闭确认 ConfirmModal 置于 <dialog> 子树内，使其遮罩能盖住对话框内容。
import {computed,nextTick,ref,watch} from "vue";
import {useI18n} from "vue-i18n";
import {ApiError} from "../../api/client";
import type {ApiFieldError,StructuredParams} from "../../api/client";
import type {ExtensionSummary} from "../../api/contracts";
import type {SettingsItem,SettingsValue} from "../../api/settings";
import {MAX_UNNUMBERED_KEYWORD_CHARS,MAX_UNNUMBERED_KEYWORDS} from "../../api/settings";
import {getShellBridge,selectSettingsPath,shellReady} from "../../api/shell";
import {useConfirm} from "../../composables/useConfirm";
import {useSettings} from "../../composables/useSettings";
import {useDialogFocus} from "../ui/dialogFocus";
import type {ExtensionsPanel} from "../../composables/useExtensions";
import AboutSection from "./AboutSection.vue";
import ConfirmModal from "../ui/ConfirmModal.vue";
import UiButton from "../ui/UiButton.vue";
import UiIcon from "../ui/UiIcon.vue";
import ExtensionSettingsHost from "./ExtensionSettingsHost.vue";
import ExtensionsSection from "./ExtensionsSection.vue";
import SettingsFormRow from "./SettingsFormRow.vue";

export type SettingsToast={type:"ok"|"fail";title:string;body:string};
const props=defineProps<{
  open:boolean;
  // SC-13 保存反馈复用宿主 useToast（ToastHost 挂在 App.vue）
  pushToast:(toast:SettingsToast)=>void;
  // 扩展分区（本次修复：停用可逆 / ARCH-DM-006 §7）。列表与启停由 App 装配；
  // 编排（取数、启停、失败就地呈现与开关焦点）归 ExtensionsSection，本对话框只把面板传下去。
  extensionsPanel:ExtensionsPanel;
}>();
const emit=defineEmits<{close:[]}>();

const {t,te}=useI18n();
const {snapshot,loading,load,save}=useSettings();
const {state:confirmState,confirmAction,resolve:resolveConfirm}=useConfirm();

const dialogEl=ref<HTMLDialogElement|null>(null);
// 保存成功语言切换后归还焦点的锚点（UiButton 组件实例，焦点落在其根 <button> $el 上）
const saveButtonEl=ref<InstanceType<typeof UiButton>|null>(null);
const errorSummaryEl=ref<HTMLDivElement|null>(null); // 422 错误摘要（tabindex=-1，可聚焦）
const section=ref<"general"|"about"|"extensions">("general");
// SC-17：当前进入的扩展配置子视图（同一 <dialog> 内的平级视图）与其宿主引用；
// 本对话框只装配「当前扩展 + 子视图页脚 + dirty 并入 hasUnsaved」，不承载设置状态
const configExtension=ref<ExtensionSummary|null>(null);
const configHost=ref<InstanceType<typeof ExtensionSettingsHost>|null>(null);
const extensionsSectionEl=ref<InstanceType<typeof ExtensionsSection>|null>(null);
const edits=ref<Record<string,SettingsValue>>({}); // key → 编辑缓冲；删除键=回退到快照值
const pendingUnset=ref<string[]>([]); // 恢复继承标记：点击不落盘，随下次保存经 unset 提交
const fieldErrors=ref<Record<string,ApiFieldError>>({}); // 422 逐字段结构化错误（message_key+params）
const saving=ref(false);
const conflictNotice=ref(""); // 409：配置已被其他窗口修改（输入保留，快照已刷新）
const saveFailedNotice=ref(""); // 其他保存失败（网络/5xx）：内存值不替换，文案按当前语言
const saveFailedDetail=ref(""); // 原始错误消息：仅作诊断详情（tooltip），不作界面翻译
const loadFailed=ref(false);
let opener:HTMLElement|null=null; // 触发按钮（齿轮），关闭时归还焦点

// ---- 打开/关闭生命周期 ----
watch(()=>props.open,async open=>{
  if(open){
    opener=document.activeElement instanceof HTMLElement?document.activeElement:null;
    section.value="general";edits.value={};pendingUnset.value=[];fieldErrors.value={};
    configExtension.value=null; // 每次打开都从扩展列表视图开始（子视图不跨会话保留）
    conflictNotice.value="";saveFailedNotice.value="";saveFailedDetail.value="";loadFailed.value=false;
    dialogEl.value?.showModal();
    await loadSettings();
  }else if(dialogEl.value?.open){
    dialogEl.value.close();
  }
});

// 焦点工具接在**原生生命周期之后**（两个 watch 都是 post flush，回调按注册顺序执行）：
// 打开时要先 `showModal()` 才能看到 top layer 里的可聚焦元素，关闭时要先 `close()` 才能归还焦点。
// 分工（PLAN-DM-029 Task 10 Step 4）：
// · **Tab 圈闭**归工具（原先手写的那份已删）；它 @keydown 绑在 <dialog> 上，与原先一致。
//   原先多出的 `!dialog.contains(active)` 分支在 <dialog> 绑定的 keydown 下**不可达**：
//   焦点在对话框外时事件根本不会冒泡到本元素——该分支是防御性死代码，删去无行为差异。
// · **初始焦点**仍由 `loadSettings()` 里的 `focusFirstField()` 负责：落点是**数据相关**的
//   （要等设置快照渲染出 `.panel input` 才能在），工具只在 open 翻转那一刻跑，无法代替。
// · **Escape** 仍走原生 `@cancel`（`onCancel`）：平台负责「只作用于最上层」，且子视图内
//   的 Esc 要退化为「返回扩展列表」——所以**不**传 `onEscape`（与 UnsavedInputDialog 同一口径）。
// · 归还焦点仍由 `close()` 显式完成（SC-09），`returnFocus` 只是把同一落点交给工具的关闭分支。
const {onDialogKeydown}=useDialogFocus({
  open:()=>props.open,
  container:dialogEl,
  initialFocus:()=>dialogEl.value,
  returnFocus:()=>opener,
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
    title:t("settings.confirm.title"),
    message:t("settings.confirm.message")+(configHost.value?.dirty===true?` ${t("settings.extensionSettings.closeExtra")}`:""),
    confirmText:t("settings.confirm.discard"),
    cancelText:t("settings.confirm.stay"),
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
  if(event.target!==dialogEl.value)return;
  // SC-17：子视图内遮罩点击与 Esc 同一分级（等价于返回扩展列表）
  if(configExtension.value){void configHost.value?.back();return}
  void tryClose();
}

function onCancel(event:Event){
  event.preventDefault(); // 接管 Esc：走关闭守卫而非直接关闭
  // SC-17：子视图内 Esc 等价于「返回扩展列表」（脏时先确认），不是关闭本对话框
  if(configExtension.value){void configHost.value?.back();return}
  void tryClose();
}

// ---- 编辑缓冲与校验 ----
const items=computed(()=>snapshot.value?.items??[]);
// 按 category key 分组（I18N-09）：稳定键分组，注册表顺序即首次出现顺序（后端稳定排序）；
// 迁移期兼容中文 category 回退已随阶段三（Task 10）删除
const groups=computed(()=>{
  const result:{key:string;items:SettingsItem[]}[]=[];
  for(const item of items.value){
    const key=item.categoryKey??item.key;
    const group=result.find(entry=>entry.key===key);
    if(group)group.items.push(item);
    else result.push({key,items:[item]});
  }
  return result;
});
function groupTitle(key:string):string{
  return t(key); // category key 由注册表保证存在
}
const schemaBlocked=computed(()=>snapshot.value?.schemaBlocked??false);

// 关键字规范化的前端副本（SPEC-DM-014）：半/全角逗号分隔、trim、忽略空项、
// casefold 去重——与后端 domain/keywords.py 同规则；仅用于编辑中的即时反馈，
// 数量/长度上限的最终判定仍以保存时的 422 逐字段错误为准（ARCH-DM-005 §6.2）
function keywordsOf(value:string):string[]{
  const seen=new Set<string>();
  const keywords:string[]=[];
  for(const raw of value.split(/[,，]/)){
    const keyword=raw.trim();
    if(!keyword)continue;
    const folded=keyword.toLowerCase();
    if(seen.has(folded))continue;
    seen.add(folded);
    keywords.push(keyword);
  }
  return keywords;
}

function localError(item:SettingsItem):string|undefined{
  if(item.control==="int"&&item.key in edits.value){
    const value=edits.value[item.key];
    if(value===""||typeof value!=="number"||!Number.isInteger(value))return t("settings.validation.integerType");
    if(item.min!==undefined&&value<item.min||item.max!==undefined&&value>item.max)return t("settings.validation.integerRange",{min:item.min,max:item.max});
  }
  if(item.control==="path"&&typeof edits.value[item.key]==="string"&&/[<>"|?*]/.test(edits.value[item.key] as string))return t("settings.validation.pathIllegalChars");
  if(item.control==="text"&&typeof edits.value[item.key]==="string"){
    // 关键字即时校验（SPEC-DM-014）：仅提前反馈数量/长度超限，最终校验以后端 422 为准
    const keywords=keywordsOf(edits.value[item.key] as string);
    if(keywords.length>MAX_UNNUMBERED_KEYWORDS)return t("settings.validation.keywordCountLimit",{limit:MAX_UNNUMBERED_KEYWORDS,actual:keywords.length});
    const longest=keywords.reduce((max,keyword)=>Math.max(max,keyword.length),0);
    if(longest>MAX_UNNUMBERED_KEYWORD_CHARS)return t("settings.validation.keywordLengthLimit",{limit:MAX_UNNUMBERED_KEYWORD_CHARS,actual:longest});
  }
  return undefined;
}
// 结构化参数原样进入命名插值；list[str]（如 allowed_values）按后端消息风格以 / 连接，
// 不做区域化转换（ARCH-DM-005 §6.2）
function errorParams(params:StructuredParams|undefined):Record<string,string|number|boolean>{
  const out:Record<string,string|number|boolean>={};
  for(const [key,value] of Object.entries(params??{})){
    out[key]=Array.isArray(value)?value.join("/"):value;
  }
  return out;
}
function fieldErrorText(error:ApiFieldError):string{
  // 渲染顺序（ARCH-DM-005 §6.2）：已知 message_key → 迁移期兼容 message → 稳定 code
  if(error.messageKey!==undefined&&te(error.messageKey))return t(error.messageKey,errorParams(error.params));
  return error.message??error.code;
}
function fieldLabel(key:string):string{
  const item=items.value.find(entry=>entry.key===key);
  if(item===undefined)return key;
  return item.labelKey!==undefined?t(item.labelKey):item.key; // 兼容中文 label 回退已随阶段三删除
}
function rowError(item:SettingsItem):string|undefined{
  const error=fieldErrors.value[item.key];
  if(error!==undefined)return fieldErrorText(error); // 422 行内错误与摘要并存（SPEC-DM-013 §3.3）
  return localError(item);
}
const hasFieldErrors=computed(()=>Object.keys(fieldErrors.value).length>0);
const hasValidationError=computed(()=>items.value.some(item=>rowError(item)!==undefined));
const hasUnsaved=computed(()=>configHost.value?.dirty===true||items.value.some(item=>item.key in edits.value&&String(edits.value[item.key])!==String(item.value??""))||pendingUnset.value.length>0);
// 保存按钮双通道禁用（SPEC-DM-015 §5.2，PLAN-DM-034 Task 4）：
// · saveNativeDisabled——强阻断（校验失败/保存中/Schema 只读）：原生 disabled，不可聚焦；
// · saveAriaDisabled——clean（无未保存修改）：可聚焦的语义禁用（UiButton ariaDisabled），
//   空保存由 onSave 首行守卫承担；成功保存后焦点仍回到本按钮。
const saveNativeDisabled=computed(()=>saving.value||schemaBlocked.value||hasValidationError.value);
const saveAriaDisabled=computed(()=>!hasUnsaved.value);

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
  // PLAN-DM-021 Task 4：按注册表 file_kind 传固定种类；exe/dll 描述取自语言包
  //（common.shell.fileKinds.*）——白名单由壳侧按 kind 固定拼接，描述不能扩大之。
  // folder（无 file_kind 的 path 项）走独立 select_folder，不传描述。
  const kind=item.fileKind??"folder";
  const description=item.fileKind===undefined?"":t(`common.shell.fileKinds.${item.fileKind}`);
  const result=await selectSettingsPath(kind,description); // undefined=桥不可用（按钮已禁用）/null=取消/string=路径
  if(typeof result==="string")onUpdate(key,result);
}

// ---- 保存状态机（SC-07；PLAN-DM-021 Task 3 语言事务）----
async function onSave(){
  // 首行守卫（SPEC-DM-015 §5.2）：clean（无未保存修改）或强阻断期的任何激活途径
  // （force 点击/Enter/Space/程序化触发）都不产生空提交——不调 API、不递增修订、
  // 不显示新的成功 toast（与按钮 ariaDisabled/native disabled 双保险）
  if(!(hasUnsaved.value&&!saveNativeDisabled.value))return;
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
  // 双保险 no-op 守卫：UI 守卫已拦下 clean 激活，这里兜底防御性触发路径
  if(!Object.keys(set).length&&!pendingUnset.value.length)return;
  saving.value=true;conflictNotice.value="";saveFailedNotice.value="";saveFailedDetail.value="";
  let savedOk=false;
  try{
    // 组合式函数内完成语言切换事务：PUT 成功 → 以响应快照 ui_locale 切换一次；
    // 失败（422/409/网络/5xx）语言与本地输入均保持不变（I18N-05）
    const unset=[...pendingUnset.value];
    await save(set,unset);
    edits.value={};pendingUnset.value=[];fieldErrors.value={};
    // SC-13：编号规则/并发相关配置变更后，追加预览重算提示
    //（不编号图纸关键字参与编号派生，故与后缀两项、并行度同属重算键集）
    const previewKeys=["enable_add_number_suffix","number_suffix_type","unnumbered_subset_keywords","cad_max_parallel","cad_version"];
    const recalc=[...Object.keys(set),...unset].some(key=>previewKeys.includes(key));
    props.pushToast({type:"ok",title:t("settings.toast.savedTitle"),body:recalc?t("settings.toast.savedRecalcBody"):t("settings.toast.savedBody")});
    savedOk=true;
  }catch(error){
    if(error instanceof ApiError&&error.status===422){
      // 结构化逐字段错误（message_key+params）优先；迁移期字符串 fields 包装为兼容对象
      const structured=error.fieldErrors
        ??Object.fromEntries(Object.entries(error.fields??{}).map(([key,message])=>[key,{code:"SETTING_INVALID",message}]));
      if(Object.keys(structured).length>0){
        fieldErrors.value=structured;
        await nextTick();
        errorSummaryEl.value?.focus(); // §3.3：错误摘要取得焦点（tabindex=-1），条目链接字段
      }else{
        saveFailedNotice.value=t("settings.errors.saveFailed");
        saveFailedDetail.value=error.message;
      }
    }else if(error instanceof ApiError&&error.status===409){
      conflictNotice.value=t("settings.errors.conflict"); // 不自动切换语言（I18N-05）
      await load(); // 输入缓冲保留，仅刷新快照与修订号（load 不触发语言切换）
    }else{
      // 网络/5xx/未知错误：当前语言通用摘要，原始消息仅作诊断详情（tooltip）
      saveFailedNotice.value=t("settings.errors.saveFailed");
      saveFailedDetail.value=error instanceof Error?error.message:"";
    }
  }finally{
    saving.value=false;
  }
  if(savedOk){
    // 语言切换（含忙碌态结束）会整体重渲染：nextTick 后把焦点归还保存按钮
    //（与冻结 Demo 一致：保存成功后焦点回到保存按钮，SPEC-DM-015 §5.2 / I18N-06）
    await nextTick();
    saveButtonEl.value?.$el?.focus();
  }
}

function jumpToError(key:string){
  const input=dialogEl.value?.querySelector<HTMLElement>(`[data-key="${key}"]`);
  input?.scrollIntoView({block:"center"});
  input?.focus();
}

// ---- 诊断横幅（SC-12）----
// 已知机器码映射语言包键；未知条目（后端附带的中文说明）原样显示，不误译
const DIAG_KEYS:Record<string,string>={
  SETTINGS_FILE_MISSING:"settings.diagnostics.fileMissing",
  SETTINGS_FILE_CORRUPT:"settings.diagnostics.fileCorrupt",
};
const diagLines=computed(()=>{
  const lines:string[]=[];
  // schema 过新时后端 diagnostics 为空（resolver 降级分支），只读态由 schema_blocked 驱动
  if(schemaBlocked.value)lines.push(t("settings.diagnostics.schemaNewer",{code:"SETTINGS_SCHEMA_NEWER"}));
  for(const entry of snapshot.value?.diagnostics??[]){
    const key=DIAG_KEYS[entry];
    lines.push(key!==undefined?t(key,{code:entry}):entry);
  }
  return lines;
});

// ---- 扩展分区与配置子视图（SC-15/SC-16/SC-17）----
// 扩展列表与启停编排已下移到 ExtensionsSection（含失败就地行内呈现与开关焦点收敛）；
// 扩展配置子视图（SC-17）只在这里装配：当前扩展、子视图页脚与返回时的焦点归还。
// 原先必须让出 top layer，是因为宿主闸门（未提交输入三选一）当时是页面内联遮罩，
// 落在本对话框之下且被它 inert；该闸门与目录页三选一现已改为原生 <dialog showModal>，
// 会自行进入 top layer 叠在本对话框之上，本对话框无需再让位。

// 返回扩展列表：子视图（含未保存编辑）已就地处置，这里只切回列表并归还焦点
async function leaveConfig(){
  const extension=configExtension.value;
  configExtension.value=null;
  await nextTick();
  // SC-17：返回子视图后焦点归还触发它的卡片「配置」按钮（关闭对话框才归还齿轮）
  if(extension)extensionsSectionEl.value?.focusConfigOpener(extension.extension_id);
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
  <dialog ref="dialogEl" class="settings-dialog" aria-labelledby="settings-title" @cancel="onCancel" @click="onBackdropClick" @keydown="onDialogKeydown" @dragover.prevent.stop @drop.prevent.stop>
    <div class="dlg">
      <div class="dlg-head">
        <h2 id="settings-title">{{t("settings.title")}}</h2>
        <span v-if="snapshot" class="rev-pill">{{t("settings.revision",{revision:snapshot.configRevision})}}</span>
        <span class="spacer"></span>
        <button type="button" class="icon-btn" :aria-label="t('settings.close')" :disabled="saving" @click="tryClose"><UiIcon name="close" /></button>
      </div>
      <p v-if="loading&&!snapshot" class="loading" role="status">{{t("settings.loading")}}</p>
      <div v-else-if="loadFailed" class="dlg-body">
        <div class="panel load-failed">
          <p>{{t("settings.loadFailed")}}</p>
          <button type="button" @click="loadSettings">{{t("settings.retry")}}</button>
        </div>
      </div>
      <template v-else-if="snapshot">
        <div v-if="diagLines.length" class="diag" :class="{readonly:schemaBlocked}" role="alert">
          <p v-for="line in diagLines" :key="line">{{line}}</p>
        </div>
        <!-- 422 错误摘要：tabindex=-1 可聚焦，取得焦点后经条目链接跳转字段（SPEC-DM-013 §3.3） -->
        <div v-if="hasFieldErrors" ref="errorSummaryEl" class="error-summary" role="alert" tabindex="-1" data-testid="settings-error-summary">
          <p>{{t("settings.errors.summaryTitle")}}</p>
          <ul>
            <li v-for="(error,key) in fieldErrors" :key="key">
              <button type="button" class="es-link" @click="jumpToError(key)">{{fieldLabel(key)}}：{{fieldErrorText(error)}}</button>
            </li>
          </ul>
        </div>
        <div class="dlg-body">
          <nav class="sections" role="tablist" :aria-label="t('settings.sections.nav')">
            <button type="button" role="tab" :aria-selected="section==='general'" :disabled="configExtension!==null" @click="section='general'">{{t("settings.sections.general")}}</button>
            <button type="button" role="tab" :aria-selected="section==='extensions'" :disabled="configExtension!==null" @click="section='extensions'">{{t("settings.sections.extensions")}}</button>
            <button type="button" role="tab" :aria-selected="section==='about'" :disabled="configExtension!==null" @click="section='about'">{{t("settings.sections.about")}}</button>
          </nav>
          <div class="panel">
            <template v-if="section==='general'">
              <div v-for="group in groups" :key="group.key" class="group">
                <div class="group-title">{{groupTitle(group.key)}}</div>
                <SettingsFormRow
                  v-for="item in group.items" :key="item.key" :item="item"
                  :edit-value="edits[item.key]" :error="rowError(item)"
                  :pending-unset="pendingUnset.includes(item.key)"
                  :browse-disabled="browseDisabled" :disabled="schemaBlocked"
                  @update="onUpdate" @clear="onClear" @unset="onUnset" @browse="onBrowse"
                />
              </div>
            </template>
            <template v-else-if="section==='extensions'">
              <!-- SC-17：配置子视图与扩展列表是同一 <dialog> 内的平级视图，切换靠可见
                   「返回扩展列表」；列表取数、启停编排与失败就地呈现已归 ExtensionsSection。
                   列表用 v-show 保留在 DOM（仅隐藏）：返回时不得重挂载重取，
                   否则列表会被 loading 占位替代，焦点归还只能退回 <body>（§3.3）。 -->
              <ExtensionSettingsHost
                v-if="configExtension" ref="configHost" :extension="configExtension" @back="leaveConfig"
              />
              <ExtensionsSection
                v-show="configExtension===null" ref="extensionsSectionEl" :panel="extensionsPanel"
                @open-config="extension => configExtension = extension"
              />
            </template>
            <template v-else-if="section==='about'">
              <!-- 关于分区呈现与取数归 AboutSection（PLAN-DM-025 任务 6）；本对话框只装配分区 -->
              <AboutSection :push-toast="pushToast" />
            </template>
          </div>
        </div>
        <div class="dlg-foot">
          <span v-if="configExtension===null&&conflictNotice" class="foot-notice warn" role="alert">{{conflictNotice}}</span>
          <span v-else-if="configExtension===null&&saveFailedNotice" class="foot-notice error" role="alert" :title="saveFailedDetail||undefined">{{saveFailedNotice}}</span>
          <!-- 常规设置操作区状态：clean 固定复用 settings.saved（“已保存”，SPEC-DM-015 §5.2）；
               dirty/saving 由按钮文案与字段行既有状态表达，不新增键 -->
          <span v-if="configExtension===null&&!hasUnsaved" class="saved-pill" role="status" data-testid="settings-saved-pill">{{t("settings.saved")}}</span>
          <span v-if="configExtension&&configHost?.saved" class="saved-pill" role="status" data-testid="extension-settings-saved-pill">{{t("settings.extensionSettings.saved")}}</span>
          <span class="spacer"></span>
          <!-- SC-17 子视图页脚：本扩展独立保存（不与核心配置共享一次提交或修订号）。
               PLAN-DM-034 Task 5：保存按钮迁至 UiButton（与常规设置同一双通道口径）——
               clean 绑 saveAriaDisabled（可聚焦语义禁用），saving/只读/无快照/字段错误
               绑 saveNativeDisabled（原生禁用）；空保存与字段错误重放由宿主 save 入口守卫承担 -->
          <template v-if="configExtension">
            <button type="button" @click="configHost?.back()">{{t("settings.extensionSettings.back")}}</button>
            <UiButton class="primary" variant="primary" :disabled="configHost===null||configHost.saveNativeDisabled" :aria-disabled="configHost!==null&&configHost.saveAriaDisabled" @click="configHost?.save()">{{configHost?.saving?t("settings.extensionSettings.saving"):t("settings.extensionSettings.save")}}</UiButton>
          </template>
          <template v-else>
            <button type="button" :disabled="saving" @click="tryClose">{{t("settings.cancel")}}</button>
            <!-- PLAN-DM-034：常规设置主保存按钮迁至 UiButton（仅此一颗，其余裸按钮不动）；
                 强阻断走原生 disabled，clean 走可聚焦语义禁用（aria-disabled） -->
            <UiButton ref="saveButtonEl" class="primary" variant="primary" :disabled="saveNativeDisabled" :aria-disabled="saveAriaDisabled" @click="onSave">{{saving?t("settings.saving"):t("settings.save")}}</UiButton>
          </template>
        </div>
      </template>
    </div>
    <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  </dialog>
</template>
<style scoped>
.settings-dialog{padding:0;width:var(--settings-dialog-width);max-width:calc(100vw - 32px);height:min(620px,86vh);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);background:var(--color-bg-surface);color:var(--color-text-primary);box-shadow:var(--shadow-3)}
.settings-dialog::backdrop{background:rgba(16,24,40,.55)}
.dlg{display:flex;flex-direction:column;height:100%}
.dlg-head{display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border-subtle);flex-shrink:0}
.dlg-head h2{margin:0;font-size:var(--font-title)}
.rev-pill{font-size:var(--font-caption);padding:2px 10px;border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary)}
.spacer{flex:1}
.icon-btn{border:0;background:transparent;color:var(--color-text-secondary);cursor:pointer;min-width:var(--tap-target-min);min-height:var(--tap-target-min);border-radius:var(--radius-md)}
.icon-btn:hover:not(:disabled){background:var(--color-bg-muted)}
.loading{margin:var(--space-5);color:var(--color-text-secondary)}
.load-failed{display:flex;flex-direction:column;gap:var(--space-3);align-items:flex-start}
.load-failed button{padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);cursor:pointer}
.diag{border:1px solid var(--color-warning);background:var(--color-warning-bg);color:var(--color-warning);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);font-size:var(--font-caption);line-height:1.8;margin:var(--space-3) var(--space-4) 0;flex-shrink:0}
.diag p{margin:0}
.diag.readonly{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.error-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);font-size:var(--font-caption);line-height:1.8;margin:var(--space-3) var(--space-4) 0;flex-shrink:0}
.error-summary p{margin:0;font-weight:600}
.error-summary ul{margin:0;padding:0;list-style:none}
.es-link{border:0;background:transparent;color:var(--color-danger);cursor:pointer;padding:0;font-size:var(--font-caption);line-height:1.8;text-align:left;text-decoration:underline}
.es-link:hover{color:var(--color-danger);opacity:.8}
.dlg-body{display:flex;flex:1;min-height:0}
.sections{width:var(--settings-nav-width);flex-shrink:0;border-right:1px solid var(--color-border-subtle);padding:var(--space-2);display:flex;flex-direction:column;gap:var(--space-1)}
.sections button{border:0;background:transparent;text-align:left;color:var(--color-text-secondary);padding:9px var(--space-3);border-radius:var(--radius-md);cursor:pointer;font-size:var(--font-label)}
.sections button[aria-selected="true"]{background:var(--color-info-bg);color:var(--color-accent);font-weight:600}
.panel{flex:1;overflow:auto;padding:var(--space-3) var(--space-4)}
.group{margin-bottom:var(--space-2)}
.group-title{font-weight:600;font-size:var(--font-label);border-left:3px solid var(--color-accent);padding-left:var(--space-2);margin:var(--space-3) 0 var(--space-2)}
.dlg-foot{display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);flex-shrink:0}
.foot-notice{font-size:var(--font-caption);line-height:1.6}
.foot-notice.warn{color:var(--color-warning)}
.foot-notice.error{color:var(--color-danger)}
.saved-pill{font-size:var(--font-caption);color:var(--color-success)}
.dlg-foot button{padding:9px var(--space-4);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:var(--button-font-size)}
.dlg-foot button:disabled{cursor:not-allowed;opacity:.5}
.dlg-foot button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
</style>
