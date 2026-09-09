<script setup lang="ts">
// 三类操作表单（PLAN-DM-015 任务 6，SPEC-DM-009 §6.3）：编辑子集/新增图纸/新建子集。
// 与 SheetPropertyEditor 共用同一唯一编辑上下文：字段输入直接写入上下文缓冲（本组件只呈现与
// 转发），dirty 标记供三选一保护；提交/取消/删除子集/模板文件选择转发给 App.vue。
// 参照以稳定对象 ID 绑定：选择参照对象而非手填序号；目标变化后清除不属于新目标的参照。
// 空图纸集显示「创建首个子集」，不展示不存在的参照；空子集提示当前流程不可用并禁用新增。
import {computed} from "vue";
import {useI18n} from "vue-i18n";
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
const {t} = useI18n();
// 操作类型 → 表单标题语义键映射（稳定操作类型 → sheets.operation.*）
const OPERATION_TITLE_KEYS = {rename: "sheets.operation.renameTitle", "insert-sheet": "sheets.operation.insertSheetTitle", "insert-subset": "sheets.operation.insertSubsetTitle"} as const;

const formTitle = computed(() => t(OPERATION_TITLE_KEYS[context.value.kind]));

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
  c.subject = subset ? t("sheets.subjects.subset", {name: subset.display_name}) : t("sheets.subjects.subsetTitleEdit");
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
      <span class="form-head-hint">{{ $t("sheets.operation.headHint") }}</span>
    </header>

    <!-- 编辑子集：显示当前子集、标题输入和只读图号范围，只修改子集标题；
         全部图纸范围下先选择编辑对象（单子集范围打开时预填当前子集） -->
    <template v-if="context.kind === 'rename'">
      <div class="form-body">
        <label class="form-field">
          {{ $t("sheets.operation.currentSubset") }}
          <select :value="context.objectId" @change="onRenameSubset">
            <option value="">{{ $t("sheets.operation.pickSubset") }}</option>
            <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
          </select>
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.subsetTitle") }}
          <input :value="context.values.title" @input="onRenameTitle">
        </label>
        <p class="derived">{{ $t("sheets.operation.derivedRange", {range: renameSubset?.number_range || "—", name: renameSubset?.display_name ?? ""}) }}</p>
      </div>
      <div class="form-danger">
        <!-- 未选择编辑对象时禁用危险入口，避免静默无操作（任务 7 修：全部范围先选对象） -->
        <button type="button" class="danger" :disabled="!context.objectId" @click="$emit('deleteSubset')">{{ $t("sheets.operation.deleteSubset") }}</button>
      </div>
    </template>

    <!-- 新增图纸：目标子集、参照图纸、之前/之后、数量、模板来源 -->
    <template v-else-if="context.kind === 'insert-sheet'">
      <div class="form-body">
        <label class="form-field">
          {{ $t("sheets.operation.targetSubset") }}
          <select :value="context.targetSubsetId" @change="onInsertTarget">
            <option value="">{{ $t("sheets.operation.pickTargetSubset") }}</option>
            <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
          </select>
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.referenceSheet") }}
          <select :value="referenceSheetId" :disabled="referenceOptions.length === 0" @change="onInsertReference">
            <option value="">{{ $t("sheets.operation.pickReferenceSheet") }}</option>
            <option v-for="sheet in referenceOptions" :key="sheet.id" :value="sheet.id">{{ sheet.number }} {{ sheet.title }}</option>
          </select>
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.placement") }}
          <select :value="context.reference?.placement ?? 'after'" @change="onInsertPlacement">
            <option value="before">{{ $t("sheets.operation.before") }}</option>
            <option value="after">{{ $t("sheets.operation.after") }}</option>
          </select>
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.sheetCount") }}
          <input :value="context.count" inputmode="numeric" @input="onInsertCount">
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.sourceType") }}
          <select :value="context.sourceType" @change="onInsertSourceType">
            <option value="template_layout">{{ $t("sheets.operation.sourceTemplateLayout") }}</option>
            <option value="existing_snapshot">{{ $t("sheets.operation.sourceExistingSnapshot") }}</option>
          </select>
        </label>
        <template v-if="context.sourceType === 'existing_snapshot'">
          <span class="derived">{{ $t("sheets.operation.existingSnapshotHint") }}</span>
        </template>
        <template v-else>
          <div class="form-field">
            <span>{{ $t("sheets.operation.layoutTemplateFile") }}</span>
            <button type="button" @click="$emit('selectTemplateFile')">{{ $t("sheets.operation.selectTemplateFile") }}</button>
            <span v-if="context.sourceFile" class="value">{{ context.sourceFile }}</span>
          </div>
          <label class="form-field">
            {{ $t("sheets.operation.layoutTemplateName") }}
            <span v-if="context.layoutLoading">{{ $t("sheets.operation.layoutLoading") }}</span>
            <template v-else-if="context.layoutError">
              <span class="error">{{ context.layoutError }}</span>
              <input :value="context.sourceLayout" @input="onInsertSourceLayout">
            </template>
            <select v-else-if="context.layoutOptions.length && !context.layoutManual" :value="context.sourceLayout" @change="onInsertSourceLayout">
              <option value="">{{ $t("sheets.operation.pickLayoutTemplate") }}</option>
              <option v-for="layout in context.layoutOptions" :key="layout" :value="layout">{{ layout }}</option>
            </select>
          </label>
        </template>
        <p v-if="emptyTargetSubset" class="notice" role="status">{{ $t("sheets.operation.emptyReferenceNotice") }}</p>
      </div>
    </template>

    <!-- 新建子集：标题、参照子集、之前/之后、初始图纸数、基础模板文件、布局模板文件及布局 -->
    <template v-else-if="context.kind === 'insert-subset'">
      <div class="form-body">
        <p v-if="isEmptySet" class="notice" role="status">{{ $t("sheets.view.createFirstSubset") }}</p>
        <template v-else>
          <label class="form-field">
            {{ $t("sheets.operation.referenceSubset") }}
            <select :value="context.referenceSubsetId" @change="onSubsetReference">
              <option value="">{{ $t("sheets.operation.pickReferenceSubset") }}</option>
              <option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{ subset.display_name }}</option>
            </select>
          </label>
          <label class="form-field">
            {{ $t("sheets.operation.subsetPlacement") }}
            <select :value="context.placement" @change="onSubsetPlacement">
              <option value="before">{{ $t("sheets.operation.before") }}</option>
              <option value="after">{{ $t("sheets.operation.after") }}</option>
            </select>
          </label>
        </template>
        <label class="form-field">
          {{ $t("sheets.operation.subsetTitle") }}
          <input :value="context.title" @input="onSubsetTitle">
        </label>
        <label class="form-field">
          {{ $t("sheets.operation.initialSheetCount") }}
          <input :value="context.initialSheetCount" inputmode="numeric" @input="onSubsetCount">
        </label>
        <div class="form-field">
          <span>{{ $t("sheets.operation.baseTemplateFile") }}</span>
          <button type="button" @click="$emit('selectBaseTemplateFile')">{{ $t("sheets.operation.selectBaseTemplateFile") }}</button>
          <span v-if="context.baseTemplateFile" class="value">{{ context.baseTemplateFile }}</span>
        </div>
        <div class="form-field">
          <span>{{ $t("sheets.operation.layoutTemplateFile") }}</span>
          <button type="button" @click="$emit('selectSubsetTemplateFile')">{{ $t("sheets.operation.selectLayoutTemplateFile") }}</button>
          <span v-if="context.templateFile" class="value">{{ context.templateFile }}</span>
        </div>
        <label class="form-field">
          {{ $t("sheets.operation.layoutTemplateName") }}
          <span v-if="context.layoutLoading">{{ $t("sheets.operation.layoutLoading") }}</span>
          <template v-else-if="context.layoutError">
            <span class="error">{{ context.layoutError }}</span>
            <input :value="context.templateLayout" @input="onSubsetLayout">
          </template>
          <select v-else-if="context.layoutOptions.length && !context.layoutManual" :value="context.templateLayout" @change="onSubsetLayout">
            <option value="">{{ $t("sheets.operation.pickLayoutTemplate") }}</option>
            <option v-for="layout in context.layoutOptions" :key="layout" :value="layout">{{ layout }}</option>
          </select>
        </label>
      </div>
    </template>

    <p v-if="context.summaryError" class="error-summary" role="alert">{{ context.summaryError }}</p>

    <footer class="form-footer">
      <span class="form-status" role="status">{{ context.invalid ? $t("sheets.operation.statusInvalid") : $t("sheets.operation.statusDraft") }}</span>
      <span class="form-spacer"></span>
      <button type="button" @click="$emit('cancel')">{{ $t("sheets.operation.cancel") }}</button>
      <button type="button" class="primary" :disabled="submitDisabled" @click="$emit('submit')">{{ $t("sheets.operation.addToDraft") }}</button>
    </footer>
  </section>
</template>
<style scoped>
.operation-form{padding:var(--space-4);display:flex;flex-direction:column;gap:var(--space-3);max-height:calc(100vh - 240px)}
.form-head{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-height:0;padding:0;color:var(--color-text-primary)}
.form-head h3{margin:0;font-size:15px}
.form-head-hint{color:var(--color-text-secondary);font-size:12px}
/* 长表单内部滚动：保留标题与取消/加入草稿入口 */
.form-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-3);overflow:auto;padding:4px var(--space-2) 4px 4px}
.form-field{display:flex;flex-direction:column;gap:4px;font-size:13px}
.operation-form :is(input:not([type="checkbox"]),select,textarea){height:38px;min-width:0;width:100%;padding:6px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);font:inherit}
.operation-form :is(input,select,textarea):focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.operation-form :is(input,select,textarea):hover:not(:disabled){border-color:var(--color-accent)}
.operation-form :is(input,select,textarea):disabled{background:var(--color-bg-muted);color:var(--color-text-muted);cursor:not-allowed}
.operation-form button{min-height:36px;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);background:var(--color-bg-surface);color:var(--color-text-primary)}
.operation-form button.primary{background:var(--color-accent);border-color:var(--color-accent);color:var(--color-on-accent)}
.operation-form button.primary:hover:not(:disabled){background:var(--color-accent-hover)}
.operation-form button.primary:active:not(:disabled){background:var(--color-accent-active)}
.form-field .value{font-size:13px;color:var(--color-text-primary);word-break:break-all}
.derived{color:var(--color-text-secondary);font-size:13px;margin:0}
.notice{padding:var(--space-2) var(--space-3);border-radius:var(--radius-md,8px);font-size:13px;margin:0;background:var(--color-warning-bg);border:1px solid var(--color-warning)}
.error{color:var(--color-danger);font-size:12px}
.error-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);border-radius:var(--radius-md,8px);padding:var(--space-3);font-size:13px;margin:0;color:var(--color-danger)}
.form-danger{border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3)}
.form-danger .danger{color:var(--color-danger)}
.form-footer{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;font-size:13px;border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3)}
.form-status{color:var(--color-text-secondary)}
.form-spacer{flex:1}
@media(max-width:900px){.form-body{grid-template-columns:minmax(0,1fr)}}
</style>
