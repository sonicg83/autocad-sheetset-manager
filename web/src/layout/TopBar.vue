<script setup lang="ts">
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import {useApplicationPreferences} from "../composables/useApplicationPreferences";
import UiIcon from "../components/ui/UiIcon.vue";
import UiIconButton from "../components/ui/UiIconButton.vue";
// 顶栏主题按钮只切换本次运行；持久主题只由配置中心保存。
const {theme,toggleTheme}=useApplicationPreferences();
const {t}=useI18n();
const props=defineProps<{sheetSetName:string;dstPath:string;dstStatus:string;closeDisabled?:boolean;hasShell?:boolean;workspaceId?:string}>();
defineEmits<{close:[];"open-folder":[];"open-settings":[]}>();
function statusClass(status:string){return status==="VALID"?"valid":status==="REPAIRED"?"warn":"invalid"}
// 状态胶囊三态映射（稳定枚举 → 语义键，I18N-07；枚举值不进用户文案）
const STATUS_KEYS:Record<string,string>={VALID:"shell.topbar.statusValid",REPAIRED:"shell.topbar.statusRepaired",INVALID_UNRECOVERABLE:"shell.topbar.statusUnrecoverable"};
function statusLabel(status:string){return t(STATUS_KEYS[status]??"shell.topbar.statusNeedsRepair")}
// 打开图纸集所在文件夹：无桌面壳时禁用并解释（桥晚到由 App.vue 的 shellReady 响应式更新）
const folderDisabled=computed(()=>!props.hasShell);
const folderTitle=computed(()=>folderDisabled.value?t("shell.topbar.folderUnavailable"):t("shell.topbar.folderTooltip"));
</script>
<template>
  <header class="topbar" role="banner">
    <span class="brand">DST Manager</span>
    <span class="brand-sub">{{ $t("shell.topbar.tagline") }}</span>
    <span v-if="sheetSetName" class="workspace-name" :title="dstPath || sheetSetName">{{sheetSetName}}</span>
    <button v-if="workspaceId" type="button" class="folder-btn" :disabled="folderDisabled" :title="folderTitle" :aria-label="$t('shell.topbar.openFolderAria')" @click="$emit('open-folder')">{{ $t("shell.topbar.openFolder") }}</button>
    <span class="spacer"></span>
    <span v-if="dstStatus" class="pill" :class="statusClass(dstStatus)"><span class="dot" aria-hidden="true"></span>DST {{statusLabel(dstStatus)}}</span>
    <button v-if="workspaceId" type="button" class="close-btn" :disabled="closeDisabled" @click="$emit('close')" :aria-label="$t('shell.topbar.closeAria')">{{ $t("shell.topbar.close") }}</button>
    <UiIconButton class="theme-btn" icon="theme" :label="$t('shell.topbar.themeToggle')" :title="theme==='dark'?$t('shell.topbar.themeToLight'):$t('shell.topbar.themeToDark')" @click="toggleTheme" />
    <!-- 设置中心入口（SPEC-DM-011 SC-01）：常驻，未加载工作区同样可用；焦点归还由对话框负责 -->
    <button type="button" class="settings-btn" :aria-label="$t('shell.topbar.settings')" aria-haspopup="dialog" :title="$t('shell.topbar.settings')" @click="$emit('open-settings')"><UiIcon name="settings" />{{ $t("shell.topbar.settings") }}</button>
  </header>
</template>
<style scoped>
.topbar{display:flex;align-items:center;gap:var(--space-4);padding:0 var(--space-4);height:var(--shell-bar-height);min-height:var(--shell-bar-height);background:var(--color-bg-surface);border-bottom:1px solid var(--color-border-subtle);flex-shrink:0}
.brand{font-weight:600;font-size:var(--button-font-size);color:var(--color-text-primary);white-space:nowrap}
.brand-sub{color:var(--color-text-muted);font-size:var(--font-caption);white-space:nowrap}
.workspace-name{color:var(--color-text-primary);font-size:var(--font-label);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:clamp(140px,24vw,300px)}
.spacer{flex:1}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:var(--radius-full);font-size:var(--font-caption);font-weight:500;white-space:nowrap}
.pill .dot{width:var(--status-dot-size);height:var(--status-dot-size);border-radius:var(--radius-full);background:currentColor}
.pill.valid{background:var(--color-success-bg);color:var(--color-success)}
.pill.warn{background:var(--color-warning-bg);color:var(--color-warning)}
.pill.invalid{background:var(--color-danger-bg);color:var(--color-danger)}
.close-btn{height:var(--button-height);padding:0 var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:var(--font-label);white-space:nowrap}
.close-btn:hover:not(:disabled){background:var(--color-bg-muted)}
.close-btn:disabled{cursor:not-allowed;opacity:.5}
.folder-btn{height:var(--button-height);min-width:var(--folder-action-min-width);padding:0 var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:transparent;color:var(--color-text-secondary);cursor:pointer;font-family:inherit;font-size:var(--font-caption);white-space:nowrap;flex:none}
.folder-btn:hover:not(:disabled){background:var(--color-bg-muted);color:var(--color-text-primary)}
.folder-btn:disabled{cursor:not-allowed;opacity:.5}
/* 主题按钮使用 UiIconButton 原语：尺寸、悬停与禁用态由原语负责，这里只锁弹性收缩 */
.theme-btn{flex:none}
.settings-btn{height:var(--button-height);padding:0 var(--space-3);flex:none;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-family:inherit;font-size:var(--font-label);white-space:nowrap}
.settings-btn:hover{background:var(--color-bg-muted)}
@media (max-width:1120px){.topbar{gap:var(--space-2)}.brand-sub{display:none}.workspace-name{max-width:var(--workspace-name-max-width)}}
@media (max-width:900px){.pill{display:none}.workspace-name{max-width:var(--workspace-name-max-width-narrow)}.folder-btn{padding:0 var(--space-2)}}
</style>
