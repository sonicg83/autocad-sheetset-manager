<script setup lang="ts">
// 设置中心「关于」分区（PLAN-DM-025 任务 6：从 SettingsDialog.vue 抽出，使对话框回落到容量软上限内）。
// 职责：呈现应用名+版本、MIT 全文（面板内滚动）与主页/反馈外链（SC-11），并自持本分区的
// loading/失败态；取数走 fetchAbout() 的会话级 memo——反复进入本分区（组件反复挂载）不重放 GET。
// 迁移时不改 i18n 键、可访问名与 DOM 结构（class 名与拆分前逐字相同，样式一并搬来）。
// 外链经 ShellBridge 白名单在系统浏览器打开（浏览器开发态回退 window.open），打开结果交
// 宿主 useToast 呈现：本分区只上报反馈，不持有全局提示状态。
import {ref} from "vue";
import {useI18n} from "vue-i18n";
import {fetchAbout} from "../../api/settings";
import type {AboutInfo} from "../../api/settings";
import {getShellBridge,openExternalLink} from "../../api/shell";
import type {SettingsToast} from "./SettingsDialog.vue";
const logoLargeUrl=new URL("../../assets/brand/dst-manager-logo-512.png",import.meta.url).href;

const props=defineProps<{pushToast:(toast:SettingsToast)=>void}>();
const {t}=useI18n();

const about=ref<AboutInfo|null>(null);
const aboutFailed=ref(false);

async function loadAbout(){
  try{about.value=await fetchAbout()}
  catch{aboutFailed.value=true}
}
// 挂载即取数：memo 命中时不产生网络请求；失败后 memo 已清除，
// 因此"离开再回到关于分区"就是显式重试，不需要单独的失败重试按钮
void loadAbout();

async function openExternal(url:string){
  // SC-11：url 来自 GET /api/about 的后端登记值（api.py _HOMEPAGE 常量），前端不传任意字符串；
  // 壳侧 open_external 再按代码内白名单二次校验（github.com/sonicg83 前缀），拒绝结果不经 WebView 导航。
  if(getShellBridge()){
    const opened=await openExternalLink(url);
    if(opened===true){
      props.pushToast({type:"ok",title:t("settings.toast.linkTitle"),body:t("settings.toast.linkOpened")});
    }else if(opened===false){
      props.pushToast({type:"fail",title:t("settings.toast.linkTitle"),body:t("settings.toast.linkRejected")});
    }else{
      // 旧壳缺 open_external 方法：维持降级提示
      props.pushToast({type:"ok",title:t("settings.toast.linkTitle"),body:t("settings.toast.linkUnsupported")});
    }
    return;
  }
  // 浏览器开发态（无桥）：维持 window.open（e2e 依赖此路径断言 popup URL）
  window.open(url,"_blank","noopener");
}
</script>
<template>
  <div class="about-block">
    <h3>{{t("settings.about.app")}}</h3>
    <div class="about-app-summary">
      <img class="brand-logo-large" :src="logoLargeUrl" :alt="t('settings.about.logoAlt')">
      <p v-if="about">DST Manager <strong>v{{about.version}}</strong></p>
      <p v-else-if="aboutFailed" class="f-hint">{{t("settings.about.loadFailed")}}</p>
      <p v-else class="f-hint" role="status">{{t("settings.about.loading")}}</p>
    </div>
  </div>
  <div class="about-block">
    <h3>{{t("settings.about.licenseTitle")}}</h3>
    <div v-if="about" class="license">{{about.license.text}}</div>
    <div v-else-if="aboutFailed" class="f-hint">{{t("settings.about.loadFailed")}}</div>
  </div>
  <div class="about-block">
    <h3>{{t("settings.about.linksTitle")}}</h3>
    <p v-if="about" class="link-line">
      <button type="button" class="link-btn" @click="openExternal(about.homepage)">{{t("settings.about.homepage")}}</button>
      <button type="button" class="link-btn" @click="openExternal(about.feedbackUrl)">{{t("settings.about.feedback")}}</button>
    </p>
    <p v-else-if="!aboutFailed" class="f-hint" role="status">{{t("settings.about.loading")}}</p>
  </div>
</template>
<style scoped>
.about-block{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);margin-bottom:var(--space-3)}
.about-block h3{margin:0 0 var(--space-2);font-size:var(--font-label)}
.about-block p{margin:0}
.about-app-summary{display:flex;align-items:center;gap:var(--space-5);min-height:var(--brand-logo-size-about);padding:var(--space-2) 0}
.brand-logo-large{display:block;width:var(--brand-logo-size-about);height:var(--brand-logo-size-about);max-width:40%;object-fit:contain;flex:none}
.license{font-size:var(--font-caption);line-height:1.7;color:var(--color-text-secondary);white-space:pre-wrap;background:var(--color-bg-canvas);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);max-height:var(--settings-license-max-height);overflow:auto}
.link-line{display:flex;gap:var(--space-2)}
@media (max-width:640px){.about-app-summary{gap:var(--space-3)}.brand-logo-large{width:var(--brand-logo-size-about-narrow);height:var(--brand-logo-size-about-narrow)}}
</style>
