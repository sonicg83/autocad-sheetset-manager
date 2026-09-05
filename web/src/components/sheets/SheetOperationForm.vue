<script setup lang="ts">
// 三类操作表单（PLAN-DM-015 任务 6，SPEC-DM-009 §6.3）：编辑子集/新增图纸/新建子集。
// 与 SheetPropertyEditor 共用同一唯一编辑上下文：字段输入直接写入上下文缓冲（本组件只呈现与
// 转发），dirty 标记供三选一保护；提交/取消/删除子集/模板文件选择转发给 App.vue。
// 参照以稳定对象 ID 绑定：选择参照对象而非手填序号；目标变化后清除不属于新目标的参照。
// 空图纸集显示「创建首个子集」，不展示不存在的参照；空子集提示当前流程不可用并禁用新增。
import {computed} from "vue";
import type {LayoutSourceType, Placement, Sheet, Subset, Workspace} from "../../api/contracts";
import type {OperationContext} from "../../composables/useSheetEditor";

const props = defineProps<{
  context: OperationContext;
  workspace: Workspace;
}>();

const emit = defineEmits<{
  submit: [];
  cancel: [];
  deleteSubset: [];
  selectTemplateFile: [];
  selectSubsetTemplateFile: [];
  selectBaseTemplateFile: [];
}>();

const context = computed(() => props.context);

const formTitle = computed(() => {
  switch (context.value.kind) {
    case "rename": return "编辑子集";
    case "insert-sheet": return "新增图纸";
    case "insert-subset": return "新建子集";
  }
});

// —— 输入联动：写缓冲副本并标记 dirty（未提交输入保护），不直接改工作区对象 ——
function touch() {
  const c = context.value;
  c.errors = {};
  c.summaryError = "";
  if (c.kind === "insert-sheet" || c.kind === "insert-subset") c.dirty = true;
}
function onRenameTitle(e: Event) {
  const c = context.value;
  if (c.kind !== "rename") return;
  c.values.title = (e.target as HTMLInputElement).value;
  touch();
}
function onRenameSubset(e: Event) {
  const c = context.value;
  if (c.kind !== "rename") return;
  const subsetId = (e.target as HTMLSelectElement).value;
  const subset = props.workspace.sheet_set.subsets.find((s) => s.id === subsetId);
  // 切换编辑对象：缓冲重置为该子集的当前标题（不继承上一个对象的未提交标题）
  c.objectId = subsetId;
  c.subject = subset ? `子集 ${subset.display_name}` : "子集标题编辑";
  c.original = {title: subset?.title ?? ""};
  c.values = {title: subset?.title ?? ""};
  touch();
}

const renameSubset = computed(() => props.workspace.sheet_set.subsets.find((s) => s.id === context.value.objectId) ?? null);

// —— 新增图纸：目标子集 / 参照图纸 / 前后 / 数量 / 模板来源 ——
const targetSubset = computed<Subset | null>(() => {
  const c = context.value;
  if (c.kind !== "insert-sheet") return null;
  return props.workspace.sheet_set.subsets.find((s) => s.id === c.targetSubsetId) ?? null;
});
const referenceOptions = computed<Sheet[]>(() => targetSubset.value?.sheets ?? []);
const referenceSheetId = computed(() => {
  const c = context.value;
  return c.kind === "insert-sheet" ? c.reference?.sheetId ?? "" : "";
});
const emptyTargetSubset = computed(() => {
  const c = context.value;
  return c.kind === "insert-sheet" && c.targetSubsetId !== "" && referenceOptions.value.length === 0;
});
function onInsertTarget(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  const id = (e.target as HTMLSelectElement).value;
  c.targetSubsetId = id;
  // 目标变化后清除不属于新目标的参照（不静默保留旧参照）
  if (c.reference && c.reference.subsetId !== id) c.reference = null;
  touch();
}
function onInsertReference(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  const sheetId = (e.target as HTMLSelectElement).value;
  c.reference = sheetId
    ? {subsetId: c.targetSubsetId, sheetId, placement: c.reference?.placement ?? "after"}
    : null;
  touch();
}
function onInsertPlacement(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  const placement = (e.target as HTMLSelectElement).value as Placement;
  if (c.reference) c.reference = {...c.reference, placement};
  touch();
}
function onInsertCount(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  c.count = (e.target as HTMLInputElement).value;
  touch();
}
function onInsertSourceType(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  c.sourceType = (e.target as HTMLSelectElement).value as LayoutSourceType;
  touch();
}
function onInsertSourceLayout(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-sheet") return;
  c.sourceLayout = (e.target as HTMLInputElement).value;
  touch();
}

// —— 新建子集：标题 / 参照子集 / 前后 / 初始图纸数 / 基础与布局模板（分开标注）——
const isEmptySet = computed(() => props.workspace.sheet_set.subsets.length === 0);
function onSubsetTitle(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-subset") return;
  c.title = (e.target as HTMLInputElement).value;
  touch();
}
function onSubsetReference(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-subset") return;
  c.referenceSubsetId = (e.target as HTMLSelectElement).value;
  touch();
}
function onSubsetPlacement(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-subset") return;
  c.placement = (e.target as HTMLSelectElement).value as Placement;
  touch();
}
function onSubsetCount(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-subset") return;
  c.initialSheetCount = (e.target as HTMLInputElement).value;
  touch();
}
function onSubsetLayout(e: Event) {
  const c = context.value;
  if (c.kind !== "insert-subset") return;
  c.templateLayout = (e.target as HTMLInputElement).value;
  touch();
}

const submitDisabled = computed(() => context.value.invalid || emptyTargetSubset.value);
</script>
<template>
  <section class="operation-form" role="region" :aria-label="formTitle">
    <header class="form-head">
      <h3>{{ formTitle }}</h3>
      <span class="form-head-hint">图号、派生标题、范围和文件/布局派生名不可编辑；派生结果经服务端预览确认</span>
    </header>

    <!-- 编辑子集：显示当前子集、标题输入和只读图号范围，只修改子集标题；
         全部图纸范围下先选择编辑对象（单子集范围打开时预填当前子集） -->
    <template v-if="context.kind === 'rename'">
      <div class="form-body">
        <label class="form-field">
          当前子集
          <select :value="context.objectId" @change="onRenameSubset">
            <option value="">请选择子集</option>
            <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
          </select>
        </label>
        <label class="form-field">
          子集标题
          <input :value="context.values.title" @input="onRenameTitle">
        </label>
        <p class="derived">只读图号范围：{{ renameSubset?.number_range || "—" }} · 显示名：{{ renameSubset?.display_name }}</p>
      </div>
      <div class="form-danger">
        <button type="button" class="danger" @click="$emit('deleteSubset')">删除整个子集</button>
      </div>
    </template>

    <!-- 新增图纸：目标子集、参照图纸、之前/之后、数量、模板来源 -->
    <template v-else-if="context.kind === 'insert-sheet'">
      <div class="form-body">
        <label class="form-field">
          目标子集
          <select :value="context.targetSubsetId" @change="onInsertTarget">
            <option value="">请选择目标子集</option>
            <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
          </select>
        </label>
        <label class="form-field">
          参照图纸
          <select :value="referenceSheetId" :disabled="referenceOptions.length === 0" @change="onInsertReference">
            <option value="">请选择参照图纸</option>
            <option v-for="sheet in referenceOptions" :key="sheet.id" :value="sheet.id">{{ sheet.number }} {{ sheet.title }}</option>
          </select>
        </label>
        <label class="form-field">
          图纸方向
          <select :value="context.reference?.placement ?? 'after'" @change="onInsertPlacement">
            <option value="before">之前</option>
            <option value="after">之后</option>
          </select>
        </label>
        <label class="form-field">
          新增图纸数量
          <input :value="context.count" inputmode="numeric" @input="onInsertCount">
        </label>
        <label class="form-field">
          模板来源
          <select :value="context.sourceType" @change="onInsertSourceType">
            <option value="template_layout">DWG/DWT 模板布局</option>
            <option value="existing_snapshot">已有布局</option>
          </select>
        </label>
        <template v-if="context.sourceType === 'existing_snapshot'">
          <span class="derived">来源为目标子集 DWG 的第一个非 Model 布局</span>
        </template>
        <template v-else>
          <div class="form-field">
            <span>布局模板文件</span>
            <button type="button" @click="$emit('selectTemplateFile')">选择模板文件</button>
            <span v-if="context.sourceFile" class="value">{{ context.sourceFile }}</span>
          </div>
          <label class="form-field">
            布局模板名称
            <span v-if="context.layoutLoading">正在读取布局…</span>
            <template v-else-if="context.layoutError">
              <span class="error">{{ context.layoutError }}</span>
              <input :value="context.sourceLayout" @input="onInsertSourceLayout">
            </template>
            <select v-else-if="context.layoutOptions.length && !context.layoutManual" :value="context.sourceLayout" @change="onInsertSourceLayout">
              <option value="">请选择布局模板名称</option>
              <option v-for="layout in context.layoutOptions" :key="layout" :value="layout">{{ layout }}</option>
            </select>
          </label>
        </template>
        <p v-if="emptyTargetSubset" class="notice" role="status">当前子集没有可用图纸参照，新增流程不可用</p>
      </div>
    </template>

    <!-- 新建子集：标题、参照子集、之前/之后、初始图纸数、基础模板文件、布局模板文件及布局 -->
    <template v-else-if="context.kind === 'insert-subset'">
      <div class="form-body">
        <p v-if="isEmptySet" class="notice" role="status">创建首个子集</p>
        <template v-else>
          <label class="form-field">
            参照子集
            <select :value="context.referenceSubsetId" @change="onSubsetReference">
              <option value="">请选择参照子集</option>
              <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
            </select>
          </label>
          <label class="form-field">
            子集方向
            <select :value="context.placement" @change="onSubsetPlacement">
              <option value="before">之前</option>
              <option value="after">之后</option>
            </select>
          </label>
        </template>
        <label class="form-field">
          子集标题
          <input :value="context.title" @input="onSubsetTitle">
        </label>
        <label class="form-field">
          初始图纸数
          <input :value="context.initialSheetCount" inputmode="numeric" @input="onSubsetCount">
        </label>
        <div class="form-field">
          <span>基础模板文件</span>
          <button type="button" @click="$emit('selectBaseTemplateFile')">选择基础模板文件</button>
          <span v-if="context.baseTemplateFile" class="value">{{ context.baseTemplateFile }}</span>
        </div>
        <div class="form-field">
          <span>布局模板文件</span>
          <button type="button" @click="$emit('selectSubsetTemplateFile')">选择布局模板文件</button>
          <span v-if="context.templateFile" class="value">{{ context.templateFile }}</span>
        </div>
        <label class="form-field">
          布局模板名称
          <span v-if="context.layoutLoading">正在读取布局…</span>
          <template v-else-if="context.layoutError">
            <span class="error">{{ context.layoutError }}</span>
            <input :value="context.templateLayout" @input="onSubsetLayout">
          </template>
          <select v-else-if="context.layoutOptions.length && !context.layoutManual" :value="context.templateLayout" @change="onSubsetLayout">
            <option value="">请选择布局模板名称</option>
            <option v-for="layout in context.layoutOptions" :key="layout" :value="layout">{{ layout }}</option>
          </select>
        </label>
      </div>
    </template>

    <p v-if="context.summaryError" class="error-summary" role="alert">{{ context.summaryError }}</p>

    <footer class="form-footer">
      <span class="form-status" role="status">{{ context.invalid ? "编辑上下文已失效（基准已刷新或对象已消失），禁止提交" : "尚未加入草稿（仅本会话保留）" }}</span>
      <span class="form-spacer"></span>
      <button type="button" @click="$emit('cancel')">取消</button>
      <button type="button" :disabled="submitDisabled" @click="$emit('submit')">加入草稿</button>
    </footer>
  </section>
</template>
<style scoped>
.operation-form{border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);padding:var(--space-4);display:flex;flex-direction:column;gap:var(--space-3);max-height:calc(100vh - 240px)}
.form-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.form-head h3{margin:0;font-size:15px}
.form-head-hint{color:var(--color-text-secondary);font-size:12px}
/* 长表单内部滚动：保留标题与取消/加入草稿入口 */
.form-body{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:var(--space-3);overflow:auto;padding-right:var(--space-2)}
.form-field{display:flex;flex-direction:column;gap:4px;font-size:13px}
.form-field .value{font-size:13px;color:var(--color-text-primary);word-break:break-all}
.derived{color:var(--color-text-secondary);font-size:13px;margin:0}
.notice{padding:var(--space-2) var(--space-3);border-radius:var(--radius-md,8px);font-size:13px;margin:0;background:var(--color-warning-soft,transparent);border:1px solid var(--color-warning,#b7791f)}
.error{color:var(--color-danger,#c53030);font-size:12px}
.error-summary{border:1px solid var(--color-danger,#c53030);background:var(--color-danger-soft,transparent);border-radius:var(--radius-md,8px);padding:var(--space-3);font-size:13px;margin:0;color:var(--color-danger,#c53030)}
.form-danger{border-top:1px solid var(--color-border,var(--color-bg-surface-2));padding-top:var(--space-3)}
.form-danger .danger{color:var(--color-danger,#c53030)}
.form-footer{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:13px;border-top:1px solid var(--color-border,var(--color-bg-surface-2));padding-top:var(--space-3)}
.form-status{color:var(--color-text-secondary)}
.form-spacer{flex:1}
</style>
