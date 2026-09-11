<script setup lang="ts">
// 设置中心单字段行（PLAN-DM-019 任务 10；PLAN-DM-021 Task 3 双语化）。
// 只负责展示与编辑事件上抛；编辑缓冲、校验与保存状态机在 SettingsDialog.vue。
// 文本一律经语言包渲染：item 的稳定显示键（labelKey/textKey/fileFilterKey），
// 迁移期兼容中文回退（I18N-17）已随阶段三（Task 10）删除。DOM 约定（e2e 依赖）：
// 行容器 data-field；可编辑控件 data-key；int 控件直接位于 .f-main 内，
// 保证 `input[data-key]` 的父节点包含来源徽章文本。
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import type {SettingsEnumOption, SettingsItem, SettingsValue} from "../../api/settings";
import BooleanSwitch from "./BooleanSwitch.vue";

const props=defineProps<{
  item:SettingsItem;
  editValue:SettingsValue|undefined; // undefined = 未编辑，显示快照值
  error:string|undefined; // 行内错误（即时校验或保存 422 逐字段回显），空串不显示
  pendingUnset:boolean; // 已标记"恢复继承"，随下次保存提交
  browseDisabled:boolean; // 桥不可用（浏览器开发态/旧壳）→ 禁用"浏览…"
  disabled:boolean; // schema 过新只读降级：全部输入禁用
}>();
const emit=defineEmits<{update:[key:string,value:SettingsValue];clear:[key:string];unset:[key:string];browse:[key:string]}>();

const {t,locale}=useI18n();

// 字段标签：稳定键经语言包渲染（兼容中文回退已随阶段三删除）
const label=computed(()=>props.item.labelKey!==undefined?t(props.item.labelKey):props.item.key);

// "跟随系统"选项的当前生效语言名：语言名保留自称形式（SPEC-DM-013 §5.1），
// 与界面语言无关地显示 zh-CN → 简体中文 / en-US → English
const currentLocaleName=computed(()=>locale.value==="zh-CN"?t("settings.locale.zhCN"):t("settings.locale.enUS"));

// 枚举选项文本：textKey 走语言包；"跟随系统"为复合标签（SPEC-DM-013 §3.2），
// 当前解析结果经命名参数注入（I18N-08），不在调用点拼接可翻译片段
function optionText(option:SettingsEnumOption):string{
  if(option.textKey==="settings.locale.system")return t("settings.locale.systemCurrent",{current:currentLocaleName.value});
  return t(option.textKey);
}

// 编辑值与快照值不同即"未保存修改"（amber 边框依据）；null 与 null 视为相同
const dirty=computed(()=>props.editValue!==undefined&&String(props.editValue)!==String(props.item.value??""));
const hasError=computed(()=>props.error!==undefined&&props.error!=="");
// 生效显示值：编辑缓冲优先；清除（null）与未配置（null/null）显示为空
const shown=computed(()=>{
  if(props.editValue!==undefined)return props.editValue;
  return props.item.value??"";
});
const pathEmpty=computed(()=>props.item.control==="path"&&shown.value==="");

const badgeText=computed(()=>props.item.source==="file"?t("settings.row.sourceFile"):props.item.source==="env"?t("settings.row.sourceEnv"):t("settings.row.sourceDefault"));
const badgeClass=computed(()=>props.item.source==="file"?"badge-file":props.item.source==="env"?"badge-env":"badge-default");

function commit(value:SettingsValue){emit("update",props.item.key,value)}

// 控件归一化：int/enum 以 number 入缓冲，path/bool 原样；int 空串保留（触发"必须为整数"行内错误）。
// ui_locale 为字符串枚举（system/zh-CN/en-US）：非数字原样入缓冲，数字枚举照旧转 number
function onIntInput(event:Event){const raw=(event.target as HTMLInputElement).value;commit(raw===""?"":Number(raw))}
// 滑动开关直接给出目标值（不再是 checkbox 的 change 事件）
function onBoolChange(value:boolean){commit(value)}
function onEnumInput(event:Event){
  const raw=(event.target as HTMLInputElement).value;
  const num=Number(raw);
  commit(raw!==""&&!Number.isNaN(num)?num:raw);
}
</script>
<template>
  <div class="field" :class="{dirty,error:hasError}" :data-field="item.key">
    <label class="f-label" :for="`settings-input-${item.key}`">{{label}}</label>
    <div class="f-main">
      <template v-if="item.control==='path'">
        <div class="f-line">
          <input :id="`settings-input-${item.key}`" type="text" :data-key="item.key" :value="shown" :placeholder="item.nullable?t('settings.row.placeholderNotSet'):''" :disabled="disabled" :aria-invalid="hasError?'true':'false'" @input="commit(($event.target as HTMLInputElement).value)">
          <button type="button" class="browse-btn" :disabled="disabled||browseDisabled" :title="browseDisabled?t('settings.row.browseUnavailable'):undefined" @click="emit('browse',item.key)">{{t("settings.row.browse")}}</button>
          <button v-if="item.nullable" type="button" class="link-btn" :disabled="disabled||pathEmpty" @click="emit('clear',item.key)">{{t("settings.row.clear")}}</button>
        </div>
      </template>
      <input v-else-if="item.control==='int'" :id="`settings-input-${item.key}`" type="number" :data-key="item.key" :min="item.min" :max="item.max" :value="shown" :disabled="disabled" :aria-invalid="hasError?'true':'false'" @input="onIntInput">
      <span v-else-if="item.control==='bool'" class="bool-line">
        <BooleanSwitch
          :checked="Boolean(shown)" :disabled="disabled" :label="label"
          :data-key="item.key" :input-id="`settings-input-${item.key}`"
          @change="onBoolChange"
        />
        <span class="f-hint">{{shown?t("settings.row.on"):t("settings.row.off")}}</span>
      </span>
      <span v-else-if="item.control==='enum'" class="radio-line" role="radiogroup" :aria-label="label">
        <label v-for="option in item.options" :key="String(option.value)">
          <input type="radio" :name="`settings-radio-${item.key}`" :data-key="item.key" :value="option.value" :checked="shown===option.value" :disabled="disabled" @change="onEnumInput">{{optionText(option)}}
        </label>
      </span>

      <div class="f-foot">
        <span class="badge" :class="badgeClass">{{badgeText}}</span>
        <button v-if="item.hasFileOverride||pendingUnset" type="button" class="link-btn" :disabled="disabled" @click="emit('unset',item.key)">{{pendingUnset?t("settings.row.undoRestoreInherited"):t("settings.row.restoreInherited")}}</button>
        <span v-if="item.control==='path'&&item.fileFilterKey!==undefined" class="f-hint">{{t(item.fileFilterKey)}}</span>
        <span v-else-if="item.control==='int'&&item.min!==undefined&&item.max!==undefined" class="f-hint">{{item.min}}–{{item.max}}</span>
      </div>
      <p v-if="hasError" class="f-error" role="alert">{{error}}</p>
    </div>
  </div>
</template>
<style scoped>
.field{display:grid;grid-template-columns:150px 1fr;gap:var(--space-2) var(--space-3);padding:var(--space-2) var(--space-3);border:1px solid transparent;border-radius:var(--radius-md);align-items:start}
.field:focus-within{background:var(--color-bg-canvas)}
.field.dirty{border-color:var(--color-warning);background:var(--color-warning-bg)}
.field.error{border-color:var(--color-danger);background:var(--color-danger-bg)}
.f-label{font-size:13px;font-weight:500;padding-top:var(--space-2);color:var(--color-text-primary)}
.f-main{display:flex;flex-direction:column;gap:var(--space-1);min-width:0}
.f-line{display:flex;gap:var(--space-2);align-items:center}
.f-line input{flex:1;min-width:0}
input[type="text"],input[type="number"]{height:34px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);padding:0 var(--space-2)}
input:disabled{opacity:.5;cursor:not-allowed}
.browse-btn{height:34px;padding:0 var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:13px;white-space:nowrap}
.browse-btn:hover:not(:disabled){background:var(--color-bg-muted)}
.browse-btn:disabled{cursor:not-allowed;opacity:.5}
.link-btn{border:0;background:transparent;color:var(--color-accent);cursor:pointer;padding:var(--space-1) var(--space-1);font-size:12px;min-height:28px}
.link-btn:disabled{cursor:not-allowed;opacity:.5}
.f-foot{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap;min-height:24px}
.badge{display:inline-block;font-size:12px;padding:2px 9px;border-radius:var(--radius-full);white-space:nowrap}
.badge-default{color:var(--color-text-secondary);background:var(--color-bg-muted)}
.badge-env{color:var(--color-warning);background:var(--color-warning-bg)}
.badge-file{color:var(--color-accent);background:var(--color-info-bg)}
.f-hint{font-size:12px;color:var(--color-text-secondary)}
.f-error{margin:0;font-size:12px;color:var(--color-danger);line-height:1.6}
.bool-line{display:inline-flex;align-items:center;gap:var(--space-2);padding-top:var(--space-2)}
.radio-line{display:flex;gap:var(--space-4);padding-top:var(--space-2);flex-wrap:wrap}
.radio-line label{display:flex;gap:var(--space-1);align-items:center;font-size:13px;color:var(--color-text-primary)}
@media (max-width:900px){.field{grid-template-columns:1fr}}
</style>
