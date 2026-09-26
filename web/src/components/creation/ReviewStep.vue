<script setup lang="ts">
// 第四阶段：检查并创建（SPEC-DM-018 §6；PLAN-DM-036 Task 9）。
// 只呈现**后端权威预览**：顶部固定标准与版本、最终项目路径、组数/张数/DWG 数、当前编号
// 设置与检查状态；主表每个图纸组一行（图纸组｜图纸范围｜图纸｜张数｜文件名｜基础模板｜
// 布局模板｜图幅｜标准动态 sheet 属性列），不提供单张 Sheet 行与「布局」列。图号范围、
// 紧凑标题、DWG 文件名与逐张属性值都原样来自预览响应，前端不推算。
// 诊断区区分阻断错误与非阻断提示，可定位的错误给出跳回按钮（定位在页面层执行）；仅当后端
// 预览无阻断错误时可创建，创建前展示最终路径与不可覆盖确认，执行只发送 `preview_digest`。
// 任务进度复用全局任务浮层的任务面板组件与终态语义（创建期尚无工作区，故在本页内呈现）。
import {computed, onMounted, ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import JobStatusPanel from "../JobStatusPanel.vue";
import SheetValuesDialog from "./SheetValuesDialog.vue";
import {isTerminalJobStatus} from "../../composables/useJobMonitor";
import {
  groupSheetValues,
  previewDiagnosticTarget,
  previewPropertyColumns,
  splitPreviewDiagnostics,
} from "../../features/creation/previewModel";
import type {
  CreationPreviewPropertyColumn,
  CreationPreviewTarget,
} from "../../features/creation/previewModel";
import type {
  CreationPreviewDiagnostic,
  CreationPreviewGroup,
} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";
import type {ConfirmOptions} from "../../composables/useConfirm";
import type {Job} from "../../api/contracts";

const props = defineProps<{
  store: CreationStore;
  confirmAction: (options: ConfirmOptions) => Promise<boolean>;
  /** 当前创建任务（由页面监视并传入）；`null` 表示尚未执行过。 */
  job: Job | null;
  connectionMode: string;
}>();
const emit = defineEmits<{
  execute: [];
  locate: [target: CreationPreviewTarget];
}>();
const {t, te} = useI18n();

const preview = computed(() => props.store.previewState);
const columns = computed(() => previewPropertyColumns(preview.value, props.store.standard));
const diagnostics = computed(() => splitPreviewDiagnostics(preview.value?.diagnostics ?? []));
const blockingCount = computed(() => diagnostics.value.errors.length);
const jobRunning = computed(() => props.job !== null && !isTerminalJobStatus(props.job.status));
/** 执行中或检查中都不允许重复发起：预览门禁本身由后端摘要决定。 */
const executeDisabled = computed(
  () =>
    !props.store.canExecute ||
    jobRunning.value ||
    props.store.previewPending ||
    props.store.executePending,
);
const dialogGroup = ref<CreationPreviewGroup | null>(null);
const dialogColumn = ref<CreationPreviewPropertyColumn | null>(null);

onMounted(() => {
  // 进入本阶段即请求权威预览：`goToStep` 的保存已使旧摘要失效，这里按需重算
  if (props.store.previewDigest === null && props.store.draftId !== "") void props.store.preview();
});

/** 诊断行：文案与跳转位置一次算好，模板不重复求值也不做非空断言。 */
function diagnosticRows(items: CreationPreviewDiagnostic[]) {
  return items.map((item, index) => ({
    key: `${item.code}-${index}`,
    text: diagnosticText(item.code, item.message),
    target: previewDiagnosticTarget(item, groupOf(item.group_id)),
    index: index + 1,
  }));
}

/** 诊断所属的预览组：仅用于区分两种模板资产（`CREATION_ASSET_INVALID` 共用一个码）。 */
function groupOf(groupId: string): CreationPreviewGroup | null {
  if (groupId === "") return null;
  return preview.value?.groups.find(group => group.group_id === groupId) ?? null;
}
const errorRows = computed(() => diagnosticRows(diagnostics.value.errors));
const noticeRows = computed(() => diagnosticRows(diagnostics.value.notices));

/** 诊断文案：已知码走创建域诊断语言包（与后端 `diagnostics[].code` 一一对应），未知码回退后端文本。 */
function diagnosticText(code: string, message: string): string {
  const key = `creation.diagnostic.${code}`;
  return te(key) ? t(key) : message;
}

/** 编号设置摘要：全部取后端预览的有效配置，前端不重算编号。 */
function numberingText(): string {
  const value = preview.value;
  if (value === null) return "";
  const parts = [
    t("creation.review.numberingValue", {
      field: value.numbering.sequence_field,
      digits: value.numbering.digits,
      start: value.numbering.start,
    }),
    value.suffix.enabled
      ? t("creation.review.suffixOn", {type: value.suffix.suffix_type})
      : t("creation.review.suffixOff"),
    value.suffix.unnumbered_keywords.length === 0
      ? t("creation.review.unnumberedNone")
      : t("creation.review.unnumberedValue", {keywords: value.suffix.unnumbered_keywords.join("、")}),
  ];
  return parts.join(" · ");
}

function cellOf(group: CreationPreviewGroup, propertyId: string) {
  return groupSheetValues(group, propertyId);
}

function openValues(group: CreationPreviewGroup, column: CreationPreviewPropertyColumn): void {
  dialogGroup.value = group;
  dialogColumn.value = column;
}

function closeValues(): void {
  dialogGroup.value = null;
  dialogColumn.value = null;
}

/** 创建前确认：展示最终路径并要求勾选不可覆盖确认；取消不发任何请求。 */
async function confirmAndExecute(): Promise<void> {
  if (executeDisabled.value) return;
  const path = preview.value?.target_path ?? props.store.targetPath();
  const confirmed = await props.confirmAction({
    title: t("creation.review.confirmTitle"),
    message: t("creation.review.confirmMessage"),
    impactLines: [t("creation.review.confirmImpact", {path})],
    confirmText: t("creation.review.confirmConfirm"),
    cancelText: t("creation.review.confirmCancel"),
    danger: true,
    requireCheckbox: true,
    reversibility: "irreversible",
  });
  if (!confirmed) return;
  emit("execute");
}

/**
 * 失败任务的重试：先重新核对有效配置与全部输出（重新检查），通过后再走同一条创建确认。
 * 绝不复用失败前的旧摘要。
 */
async function recheckAndExecute(): Promise<void> {
  if (!(await props.store.preview())) return;
  await confirmAndExecute();
}
</script>
<template>
  <section class="review-step" role="region" :aria-label="$t('creation.review.region')">
    <section class="card">
      <header class="card-head">
        <div>
          <h2>{{ $t("creation.review.title") }}</h2>
          <p>{{ $t("creation.review.lead") }}</p>
        </div>
        <UiButton
          variant="secondary" data-testid="creation-preview-recheck"
          :disabled="store.previewPending || jobRunning || store.draftId === ''"
          @click="store.preview()"
        >
          {{ $t("creation.review.recheck") }}
        </UiButton>
      </header>
      <p v-if="store.previewPending" class="note" role="status" data-testid="creation-preview-loading">
        {{ $t("creation.review.loading") }}
      </p>
      <template v-else-if="preview === null">
        <p class="banner warn" data-testid="creation-preview-stale">
          <strong>{{ $t("creation.review.staleTitle") }}</strong>
          {{ $t("creation.review.staleDesc") }}
        </p>
        <p class="note">{{ $t("creation.review.stalePath", {path: store.targetPath()}) }}</p>
      </template>
      <template v-else>
        <div class="summary-row" data-testid="creation-preview-summary">
          <span class="badge neutral">{{ $t("creation.review.groupsBadge", {count: preview.group_count}) }}</span>
          <span class="badge neutral">{{ $t("creation.review.sheetsBadge", {count: preview.sheet_count}) }}</span>
          <span class="badge neutral">{{ $t("creation.review.dwgBadge", {count: preview.dwg_count}) }}</span>
          <span
            class="badge" :class="blockingCount > 0 ? 'bad' : 'good'" data-testid="creation-preview-status"
          >{{ blockingCount > 0 ? $t("creation.review.statusBlocked", {count: blockingCount}) : $t("creation.review.statusOk") }}</span>
        </div>
        <dl class="preview-context" data-testid="creation-preview-context">
          <div>
            <dt>{{ $t("creation.review.contextStandard") }}</dt>
            <dd>{{ preview.standard_name }} · v{{ preview.standard_version }}（{{ preview.standard_id }}）</dd>
          </div>
          <div>
            <dt>{{ $t("creation.review.contextTarget") }}</dt>
            <dd class="mono">{{ preview.target_path }}</dd>
          </div>
          <div>
            <dt>{{ $t("creation.review.contextNumbering") }}</dt>
            <dd data-testid="creation-preview-numbering">{{ numberingText() }}</dd>
          </div>
        </dl>
        <section
          v-if="errorRows.length > 0" class="diagnostics error"
          data-testid="creation-preview-errors" role="alert"
        >
          <h3>{{ $t("creation.review.errorsTitle", {count: errorRows.length}) }}</h3>
          <ul>
            <li v-for="row in errorRows" :key="row.key">
              <span>{{ row.text }}</span>
              <button
                v-if="row.target !== null" type="button" class="link"
                @click="emit('locate', row.target)"
              >{{ $t("creation.review.jump", {index: row.index}) }}</button>
            </li>
          </ul>
        </section>
        <section
          v-if="noticeRows.length > 0" class="diagnostics notice"
          data-testid="creation-preview-warnings"
        >
          <h3>{{ $t("creation.review.noticesTitle", {count: noticeRows.length}) }}</h3>
          <ul>
            <li v-for="row in noticeRows" :key="row.key">
              <span>{{ row.text }}</span>
              <button
                v-if="row.target !== null" type="button" class="link"
                @click="emit('locate', row.target)"
              >{{ $t("creation.review.jump", {index: row.index}) }}</button>
            </li>
          </ul>
        </section>
        <!-- 主表：一组一行；表宽随内容，容器自身横向滚动，首列保持可见 -->
        <div class="table-scroll">
          <table class="preview-table" data-testid="creation-preview-table" :aria-label="$t('creation.review.tableLabel')">
            <thead>
              <tr>
                <th class="group-col">{{ $t("creation.review.columnGroup") }}</th>
                <th>{{ $t("creation.review.columnRange") }}</th>
                <th>{{ $t("creation.review.columnDrawing") }}</th>
                <th class="count-col">{{ $t("creation.review.columnCount") }}</th>
                <th>{{ $t("creation.review.columnFileName") }}</th>
                <th>{{ $t("creation.review.columnBase") }}</th>
                <th>{{ $t("creation.review.columnLayout") }}</th>
                <th>{{ $t("creation.review.columnPaper") }}</th>
                <th v-for="column in columns" :key="column.property_id">{{ column.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(group, index) in preview.groups" :key="group.group_id"
                :data-group-id="group.group_id"
              >
                <th scope="row" class="group-col">{{ group.title }}</th>
                <td class="mono">{{ group.number_range }}</td>
                <td>{{ group.title_range }}</td>
                <td class="count-col">{{ group.sheet_count }}</td>
                <td class="mono">{{ group.dwg_name }}</td>
                <td>{{ group.base_template }}</td>
                <td>{{ group.layout_template }}</td>
                <td>{{ group.paper_layout }}</td>
                <td
                  v-for="column in columns" :key="column.property_id"
                  :data-property-id="column.property_id"
                >
                  <span v-if="cellOf(group, column.property_id).text !== ''">{{ cellOf(group, column.property_id).text }}</span>
                  <span v-else class="empty">{{ $t("creation.review.emptyValue") }}</span>
                  <button
                    v-if="cellOf(group, column.property_id).showDetails"
                    type="button" class="more"
                    :aria-label="$t('creation.review.moreLabel', {index: index + 1, property: column.label})"
                    @click="openValues(group, column)"
                  >{{ $t("creation.review.moreValues") }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="note">{{ $t("creation.review.tableNote") }}</p>
        <div class="execute-bar">
          <p class="note">{{ $t("creation.review.executeHint") }}</p>
          <UiButton
            variant="primary" data-testid="creation-execute"
            :disabled="executeDisabled" @click="confirmAndExecute"
          >
            {{ $t("creation.review.execute") }}
          </UiButton>
        </div>
      </template>
    </section>
    <section v-if="job !== null" class="card job-card" data-testid="creation-job">
      <h3>{{ $t("creation.review.jobTitle") }}</h3>
      <JobStatusPanel :job="job" :connection-mode="connectionMode" @retry="recheckAndExecute" />
      <p v-if="!jobRunning && job.status !== 'SUCCEEDED'" class="note">
        {{ $t("creation.review.jobFailedNote") }}
      </p>
    </section>
    <SheetValuesDialog
      :open="dialogGroup !== null && dialogColumn !== null"
      :group="dialogGroup" :column="dialogColumn"
      @close="closeValues"
    />
  </section>
</template>
<style scoped>
.review-step{display:grid;gap:var(--space-4);min-width:0}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);display:grid;gap:var(--space-3);min-width:0}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.card-head h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.card-head p{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.note{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.banner{margin:0;padding:var(--space-3);border-radius:var(--radius-md);background:var(--color-info-bg);color:var(--color-text-primary);font-size:var(--font-label)}
.banner.warn{background:var(--color-warning-bg);color:var(--color-text-primary)}
.summary-row{display:flex;gap:var(--space-2);flex-wrap:wrap}
.badge{font-size:var(--font-caption);padding:var(--space-1) var(--space-2);border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary)}
.badge.good{background:var(--color-success-bg);color:var(--color-success)}
.badge.bad{background:var(--color-danger-bg);color:var(--color-danger)}
.preview-context{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,var(--sheet-property-search-width)),1fr));gap:var(--space-3);margin:0}
.preview-context dt{color:var(--color-text-secondary);font-size:var(--font-caption)}
.preview-context dd{margin:var(--space-1) 0 0;color:var(--color-text-primary);font-size:var(--font-label);word-break:break-all}
.diagnostics{padding:var(--space-3);border-radius:var(--radius-md);display:grid;gap:var(--space-2)}
.diagnostics.error{background:var(--color-danger-bg)}
.diagnostics.notice{background:var(--color-warning-bg)}
.diagnostics h3{margin:0;font-size:var(--font-card-title);color:var(--color-text-primary)}
.diagnostics ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.diagnostics li{display:flex;align-items:baseline;gap:var(--space-2);flex-wrap:wrap;font-size:var(--font-label);color:var(--color-text-primary)}
.diagnostics .link{font-size:var(--font-label);padding:var(--space-1) var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer}
/* 表宽随内容，容器自身横向滚动：900×768 下页面整体不横溢 */
.table-scroll{overflow-x:auto;min-width:0}
.preview-table{width:100%;min-width:max-content;border-collapse:collapse}
.preview-table th,.preview-table td{height:var(--sheet-table-row-height);padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;vertical-align:middle}
.preview-table thead th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500;white-space:nowrap;vertical-align:middle}
.preview-table tbody th,.preview-table tbody td{font-size:var(--font-label);color:var(--color-text-primary);vertical-align:middle}
/* 张数：可比较数值列右对齐并启用 tabular-nums，表头跟随列数据（SPEC-DM-006 §6.4） */
.preview-table .count-col{text-align:right;font-variant-numeric:tabular-nums;vertical-align:middle}
/* 首列（图纸组）固定在最左：横向滚动时组名始终可见 */
.group-col{position:sticky;left:0;z-index:1;background:var(--color-bg-surface);min-width:var(--sheet-title-max-width)}
.empty{color:var(--color-text-muted)}
.more{margin-left:var(--space-1);padding:0 var(--space-1);border:0;background:none;color:var(--color-accent);font-size:var(--font-label);cursor:pointer}
.more:hover{text-decoration:underline}
.execute-bar{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.job-card h3{margin:0;font-size:var(--font-card-title);color:var(--color-text-primary)}
</style>
