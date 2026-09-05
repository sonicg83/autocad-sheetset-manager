<!-- 属性 CSV 导入导出面板（PLAN-DM-016 任务 5，SPEC-DM-006 §6.2/§10.3、SPEC-DM-010 §4）。
     按需渐进流程：默认不显示文件选择；「导入 / 导出」菜单收纳下载模板/导出/导入入口（链接保持原 URL）；
     选择文件后才出现预览操作，确认导入为 Danger 分级正式写入（禁用态见 useCsvImport 门禁）。
     组件只展示与派发动作：文件读取/预览/正式确认仍由 App 的 useCsvImport 完成（强确认、代次失效、job 监控不在组件内）。
     导入区用 v-show、预览区按存在性渲染：关闭仅隐藏 UI，不取消在途任务；预览失效由 App 依代次/基准/定义草稿判定。
     样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, ref} from "vue";
import type {CsvPreview} from "../../api/contracts";

const props = defineProps<{
  workspaceId: string;
  hasCsv: boolean;
  csvPreview: CsvPreview | null;
  csvExecutable: boolean;
  writesDisabled: boolean;
  // 面板折叠为工作区会话态（默认展开）：折叠后标题栏仍显示 CSV 状态
  collapsed: boolean;
  // 导入区开关为工作区会话态（PLAN-DM-016 任务 6）：切 workspace 重置为关闭，切主标签保留
  csvOpen: boolean;
}>();
const emit = defineEmits<{
  readCsv: [event: Event];
  previewCsv: [];
  importCsv: [];
  "update:collapsed": [value: boolean];
  "update:csvOpen": [value: boolean];
}>();

// —— 菜单（面板内局部）；导入区开关为会话态，经 emit 上报 ——
const menuOpen = ref(false);
function toggleMenu() { menuOpen.value = !menuOpen.value; }
function toggleCsv() {
  emit("update:csvOpen", !props.csvOpen);
  menuOpen.value = false; // 打开/关闭导入区后收起菜单，保持单一焦点
}
// 标题栏 CSV 状态摘要：折叠后仍可见（措辞与流程区提示区分，避免同文案歧义）
const csvStatus = computed(() => {
  if (!props.hasCsv) return "CSV：未选择文件";
  if (!props.csvPreview) return "CSV：已选择文件，未预览";
  return props.csvExecutable ? "CSV：预览可确认" : "CSV：预览存在诊断，无法确认";
});
</script>
<template>
  <section class="csv-panel" aria-label="属性导入导出">
    <header class="panel-head">
      <button
        type="button"
        class="head-toggle"
        :aria-expanded="!collapsed"
        aria-controls="csv-panel-body"
        :aria-label="collapsed ? '展开属性导入导出' : '收起属性导入导出'"
        @click="emit('update:collapsed', !collapsed)"
      >
        <span class="chevron" aria-hidden="true">{{ collapsed ? "▸" : "▾" }}</span>
        <span class="head-title">属性导入导出</span>
      </button>
      <span class="head-status" role="status">{{ csvStatus }}</span>
      <!-- 面板折叠时菜单目标（io-menu）在隐藏的面板体内：禁用避免死键；展开面板后即可用 -->
      <button
        type="button"
        class="menu-toggle"
        :disabled="collapsed"
        :aria-expanded="menuOpen"
        aria-controls="csv-io-menu"
        @click="toggleMenu"
      >导入 / 导出</button>
    </header>
    <div v-if="!collapsed" id="csv-panel-body" class="panel-body">
      <div v-show="menuOpen" id="csv-io-menu" class="io-menu">
        <a href="/api/custom-properties/template" download @click="menuOpen = false">下载 CSV 模板</a>
        <a :href="`/api/workspaces/${workspaceId}/custom-properties/export`" download @click="menuOpen = false">导出当前属性</a>
        <button v-if="!csvOpen" type="button" :aria-expanded="csvOpen" @click="toggleCsv">导入 CSV</button>
      </div>
      <div v-show="csvOpen" class="csv-flow">
        <label>属性 CSV 文件<input type="file" accept=".csv,text/csv" @change="emit('readCsv', $event)"></label>
        <!-- 关闭入口在流程区内：菜单收起后仍可关闭导入区；关闭仅隐藏 UI，不取消在途任务 -->
        <!-- 预览操作在选择文件后才可用（未选择时隐藏）；确认导入为 Danger 分级，无效数据禁用 -->
        <button v-show="hasCsv" type="button" @click="emit('previewCsv')">预览 CSV 导入</button>
        <button
          type="button"
          class="danger"
          :disabled="writesDisabled || !csvExecutable"
          @click="emit('importCsv')"
        >确认导入</button>
        <button type="button" :aria-expanded="csvOpen" @click="toggleCsv">关闭导入</button>
        <p v-if="!hasCsv" class="csv-hint" role="status">未选择 CSV 文件：请选择 UTF-8 编码的 .csv 文件，选择后可预览合并结果</p>
        <p v-else-if="csvPreview && csvPreview.changes.length === 0" class="csv-hint" role="status">本次导入不含属性定义变更</p>
        <p v-else-if="csvPreview && !csvExecutable" class="csv-hint error" role="alert">预览结果不可执行：请按诊断修正 CSV 后重新预览</p>
      </div>
      <!-- 预览数据保存在 useCsvImport（App 域）：关闭导入区不销毁上下文，重开后仍显示最近一次预览 -->
      <div v-if="csvOpen && csvPreview" class="csv-preview">
        <h3>CSV 合并预览</h3>
        <ul class="change-list"><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`" class="csv-change">第 {{ change.line }} 行 · {{ change.action }} · {{ change.type }} · {{ change.name }}</li></ul>
        <ul v-if="csvPreview.diagnostics.length > 0" class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">第 {{ item.line }} 行 · </span><b>{{ item.code }}</b>：{{ item.message }}</li></ul>
      </div>
    </div>
  </section>
</template>
<style scoped>
.csv-panel{background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:60px;padding:var(--space-2) var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
/* 折叠开关沿用属性页受控按钮基线（≥36px、边框与不透明背景），仅排布为标题样式 */
.head-toggle{display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);min-height:36px}
/* 标题文字用 span（button 内不允许 h2）：面板名由 section aria-label 与按钮 aria-label 提供 */
.head-title{margin:0;font-size:16px;font-weight:600}
.chevron{color:var(--color-text-secondary);font-size:12px}
.head-status{color:var(--color-text-muted);font-size:12px}
.menu-toggle{margin-left:auto;display:inline-flex;align-items:center;min-height:36px;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary)}
.panel-body{padding:var(--space-4)}
.io-menu{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;padding:0 0 var(--space-3);border-bottom:1px solid var(--color-border-subtle);margin-bottom:var(--space-3)}
.io-menu a{display:inline-flex;align-items:center;min-height:36px;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary)}
/* 确认导入为正式写入：沿用确认模态的危险分级（红色文字 + 危险描边），不新造色值 */
.csv-flow{display:flex;align-items:end;gap:var(--space-3);flex-wrap:wrap;margin:0;padding:0}
.csv-flow label{display:grid;gap:var(--space-1);color:var(--color-text-secondary);font-size:13px}
.csv-flow input{min-width:0;padding:8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm)}
.csv-flow button.danger{color:var(--color-danger);border:1px solid var(--color-danger);background:var(--color-bg-surface)}
.csv-hint{margin:0;color:var(--color-text-muted);font-size:12px}
.csv-hint.error{color:var(--color-danger)}
.csv-preview{margin:var(--space-3) 0 0;background:var(--color-bg-muted);padding:var(--space-3);border-radius:var(--radius-md)}
.csv-preview h3{margin:0 0 var(--space-2);font-size:14px}
.csv-preview ul{margin:var(--space-2) 0;padding-left:20px}
.diagnostics .error{color:var(--color-danger)}
.diagnostics .warning{color:var(--color-warning)}
</style>
