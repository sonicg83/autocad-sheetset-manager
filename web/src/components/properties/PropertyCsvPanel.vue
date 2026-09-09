<!-- 属性 CSV 导入导出面板（PLAN-DM-016 任务 5，SPEC-DM-006 §6.2/§10.3、SPEC-DM-010 §4）。
     按需渐进流程：面板展开后直接常驻下载模板/导出/导入三个操作（2026-09-06 用户裁决取消二级菜单）；
     选择文件后才出现预览操作，确认导入为 Danger 分级正式写入（禁用态见 useCsvImport 门禁）。
     组件只展示与派发动作：文件读取/预览/正式确认仍由 App 的 useCsvImport 完成（强确认、代次失效、job 监控不在组件内）。
     关闭导入区经 closeCsv 交 App 处理：有未导入数据（已选文件/预览）先确认，确认后清空缓存并收起（2026-09-06 用户裁决）；
     在途任务不受关闭影响；预览失效仍由 App 依代次/基准/定义草稿判定。样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
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
  closeCsv: [];
  "update:collapsed": [value: boolean];
  "update:csvOpen": [value: boolean];
}>();

// 导入区开关为会话态，经 emit 上报
function toggleCsv() {
  emit("update:csvOpen", !props.csvOpen);
}
// 关闭确认清空后 hasCsv 翻转 false：同步重置原生 file input，避免残留文件名显示
const fileInput = ref<HTMLInputElement|null>(null);
watch(() => props.hasCsv, (has) => {
  if (!has && fileInput.value) fileInput.value.value = "";
});
// 标题栏 CSV 状态摘要：折叠后仍可见（措辞与流程区提示区分，避免同文案歧义）
const {t} = useI18n();
const csvStatus = computed(() => {
  if (!props.hasCsv) return t("properties.csv.statusNoFile");
  if (!props.csvPreview) return t("properties.csv.statusSelectedNoPreview");
  return props.csvExecutable ? t("properties.csv.statusExecutable") : t("properties.csv.statusNotExecutable");
});
</script>
<template>
  <section class="csv-panel" :aria-label="$t('properties.csv.panelAria')">
    <header class="panel-head">
      <button
        type="button"
        class="head-toggle"
        :aria-expanded="!collapsed"
        aria-controls="csv-panel-body"
        :aria-label="collapsed ? $t('properties.csv.openPanel') : $t('properties.csv.collapsePanel')"
        @click="emit('update:collapsed', !collapsed)"
      >
        <span class="chevron" aria-hidden="true">{{ collapsed ? "▸" : "▾" }}</span>
        <span class="head-title">{{ $t("properties.csv.title") }}</span>
      </button>
      <span class="head-status" role="status">{{ csvStatus }}</span>
    </header>
    <div v-if="!collapsed" id="csv-panel-body" class="panel-body">
      <!-- 三个操作常驻（面板展开即见）；下载文件名由后端 Content-Disposition 提供，桌面壳放行页面内下载 -->
      <div class="io-menu">
        <a href="/api/custom-properties/template" download>{{ $t("properties.csv.downloadTemplate") }}</a>
        <a :href="`/api/workspaces/${workspaceId}/custom-properties/export`" download>{{ $t("properties.csv.exportCurrent") }}</a>
        <button v-if="!csvOpen" type="button" :aria-expanded="csvOpen" @click="toggleCsv">{{ $t("properties.csv.importCsv") }}</button>
      </div>
      <div v-show="csvOpen" class="csv-flow">
        <label>{{ $t("properties.csv.fileLabel") }}<input ref="fileInput" type="file" accept=".csv,text/csv" @change="emit('readCsv', $event)"></label>
        <!-- 关闭入口在流程区内：有未导入数据时由 App 先弹确认，确认后清空文件与预览缓存；在途任务不受影响 -->
        <!-- 预览操作在选择文件后才可用（未选择时隐藏）；确认导入为 Danger 分级，无效数据禁用 -->
        <button v-show="hasCsv" type="button" @click="emit('previewCsv')">{{ $t("properties.csv.previewImport") }}</button>
        <button
          type="button"
          class="danger"
          :disabled="writesDisabled || !csvExecutable"
          @click="emit('importCsv')"
        >{{ $t("properties.csv.confirmImport") }}</button>
        <button type="button" :aria-expanded="csvOpen" @click="emit('closeCsv')">{{ $t("properties.csv.closeImport") }}</button>
        <p v-if="!hasCsv" class="csv-hint" role="status">{{ $t("properties.csv.noFileHint") }}</p>
        <p v-else-if="csvPreview && csvPreview.changes.length === 0" class="csv-hint" role="status">{{ $t("properties.csv.noDefinitionChanges") }}</p>
        <p v-else-if="csvPreview && !csvExecutable" class="csv-hint error" role="alert">{{ $t("properties.csv.notExecutableHint") }}</p>
      </div>
      <!-- 预览数据保存在 useCsvImport（App 域）：关闭导入区即清空（有数据先确认），重开需重新选择文件并预览 -->
      <div v-if="csvOpen && csvPreview" class="csv-preview">
        <h3>{{ $t("properties.csv.previewTitle") }}</h3>
        <!-- action/type 为协议稳定码，保持原样（I18N-16）；名称为 CSV 内容（用户数据），不翻译 -->
        <ul class="change-list"><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`" class="csv-change">{{ $t("properties.csv.changeItem", {line: change.line, action: change.action, type: change.type, name: change.name}) }}</li></ul>
        <ul v-if="csvPreview.diagnostics.length > 0" class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">{{ $t("properties.csv.diagLine", {line: item.line}) }}</span><b>{{ item.code }}</b>{{ $t("properties.csv.diagSeparator") }}{{ item.message }}</li></ul>
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
