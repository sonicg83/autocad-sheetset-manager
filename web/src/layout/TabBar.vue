<script setup lang="ts">
// 标签栏：role="tablist" + roving tabindex（SPEC-DM-006 §7.2 / PLAN-DM-020 Task 10）。
// 标签列表由 App 以 TabDescriptor[] 提供：核心三标签顺序固定在前，扩展页面追加在后；
// label 为已本地化文本（App 经宿主 i18n 渲染），id 为稳定标签标识与焦点归还目标。
// 键盘模型由 App.vue 经 useShellTabs 的 onKeydown 回退挂载到根元素
import type {TabDescriptor} from "../composables/useShellTabs";
defineProps<{descriptors:TabDescriptor[];active:string}>();
const emit=defineEmits<{select:[id:string]}>();
function clickTab(tab:TabDescriptor){if(tab.disabled!==true)emit("select",tab.id)}
</script>
<template>
  <nav class="tabbar" role="tablist" :aria-label="$t('shell.tabs.region')">
    <button v-for="tab in descriptors" :key="tab.id" :id="`tab-${tab.id}`" type="button" class="tab" role="tab"
      :aria-selected="active===tab.id" :aria-controls="`panel-${tab.id}`" :tabindex="active===tab.id?0:-1"
      :disabled="tab.disabled===true" @click="clickTab(tab)">
      <span v-if="tab.number" class="num">{{tab.number}}</span>{{ tab.label }}
    </button>
    <span class="tab-ghost" :title="$t('shell.tabs.ghostTitle')">{{ $t("shell.tabs.ghost") }}</span>
  </nav>
</template>
<style scoped>
.tabbar{display:flex;align-items:stretch;gap:2px;padding:0 var(--space-4);background:var(--color-bg-surface);border-bottom:1px solid var(--color-border-subtle);overflow-x:auto;flex-shrink:0}
.tab{display:flex;align-items:center;gap:6px;padding:10px var(--space-4);color:var(--color-text-secondary);border:none;background:none;border-bottom:2px solid transparent;font-weight:500;white-space:nowrap;cursor:pointer;font-family:inherit;font-size:14px}
.tab:hover:not(:disabled){color:var(--color-text-primary)}
.tab[aria-selected="true"]{color:var(--color-accent);border-bottom-color:var(--color-accent)}
.tab:disabled{cursor:not-allowed;opacity:.5}
.tab .num{font-size:11px;background:var(--color-bg-muted);border-radius:var(--radius-full);width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;color:var(--color-text-muted)}
.tab[aria-selected="true"] .num{background:var(--color-accent);color:var(--color-on-accent)}
.tab-ghost{align-self:center;margin-left:auto;padding:4px 12px;color:var(--color-text-muted);font-size:12px;border:1px dashed var(--color-border-strong);border-radius:var(--radius-full);cursor:default;white-space:nowrap}
</style>
