<script setup lang="ts">
// 发布检查页（PLAN-DM-035 Task 10 / SPEC-DM-016 §9.1–§9.2）：独立检查页，不使用小型确认对话框。
// 左侧列出检查域及错误/警告计数，右侧列出问题、修复入口、版本号、版本说明与发布动作。
// 错误阻止发布，警告允许发布并在发布动作附近汇总；每个问题均可返回对应编辑分区并聚焦到
// 字段、映射行或资产；检查本身失败单独呈现，不误报为「标准存在错误」。
// 版本号只读：草稿身份在创建时确定（`PUT /api/standards/{id}/{ver}` 按文档内身份查找草稿），
// 需要新版本应从已发布版本派生新草稿。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import {
  buildPublishGate,
  PUBLISH_SECTIONS,
  type PublishIssue,
  type PublishTarget,
  type InspectionFailure,
} from "../../features/standards/publishModel";
import type {DraftDocument, EditorSectionId} from "../../features/standards/draftModel";
import type {AssetInspection} from "../../features/standards/types";

const props = defineProps<{
  document: DraftDocument;
  assets: AssetInspection[];
  inspectionFailures: InspectionFailure[];
  inspectionPending: boolean;
  publishPending: boolean;
  publishError: string;
  releaseNotes: string;
}>();
const emit = defineEmits<{
  publish: [];
  close: [];
  recheck: [];
  jump: [target: PublishTarget];
  "update:releaseNotes": [value: string];
}>();

const sectionLabelKeys: Record<EditorSectionId, string> = {
  basic: "standards.sections.basic",
  ordinary: "standards.sections.ordinary",
  derived: "standards.sections.derived",
  dwgNaming: "standards.sections.dwgNaming",
  assets: "standards.sections.assets",
  publish: "standards.sections.publish",
};

const gate = computed(() => buildPublishGate({
  document: props.document,
  assets: props.assets,
  inspectionFailures: props.inspectionFailures,
}));

const issues = computed<PublishIssue[]>(() => [...gate.value.blockingErrors, ...gate.value.warnings]);

function issuesOf(section: EditorSectionId): PublishIssue[] {
  return issues.value.filter(issue => issue.target.section === section);
}

function errorsOf(section: EditorSectionId): number {
  return issuesOf(section).filter(issue => issue.severity === "error").length;
}

function warningsOf(section: EditorSectionId): number {
  return issuesOf(section).filter(issue => issue.severity === "warning").length;
}

/** 问题定位文本：只显示用户可读的名称（属性名、源枚举显示值、令牌序号），不显示内部 ID。 */
function locationOf(issue: PublishIssue): string {
  if (issue.target.layout !== undefined) return issue.target.layout;
  if (issue.target.assetId !== undefined) return issue.target.assetId;
  if (issue.target.segmentIndex !== undefined) {
    return String(issue.target.segmentIndex + 1);
  }
  if (issue.target.propertyId !== undefined) {
    const property = props.document.properties.find(item => item.property_id === issue.target.propertyId);
    if (property === undefined) return "";
    if (issue.target.itemId === undefined) return property.name || property.property_id;
    const source = props.document.properties.find(
      item => item.property_id === (property.kind === "mapping" ? property.source_property_id : ""),
    );
    const item = source !== undefined && source.kind === "enum"
      ? source.enum_items.find(candidate => candidate.item_id === issue.target.itemId)
      : undefined;
    return item === undefined
      ? property.name || property.property_id
      : `${property.name || property.property_id} · ${item.value}`;
  }
  return "";
}

function addNote(value: unknown): void {
  emit("update:releaseNotes", String(value));
}
</script>
<template>
  <section class="publish-review" role="region" :aria-label="$t('standards.publish.title')" data-testid="publish-review">    <header class="review-header">
      <div>
        <h3 class="review-title">{{ $t("standards.publish.title") }}</h3>
        <p class="review-hint">{{ $t("standards.publish.hint") }}</p>
      </div>
      <UiButton variant="secondary" @click="emit('close')">{{ $t("standards.publish.back") }}</UiButton>
    </header>
    <div class="review-split">
      <div class="domain-column">
        <h4 class="block-title">{{ $t("standards.publish.domains") }}</h4>
        <ul class="domain-list">
          <li v-for="section in PUBLISH_SECTIONS" :key="section" class="domain-row" :data-testid="`publish-domain-${section}`">
            <span>{{ $t(sectionLabelKeys[section]) }}</span>
            <span class="domain-counts" :class="{blocked: errorsOf(section) > 0}">
              {{ $t("standards.publish.domainCounts", {errors: errorsOf(section), warnings: warningsOf(section)}) }}
            </span>
          </li>
        </ul>
        <div class="counts" role="status">
          <span class="count error">{{ $t("standards.publish.countErrors", {count: gate.counts.errors}) }}</span>
          <span class="count warning">{{ $t("standards.publish.countWarnings", {count: gate.counts.warnings}) }}</span>
          <span class="count">{{ $t("standards.publish.countFailures", {count: gate.counts.failures}) }}</span>
        </div>
      </div>
      <div class="issue-column">
        <h4 class="block-title">{{ $t("standards.publish.issues") }}</h4>
        <p v-if="inspectionPending" class="review-note" role="status">{{ $t("standards.publish.inspecting") }}</p>
        <template v-else>
          <p v-if="issues.length === 0 && gate.inspectionFailures.length === 0" class="review-note" role="status">
            {{ $t("standards.publish.noIssues") }}
          </p>
          <ol v-if="issues.length > 0" class="issue-list">
            <li v-for="(issue, index) in issues" :key="index" class="issue-row" :class="issue.severity">
              <div class="issue-text">
                <span class="issue-flag">{{ $t(issue.severity === "error" ? "standards.publish.errors" : "standards.publish.warnings") }}</span>
                <span class="issue-message">{{ $t(`standards.diagnostic.${issue.code}`, issue.params) }}</span>
                <span v-if="locationOf(issue)" class="issue-location">{{ locationOf(issue) }}</span>
              </div>
              <button
                type="button"
                class="issue-jump"
                :data-testid="`publish-issue-${index}`"
                @click="emit('jump', issue.target)"
              >{{ $t("standards.publish.issueJump") }} · {{ $t(sectionLabelKeys[issue.target.section]) }}</button>
            </li>
          </ol>
          <div v-if="gate.inspectionFailures.length > 0" class="failure-block">
            <h5 class="block-title">{{ $t("standards.publish.inspectionFailedTitle") }}</h5>
            <ul class="issue-list">
              <li v-for="failure in gate.inspectionFailures" :key="failure.assetId" class="issue-row error">
                <div class="issue-text">
                  <span class="issue-message">{{ failure.assetId }}</span>
                  <span class="issue-location">{{ failure.message }}</span>
                </div>
              </li>
            </ul>
            <UiButton variant="secondary" @click="emit('recheck')">{{ $t("standards.publish.recheck") }}</UiButton>
          </div>
        </template>
        <div class="release-block">
          <p class="review-note" data-testid="publish-version">{{ $t("standards.publish.versionLabel") }}：{{ document.version }}</p>
          <p class="review-note">{{ $t("standards.publish.versionHint") }}</p>
          <label class="field-label" for="publish-release-notes">{{ $t("standards.publish.releaseNotes") }}</label>
          <textarea
            id="publish-release-notes"
            class="notes-input"
            rows="3"
            :value="releaseNotes"
            @input="addNote(($event.target as HTMLTextAreaElement).value)"
          />
          <p class="review-note">{{ $t("standards.publish.releaseNotesHint") }}</p>
        </div>
        <div class="dependency-block">
          <h5 class="block-title">{{ $t("standards.publish.dependencies") }}</h5>
          <ul v-if="document.dependencies.length > 0" class="dependency-list">
            <li v-for="dependency in document.dependencies" :key="dependency.capability_id">
              {{ dependency.extension_id }} / {{ dependency.capability_id }} ≥ {{ dependency.min_version }}
            </li>
          </ul>
          <p v-else class="review-note">{{ $t("standards.publish.noDependencies") }}</p>
          <p class="review-note">{{ $t("standards.publish.dependencyNote") }}</p>
        </div>
        <p v-if="publishError" class="publish-error" role="alert" data-testid="publish-error">
          {{ $t("standards.publish.publishFailed", {message: publishError}) }}
        </p>
        <div class="publish-actions">
          <UiButton variant="secondary" :loading="publishPending" :disabled="!gate.canPublish" @click="emit('publish')">
            {{ $t(publishPending ? "standards.publish.publishing" : "standards.publish.publish") }}
          </UiButton>
          <span v-if="!gate.canPublish" class="review-note" role="status">{{ $t("standards.publish.blocked") }}</span>
          <span v-else-if="gate.counts.warnings > 0" class="review-note" role="status">
            {{ $t("standards.publish.warningSummary", {count: gate.counts.warnings}) }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.publish-review{display:grid;gap:var(--space-3);min-width:0}
.review-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.review-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.review-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.review-split{display:grid;grid-template-columns:minmax(200px,260px) minmax(0,1fr);gap:var(--space-4);align-items:start}
.domain-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.domain-row{display:grid;gap:var(--space-1);padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);font-size:var(--font-label);color:var(--color-text-primary)}
.domain-counts{color:var(--color-text-secondary)}
.domain-counts.blocked{color:var(--color-danger)}
.counts{display:flex;gap:var(--space-2);flex-wrap:wrap;margin-top:var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.count.error{color:var(--color-danger)}
.count.warning{color:var(--color-warning)}
.block-title{margin:0 0 var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary)}
.issue-column{display:grid;gap:var(--space-3);min-width:0}
.review-note{margin:0;font-size:var(--font-label);color:var(--color-text-muted)}
.issue-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2)}
.issue-row{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-2);padding:var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);flex-wrap:wrap}
.issue-row.error{border-color:var(--color-danger)}
.issue-row.warning{border-color:var(--color-warning)}
.issue-text{display:grid;gap:var(--space-1);min-width:0}
.issue-flag{font-size:var(--font-caption);color:var(--color-text-secondary)}
.issue-message{color:var(--color-text-primary)}
.issue-location{font-size:var(--font-label);color:var(--color-text-secondary);word-break:break-all}
.issue-jump{min-height:var(--min-tap-height);padding:var(--space-1) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:var(--font-label)}
.failure-block{display:grid;gap:var(--space-2)}
.release-block,.dependency-block{display:grid;gap:var(--space-1);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.notes-input{width:100%;box-sizing:border-box;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:var(--space-2);font-family:var(--font-ui);font-size:var(--input-font-size);background:var(--color-bg-surface);color:var(--color-text-primary)}
.dependency-list{margin:0;padding-left:var(--space-4);font-size:var(--font-label);color:var(--color-text-primary);word-break:break-all}
.publish-error{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.publish-actions{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
@media (max-width: 959px){
  .review-split{grid-template-columns:minmax(0,1fr)}
}
</style>
