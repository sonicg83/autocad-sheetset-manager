<script setup lang="ts">
// 固定标签栏：role="tablist" + roving tabindex（SPEC-DM-006 §7.2）；键盘模型由 App.vue 经 useShellTabs 的 onKeydown 回退挂载到根元素
const props=defineProps<{active:string;revisionsDisabled?:boolean}>();
const emit=defineEmits<{select:[id:string]}>();
const TABS=[
  {id:"sheets",label:"图纸",num:"①"},
  {id:"properties",label:"属性",num:"②"},
  {id:"revisions",label:"修订历史",num:"③"},
] as const;
function isDisabled(id:string){return id==="revisions"&&props.revisionsDisabled===true}
function clickTab(id:string){if(!isDisabled(id))emit("select",id)}
</script>
<template>
  <nav class="tabbar" role="tablist" aria-label="功能分区">
    <button v-for="tab in TABS" :key="tab.id" :id="`tab-${tab.id}`" type="button" class="tab" role="tab"
      :aria-selected="active===tab.id" :aria-controls="`panel-${tab.id}`" :tabindex="active===tab.id?0:-1"
      :disabled="isDisabled(tab.id)" @click="clickTab(tab.id)">
      <span class="num">{{tab.num}}</span>{{tab.label}}
    </button>
    <span class="tab-ghost" title="预留扩展位：设置 / 打印 / 生成图纸目录等未来功能">＋ 预留扩展</span>
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
