<!-- 属性字段定义面板（PLAN-DM-016 任务 4，任务 5 起为纯定义面板，SPEC-DM-010 §3/§4）。
     外壳：折叠标题栏（默认折叠，标题栏始终显示字段总数）、查询区、六条分页、新增/删除。
     CSV 导入导出组合在 PropertyCsvPanel（任务 5 抽出）。
     定义数据来自草稿投影（只读，不修改 workspace）；新增/删除经 emit 交给 App 既有命令簿门禁
     （与 submitCommands(...,'property') 同一草稿栈，不得绕过 hasStructuralCommands 分批门禁）。
     过滤/分页为纯派生（features/properties/model）：查询/筛选变化回第一页，删除后回退到最后有效页；
     新增成功清空输入、失败就近展示字段错误并保留输入，与当前筛选不匹配时提示并提供「查看字段」。
     样式全部 scoped 且只用语义令牌。 -->
<script setup lang="ts">
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {PropertyDefinition, PropertyType} from "../../api/contracts";
import {DEFINITIONS_PAGE_SIZE, definitionKey, definitionMatches, filterDefinitions} from "../../features/properties/model";
import type {DefinitionScopeFilter} from "../../features/properties/model";
import UiButton from "../ui/UiButton.vue";
import UiIcon from "../ui/UiIcon.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import PropertyDefinitionTable from "./PropertyDefinitionTable.vue";

const props = defineProps<{
  definitions: PropertyDefinition[];
  // 新增表单为工作区会话态（usePropertiesWorkspace.definitionForm），经 App 传入共享
  form: {type: PropertyType; name: string; defaultValue: string};
  // 折叠/查询/作用域/页码为工作区会话态（PLAN-DM-016 任务 6）：切 workspace 重置，切主标签保留
  collapsed: boolean;
  query: string;
  scopeFilter: DefinitionScopeFilter;
  page: number;
}>();
const emit = defineEmits<{
  addDefinition: [];
  deleteDefinition: [definition: PropertyDefinition];
  "update:collapsed": [value: boolean];
  "update:query": [value: string];
  "update:scopeFilter": [value: DefinitionScopeFilter];
  "update:page": [value: number];
}>();

// 稳定作用域枚举 → 语义键映射（I18N-16：枚举值本身不翻译）
const {t} = useI18n();
function scopeLabel(definition: PropertyDefinition): string {
  return t(definition.type === "sheetset" ? "properties.scope.sheetset" : "properties.scope.sheet");
}

// 新增区字段的原语 id：原语把 id 透传到内部控件，焦点回到名称输入需按 id 定位
// （与仓内既有「显式 id + getElementById」范式一致，不穿透明细节）。
const ADD_SCOPE_ID = "definition-add-scope";
const ADD_NAME_ID = "definition-add-name";
const ADD_DEFAULT_ID = "definition-add-default";

// —— 折叠（默认折叠；仅隐藏内容，不清空输入；会话态经 emit 上报）——
function toggleCollapsed() { emit("update:collapsed", !props.collapsed); }

// —— 查询与分页：状态在会话态，本面板只做派生与上报（SPEC-DM-010 §4.1）——
const filtered = computed(() => filterDefinitions(props.definitions, props.query, props.scopeFilter));
const lastPage = computed(() => Math.max(1, Math.ceil(filtered.value.length / DEFINITIONS_PAGE_SIZE)));
const pageRows = computed(() => filtered.value.slice((props.page - 1) * DEFINITIONS_PAGE_SIZE, props.page * DEFINITIONS_PAGE_SIZE));
watch([() => props.query, () => props.scopeFilter], () => { if (props.page !== 1) emit("update:page", 1); });    // 查询/筛选变化回第一页
watch(lastPage, (value) => { const next = Math.min(props.page, value); if (next !== props.page) emit("update:page", next); }); // 删除后回退到最后有效页
function changePage(value: number) { emit("update:page", value); }
function clearFilter() { emit("update:query", ""); emit("update:scopeFilter", "all"); }

// —— 查询控件（改成原语后由原语上报值，不再从事件目标读值）——
function setQuery(value: string) { emit("update:query", value); }
function setScopeFilter(value: string) { emit("update:scopeFilter", value as DefinitionScopeFilter); }

// —— 新增区（SPEC-DM-010 §4.2）：仅作用域/名称/默认值；成功清空，失败保留输入并就近展示错误 ——
const adding = ref(false);
const nameError = ref("");
const addToggleButton = ref<InstanceType<typeof UiButton> | null>(null);
function focusAddName() { document.getElementById(ADD_NAME_ID)?.focus(); }
function setAddScope(value: string) { props.form.type = value as PropertyType; }
function setAddName(value: string) { props.form.name = value; nameError.value = ""; }
function setAddDefault(value: string) { props.form.defaultValue = value; }
// openAdd 可指定预置作用域（值面板「新增 sheetset 字段」入口调用）：展开面板并聚焦名称输入
async function openAdd(scope?: "sheet" | "sheetset") {
  if (scope) props.form.type = scope;
  if (props.collapsed) emit("update:collapsed", false);
  adding.value = true;
  await nextTick();
  focusAddName();
}
defineExpose({openAdd});
function closeAdd() {
  adding.value = false;
  nameError.value = "";
  addHint.value = "";
  pendingAddKey.value = null;
  hiddenAddedKey.value = null;
  props.form.name = "";           // 关闭新增清空输入（form 为工作区会话共享表单状态）
  props.form.defaultValue = "";
  addToggleButton.value?.$el.focus(); // 关闭录入区后焦点回到有效控件
}
function submitAdd() {
  nameError.value = "";
  addHint.value = "";
  const name = props.form.name.trim();
  if (!name) {
    nameError.value = t("properties.errors.propertyNameEmpty");
    focusAddName();
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
  if (definitionMatches(added, props.query, props.scopeFilter)) {
    emit("update:page", Math.floor(definitions.indexOf(added) / DEFINITIONS_PAGE_SIZE) + 1); // 使新增定义可见
    addHint.value = t("properties.definitions.addHint", {scope: scopeLabel(added), name: added.name});
  } else {
    hiddenAddedKey.value = definitionKey(added);
    addHint.value = t("properties.definitions.addHintFiltered", {scope: scopeLabel(added), name: added.name});
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
  emit("update:page", Math.floor(index / DEFINITIONS_PAGE_SIZE) + 1);
}

// —— CSV 区已移交 PropertyCsvPanel（任务 5）：本面板只负责定义查询/分页/新增/删除 ——
</script>
<template>
  <section class="definition-panel" :aria-label="$t('properties.definitions.panelAria')">
    <header class="panel-head">
      <button
        type="button"
        class="head-toggle"
        :aria-expanded="!collapsed"
        aria-controls="definition-body"
        :aria-label="collapsed ? $t('properties.definitions.openPanel') : $t('properties.definitions.collapsePanel')"
        @click="toggleCollapsed"
      >
        <UiIcon :name="collapsed ? 'chevron-right' : 'chevron-down'" size="sm" class="chevron" />
        <span class="head-title">{{ $t("properties.definitions.title") }} <small>{{ $t("properties.definitions.totalItems", {count: definitions.length}) }}</small></span>
      </button>
      <div class="link-actions">
        <UiButton ref="addToggleButton" variant="primary" @click="adding ? closeAdd() : openAdd()">{{ adding ? $t("properties.definitions.closeAdd") : $t("properties.definitions.addField") }}</UiButton>
      </div>
    </header>
    <div v-if="!collapsed" id="definition-body" class="panel-body">
      <div class="query-bar">
        <div class="query-search">
          <UiInput
            type="search"
            :label="$t('properties.definitions.searchLabel')"
            :placeholder="$t('properties.definitions.searchPlaceholder')"
            :model-value="query"
            @update:model-value="setQuery"
          />
        </div>
        <UiSelect
          :label="$t('properties.definitions.scopeFilterLabel')"
          :model-value="scopeFilter"
          @update:model-value="setScopeFilter"
        >
          <option value="all">{{ $t("properties.definitions.scopeAll") }}</option>
          <option value="sheetset">{{ $t("properties.scope.sheetset") }}</option>
          <option value="sheet">{{ $t("properties.scope.sheet") }}</option>
        </UiSelect>
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
          <UiSelect :id="ADD_SCOPE_ID" :label="$t('properties.definitions.addScopeLabel')" :model-value="form.type" @update:model-value="setAddScope">
            <option value="sheet">{{ $t("properties.scope.sheet") }}</option>
            <option value="sheetset">{{ $t("properties.scope.sheetset") }}</option>
          </UiSelect>
          <UiInput
            :id="ADD_NAME_ID"
            :label="$t('properties.definitions.addNameLabel')"
            :model-value="form.name"
            autocomplete="off"
            :invalid="Boolean(nameError)"
            :described-by="nameError ? 'definition-name-error' : undefined"
            @update:model-value="setAddName"
          />
          <UiInput :id="ADD_DEFAULT_ID" :label="$t('properties.definitions.addDefaultValueLabel')" :model-value="form.defaultValue" autocomplete="off" @update:model-value="setAddDefault" />
        </div>
        <p v-if="nameError" id="definition-name-error" class="field-error" role="alert">{{ nameError }}</p>
        <div class="add-actions">
          <span class="hint">{{ $t("properties.definitions.addDraftHint") }}</span>
          <UiButton variant="primary" class="submit-add" @click="submitAdd">{{ $t("properties.definitions.addToDraft") }}</UiButton>
        </div>
      </div>
      <p v-if="addHint" class="add-hint" role="status">
        {{ addHint }}
        <button v-if="hiddenAddedKey" type="button" class="link" @click="viewAddedField">{{ $t("properties.definitions.viewField") }}</button>
      </p>
    </div>
  </section>
</template>
<style scoped>
.definition-panel{background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:var(--panel-head-min-height);padding:var(--space-2) var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
/* 折叠开关是复合标题控件（字形 + 标题 + 计数），保留原生按钮；最小高度消费普通档结构令牌 */
.head-toggle{display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);min-height:var(--control-height-default)}
/* 标题文字用 span（button 内不允许 h2）：面板名由 section aria-label 与按钮 aria-label 提供 */
.head-title{margin:0;font-size:var(--font-label);font-weight:600}
.head-title small{font-weight:400;color:var(--color-text-secondary);font-size:var(--font-caption)}
.chevron{color:var(--color-text-secondary)}
.link-actions{margin-left:auto;display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:center}
.panel-body{padding:var(--space-4) var(--space-5)}
/* 可见弱化 label 位于控件上方：工具行按底边对齐，使 38px 输入与 36px 按钮中心差不超过 1px */
.query-bar{display:flex;gap:var(--space-2);align-items:flex-end;flex-wrap:wrap;margin-bottom:var(--space-3)}
.query-search{width:var(--panel-search-width)}
/* 新增区：仅作用域/名称/默认值，字段组合与 38px 控件由原语提供 */
.add-form{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-canvas);padding:var(--space-3);margin-top:var(--space-4)}
.add-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,260px));gap:var(--space-3);justify-content:start}
.add-actions{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;margin-top:var(--space-3)}
.submit-add{margin-left:auto}
.add-actions .hint{color:var(--color-text-muted);font-size:var(--font-caption)}
.field-error{margin:var(--space-2) 0 0;color:var(--color-danger);font-size:var(--font-caption)}
.add-hint{margin:var(--space-3) 0 0;color:var(--color-success);font-size:var(--font-label);display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.add-hint .link{color:var(--color-accent);text-decoration:underline}
</style>
