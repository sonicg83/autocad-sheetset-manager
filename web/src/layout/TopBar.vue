<script setup lang="ts">
import {computed} from "vue";
import {useTheme} from "../composables/useTheme";
// 主题按钮迁入顶栏：useTheme 为模块级单例，TopBar 与 App.vue 共享同一主题状态
const {theme,toggleTheme}=useTheme();
const props=defineProps<{sheetSetName:string;dstPath:string;dstStatus:string;cadVersion:string;closeDisabled?:boolean;hasShell?:boolean;workspaceId?:string}>();
defineEmits<{"update:cadVersion":[value:string];close:[];"open-folder":[]}>();
function statusClass(status:string){return status==="VALID"?"valid":status==="REPAIRED"?"warn":"invalid"}
// 状态胶囊中文三态映射（枚举不进用户文案，与 RepairStatusPanel/App.vue dock 文案一致风格）
function statusLabel(status:string){
  if(status==="VALID")return "正常";
  if(status==="REPAIRED")return "已修复";
  if(status==="INVALID_UNRECOVERABLE")return "不可恢复";
  return "需修复";
}
// 打开图纸集所在文件夹：无桌面壳时禁用并解释（桥晚到由 App.vue 的 shellReady 响应式更新）
const folderDisabled=computed(()=>!props.hasShell);
const folderTitle=computed(()=>folderDisabled.value?"桌面壳未就绪，无法打开图纸集所在文件夹":"打开图纸集所在文件夹");
</script>
<template>
  <header class="topbar" role="banner">
    <span class="brand">DST Manager</span>
    <span class="brand-sub">v0.3 · 受控日常编辑与可恢复发布</span>
    <span v-if="sheetSetName" class="workspace-name" :title="dstPath || sheetSetName">{{sheetSetName}}</span>
    <button v-if="workspaceId" type="button" class="folder-btn" :disabled="folderDisabled" :title="folderTitle" aria-label="打开图纸集所在文件夹" @click="$emit('open-folder')">打开所在文件夹</button>
    <span class="spacer"></span>
    <span v-if="dstStatus" class="pill" :class="statusClass(dstStatus)"><span class="dot" aria-hidden="true"></span>DST {{statusLabel(dstStatus)}}</span>
    <label class="cad-version">AutoCAD 版本<select :value="cadVersion" @change="$emit('update:cadVersion',($event.target as HTMLSelectElement).value)"><option value="2016">2016</option><option value="2020">2020</option></select></label>
    <button v-if="workspaceId" type="button" class="close-btn" :disabled="closeDisabled" @click="$emit('close')" aria-label="关闭工作区">关闭</button>
    <button type="button" class="iconbtn" aria-label="切换主题" :title="theme==='dark'?'切换为浅色':'切换为深色'" @click="toggleTheme">◐</button>
  </header>
</template>
<style scoped>
.topbar{display:flex;align-items:center;gap:var(--space-4);padding:0 var(--space-4);height:52px;min-height:52px;background:var(--color-bg-surface);border-bottom:1px solid var(--color-border-subtle);flex-shrink:0}
.brand{font-weight:600;font-size:15px;color:var(--color-text-primary);white-space:nowrap}
.brand-sub{color:var(--color-text-muted);font-size:12px;white-space:nowrap}
.workspace-name{color:var(--color-text-primary);font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:clamp(140px,24vw,300px)}
.spacer{flex:1}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:var(--radius-full);font-size:12px;font-weight:500;white-space:nowrap}
.pill .dot{width:7px;height:7px;border-radius:var(--radius-full);background:currentColor}
.pill.valid{background:var(--color-success-bg);color:var(--color-success)}
.pill.warn{background:var(--color-warning-bg);color:var(--color-warning)}
.pill.invalid{background:var(--color-danger-bg);color:var(--color-danger)}
.cad-version{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--color-text-secondary);white-space:nowrap}
.cad-version select{height:30px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);padding:0 var(--space-2);font-family:inherit}
.close-btn{height:32px;padding:0 var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:13px;white-space:nowrap}
.close-btn:hover:not(:disabled){background:var(--color-bg-muted)}
.close-btn:disabled{cursor:not-allowed;opacity:.5}
.folder-btn{height:32px;min-width:112px;padding:0 var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:transparent;color:var(--color-text-secondary);cursor:pointer;font-family:inherit;font-size:12px;white-space:nowrap;flex:none}
.folder-btn:hover:not(:disabled){background:var(--color-bg-muted);color:var(--color-text-primary)}
.folder-btn:disabled{cursor:not-allowed;opacity:.5}
.iconbtn{width:32px;height:32px;padding:0;flex:0 0 32px;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:var(--radius-md);background:transparent;color:var(--color-text-secondary);cursor:pointer;font-size:15px}
.iconbtn:hover:not(:disabled){background:var(--color-bg-muted)}
.iconbtn:disabled{cursor:not-allowed;opacity:.5}
@media (max-width:1120px){.topbar{gap:var(--space-2)}.brand-sub{display:none}.workspace-name{max-width:180px}}
@media (max-width:900px){.pill{display:none}.workspace-name{max-width:130px}.folder-btn{padding:0 var(--space-2)}}
</style>
