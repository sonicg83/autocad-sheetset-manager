<!-- 属性字段定义面板（PLAN-DM-016 任务 4，SPEC-DM-010 §3/§4）。
     外壳：折叠标题栏（默认折叠，标题栏始终显示字段总数）、查询区、六条分页、新增/删除与 CSV 区组合。
     定义数据来自草稿投影（只读，不修改 workspace）；新增/删除经 emit 交给 App 既有命令簿门禁
     （与 submitCommands(...,'property') 同一草稿栈，不得绕过 hasStructuralCommands 分批门禁）。
     过滤/分页为纯派生（features/properties/model）：查询/筛选变化回第一页，删除后回退到最后有效页；
     新增成功清空输入、失败就近展示字段错误并保留输入，与当前筛选不匹配时提示并提供「查看字段」。
     CSV 区为任务 5 前的过渡承载：默认收起、不常驻文件选择器，任务 5 抽为 PropertyCsvPanel。
     样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import type {CsvPreview, PropertyDefinition, PropertyType} from "../../api/contracts";
import {DEFINITIONS_PAGE_SIZE, definitionKey, definitionMatches, filterDefinitions} from "../../features/properties/model";
import type {DefinitionScopeFilter} from "../../features/properties/model";
import PropertyDefinitionTable from "./PropertyDefinitionTable.vue";

const props = defineProps<{
  definitions: PropertyDefinition[];
  // 新增表单状态由 App 持有（与既有 queuePropertyDefinition 门禁共用），任务 6 移交组合式函数
  form: {type: PropertyType; name: string; defaultValue: string};
  workspaceId: string;
  hasCsv: boolean;
  csvPreview: CsvPreview | null;
  csvExecutable: boolean;
  writesDisabled: boolean;
}>();
const emit = defineEmits<{
  addDefinition: [];
  deleteDefinition: [definition: PropertyDefinition];
  readCsv: [event: Event];
  previewCsv: [];
  importCsv: [];
}>();

function scopeLabel(definition: PropertyDefinition): string {
  return definition.type === "sheetset" ? "图纸集" : "图纸";
}

// —— 折叠（默认折叠；仅隐藏内容，不清空输入；任务 6 起提升为工作区会话态）——
const collapsed = ref(true);
function toggleCollapsed() { collapsed.value = !collapsed.value; }

// —— 查询与分页：面板持有，表格只展示（SPEC-DM-010 §4.1）——
const query = ref("");
const scopeFilter = ref<DefinitionScopeFilter>("all");
const page = ref(1);
const filtered = computed(() => filterDefinitions(props.definitions, query.value, scopeFilter.value));
const lastPage = computed(() => Math.max(1, Math.ceil(filtered.value.length / DEFINITIONS_PAGE_SIZE)));
const pageRows = computed(() => filtered.value.slice((page.value - 1) * DEFINITIONS_PAGE_SIZE, page.value * DEFINITIONS_PAGE_SIZE));
watch([query, scopeFilter], () => { page.value = 1; });                       // 查询/筛选变化回第一页
watch(lastPage, (value) => { page.value = Math.min(page.value, value); });    // 删除后回退到最后有效页
function changePage(value: number) { page.value = value; }
function clearFilter() { query.value = ""; scopeFilter.value = "all"; }

// —— 新增区（SPEC-DM-010 §4.2）：仅作用域/名称/默认值；成功清空，失败保留输入并就近展示错误 ——
const adding = ref(false);
const nameError = ref("");
const addNameInput = ref<HTMLInputElement | null>(null);
const addToggleButton = ref<HTMLButtonElement | null>(null);
async function openAdd() {
  collapsed.value = false;
  adding.value = true;
  await nextTick();
  addNameInput.value?.focus();
}
function closeAdd() {
  adding.value = false;
  nameError.value = "";
  addHint.value = "";
  pendingAddKey.value = null;
  hiddenAddedKey.value = null;
  props.form.name = "";           // 关闭新增清空输入（form 为 App 持有的共享表单状态）
  props.form.defaultValue = "";
  addToggleButton.value?.focus(); // 关闭录入区后焦点回到有效控件
}
function submitAdd() {
  nameError.value = "";
  addHint.value = "";
  const name = props.form.name.trim();
  if (!name) {
    nameError.value = "属性名称不能为空";
    addNameInput.value?.focus();
    return;
  }
  pendingAddKey.value = definitionKey({type: props.form.type, name, default_value: props.form.defaultValue});
  emit("addDefinition"); // 命令簿门禁在 App：结构命令存在时返回既有分批提示且不改投影
}

// —— 新增结果：命令簿投影出现该定义即成功；与当前筛选不匹配时提示并提供「查看字段」——
const pendingAddKey = ref<string | null>(null);
const addHint = ref("");
const hiddenAddedKey = ref<string | null>(null);
watch(() => props.definitions, (definitions) => {
  const key = pendingAddKey.value;
  if (!key) return;
  const added = definitions.find((definition) => definitionKey(definition) === key);
  if (!added) return;
  pendingAddKey.value = null;
  if (definitionMatches(added, query.value, scopeFilter.value)) {
    page.value = Math.floor(definitions.indexOf(added) / DEFINITIONS_PAGE_SIZE) + 1; // 使新增定义可见
    addHint.value = `已加入草稿：${scopeLabel(added)}属性「${added.name}」`;
  } else {
    hiddenAddedKey.value = definitionKey(added);
    addHint.value = `已加入草稿：${scopeLabel(added)}属性「${added.name}」与当前筛选不匹配`;
  }
});
// 「查看字段」：显式清除筛选（不静默更改作用域）并跳到新增定义所在页。
// 页码在查询/筛选复位之后设置（等复位 flush 完成再跳页），避免被 page=1 复位覆盖。
async function viewAddedField() {
  const key = hiddenAddedKey.value;
  hiddenAddedKey.value = null;
  addHint.value = "";
  clearFilter();
  if (!key) return;
  const index = props.definitions.findIndex((definition) => definitionKey(definition) === key);
  if (index < 0) return;
  await nextTick();
  page.value = Math.floor(index / DEFINITIONS_PAGE_SIZE) + 1;
}

// —— CSV 区（任务 5 前过渡承载）：默认收起，不常驻文件选择器与确认按钮；打开时同时展开面板 ——
const csvOpen = ref(false);
function toggleCsv() {
  csvOpen.value = !csvOpen.value;
  if (csvOpen.value) collapsed.value = false;
}
</script>
<template>
  <section class="definition-panel" aria-label="属性字段定义">
    <header class="panel-head">
      <button
        type="button"
        class="head-toggle"
        :aria-expanded="!collapsed"
        aria-controls="definition-body"
        :aria-label="collapsed ? '展开属性字段定义' : '收起属性字段定义'"
        @click="toggleCollapsed"
      >
        <span class="chevron" aria-hidden="true">{{ collapsed ? "▸" : "▾" }}</span>
        <h2>属性字段定义 <small>共 {{ definitions.length }} 项</small></h2>
      </button>
      <div class="link-actions">
        <a href="/api/custom-properties/template" download>下载 CSV 模板</a>
        <a :href="`/api/workspaces/${workspaceId}/custom-properties/export`" download>导出当前属性</a>
        <button type="button" :aria-expanded="csvOpen" @click="toggleCsv">导入 CSV</button>
        <button ref="addToggleButton" type="button" class="primary" @click="adding ? closeAdd() : openAdd()">{{ adding ? "关闭新增" : "新增字段" }}</button>
      </div>
    </header>
    <div v-if="!collapsed" id="definition-body" class="panel-body">
      <div class="query-bar">
        <input
          type="search"
          aria-label="搜索字段"
          placeholder="搜索字段名或默认值"
          :value="query"
          @input="query = ($event.target as HTMLInputElement).value"
        >
        <select
          aria-label="作用域筛选"
          :value="scopeFilter"
          @change="scopeFilter = ($event.target as HTMLSelectElement).value as DefinitionScopeFilter"
        >
          <option value="all">全部作用域</option>
          <option value="sheetset">图纸集</option>
          <option value="sheet">图纸</option>
        </select>
      </div>
      <PropertyDefinitionTable
        :rows="pageRows"
        :page="page"
        :last-page="lastPage"
        :matched-count="filtered.length"
        :total-count="definitions.length"
        @change-page="changePage"
        @clear-filter="clearFilter"
        @delete-definition="(definition) => emit('deleteDefinition', definition)"
      />
      <div v-if="adding" class="add-form">
        <div class="add-grid">
          <label>属性作用域
            <select v-model="form.type">
              <option value="sheet">图纸</option>
              <option value="sheetset">图纸集</option>
            </select>
          </label>
          <label>属性名称
            <input
              ref="addNameInput"
              v-model="form.name"
              type="text"
              autocomplete="off"
              :aria-invalid="nameError ? 'true' : undefined"
              :aria-describedby="nameError ? 'definition-name-error' : undefined"
              @input="nameError = ''"
            >
          </label>
          <label>默认值<input v-model="form.defaultValue" type="text" autocomplete="off"></label>
        </div>
        <p v-if="nameError" id="definition-name-error" class="field-error" role="alert">{{ nameError }}</p>
        <div class="add-actions">
          <span class="hint">新增仅加入草稿：分批预览后才执行，不直接写入工程文件</span>
          <button type="button" class="primary" @click="submitAdd">加入草稿</button>
        </div>
      </div>
      <p v-if="addHint" class="add-hint" role="status">
        {{ addHint }}
        <button v-if="hiddenAddedKey" type="button" class="link" @click="viewAddedField">查看字段</button>
      </p>
      <template v-if="csvOpen">
        <div class="csv-flow">
          <label>属性 CSV 文件<input type="file" accept=".csv,text/csv" @change="emit('readCsv', $event)"></label>
          <button type="button" :disabled="!hasCsv" @click="emit('previewCsv')">预览 CSV 导入</button>
          <button type="button" class="primary" :disabled="writesDisabled || !csvExecutable" @click="emit('importCsv')">确认导入</button>
        </div>
        <div v-if="csvPreview" class="csv-preview">
          <h3>CSV 合并预览</h3>
          <ul><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`">第 {{ change.line }} 行 · {{ change.action }} · {{ change.type }} · {{ change.name }}</li></ul>
          <ul class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">第 {{ item.line }} 行 · </span><b>{{ item.code }}</b>：{{ item.message }}</li></ul>
        </div>
      </template>
    </div>
  </section>
</template>
<style scoped>
.definition-panel{background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);margin-bottom:var(--space-4);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:60px;padding:var(--space-2) var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
/* 折叠开关沿用属性页受控按钮基线（≥36px、边框与不透明背景），仅排布为标题样式 */
.head-toggle{display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);min-height:36px}
.head-toggle h2{margin:0;font-size:16px}
.head-toggle small{font-weight:400;color:var(--color-text-secondary);font-size:12px}
.chevron{color:var(--color-text-secondary);font-size:12px}
.link-actions{margin-left:auto;display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:center}
.link-actions a{display:inline-flex;align-items:center;min-height:36px;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary)}
.link-actions button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.panel-body{padding:var(--space-4) var(--space-5)}
.query-bar{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap;margin-bottom:var(--space-3)}
.query-bar input[type="search"]{height:38px;width:280px;min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.query-bar select{height:38px;padding:6px 8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
/* 新增区：仅作用域/名称/默认值，输入与选择器 38px */
.add-form{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-canvas);padding:var(--space-3);margin-top:var(--space-4)}
.add-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,260px));gap:var(--space-3);justify-content:start}
.add-grid label{display:grid;gap:var(--space-1);color:var(--color-text-secondary);font-size:13px}
.add-grid input,.add-grid select{height:38px;width:100%;min-width:0;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.add-grid input[aria-invalid="true"]{border-color:var(--color-danger)}
.add-actions{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;margin-top:var(--space-3)}
.add-actions .primary{margin-left:auto;background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.add-actions .hint{color:var(--color-text-muted);font-size:12px}
.field-error{margin:var(--space-2) 0 0;color:var(--color-danger);font-size:12px}
.add-hint{margin:var(--space-3) 0 0;color:var(--color-success);font-size:13px;display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.add-hint .link{color:var(--color-accent);text-decoration:underline}
/* CSV 过渡承载沿用既有紧凑流式布局（任务 5 抽为 PropertyCsvPanel） */
.csv-flow{display:flex;align-items:end;gap:var(--space-3);flex-wrap:wrap;margin-top:var(--space-4);padding-top:var(--space-4);border-top:1px solid var(--color-border-subtle)}
.csv-flow label{display:grid;gap:var(--space-1);color:var(--color-text-secondary);font-size:13px}
.csv-flow input{min-width:0;padding:8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm)}
.csv-flow button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.csv-preview{margin-top:var(--space-3);background:var(--color-bg-muted);padding:var(--space-3);border-radius:var(--radius-md)}
.csv-preview h3{margin:0 0 var(--space-2);font-size:14px}
.csv-preview ul{margin:var(--space-2) 0;padding-left:20px}
.diagnostics .error{color:var(--color-danger)}
.diagnostics .warning{color:var(--color-warning)}
</style>
