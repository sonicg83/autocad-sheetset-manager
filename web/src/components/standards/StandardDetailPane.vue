<script setup lang="ts">
// 标准详情右栏（PLAN-DM-035 Task 8）：身份、能力摘要、版本历史与动作。
// 只读边界不隐藏动作——禁用并显示可见原因（detailActions.readOnlyReason）。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import {detailActions, versionHistory} from "./standardLibraryModel";
import type {StandardDetail, StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  summary: StandardSummary | null;
  detail: StandardDetail | null;
  detailPending: boolean;
  detailError: string;
  items: StandardSummary[];
}>();
const emit = defineEmits<{
  derive: [];
  exportStandard: [];
  deleteDraft: [];
  edit: [];
  useForCreate: [];
  openVersion: [version: string];
}>();

const actions = computed(() => (props.summary === null ? null : detailActions(props.summary)));
const versions = computed(() =>
  props.summary === null ? [] : versionHistory(props.summary, props.items),
);
const documentCounts = computed(() => {
  const document = props.detail?.document;
  if (!document) return null;
  const count = (value: unknown): number => (Array.isArray(value) ? value.length : 0);
  return {
    properties: count(document["properties"]),
    rules: count(document["rules"]),
    assets: count(document["assets"]),
  };
});
</script>
<template>
  <section class="detail-pane" role="region" :aria-label="$t('standards.detail.region')">
    <p v-if="summary === null" class="detail-note">{{ $t("standards.detail.empty") }}</p>
    <template v-else>
      <h3 class="detail-title">{{ summary.name }}</h3>
      <p v-if="actions?.readOnlyReason" class="detail-reason" role="note">
        {{ $t(actions.readOnlyReason === "official" ? "standards.detail.readOnlyOfficial" : "standards.detail.readOnlyPublished") }}
      </p>
      <dl class="detail-identity">
        <div><dt>{{ $t("standards.detail.standardId") }}</dt><dd>{{ summary.standard_id }}</dd></div>
        <div v-if="summary.status === 'published'">
          <dt>{{ $t("standards.detail.version") }}</dt><dd>{{ summary.version }}</dd>
        </div>
        <div>
          <dt>{{ $t("standards.detail.status") }}</dt>
          <dd>{{ $t(summary.status === "draft" ? "standards.library.statusDraft" : "standards.library.statusPublished") }}</dd>
        </div>
        <div>
          <dt>{{ $t("standards.detail.source") }}</dt>
          <dd>{{ $t(summary.source === "official" ? "standards.library.sourceOfficial" : "standards.library.sourceUser") }}</dd>
        </div>
      </dl>
      <p v-if="detailPending" class="detail-note" role="status">{{ $t("standards.detail.loading") }}</p>
      <p v-else-if="detailError" class="detail-note error" role="alert">{{ detailError }}</p>
      <template v-else-if="detail">
        <div v-if="documentCounts" class="detail-counts">
          <span>{{ $t("standards.detail.propertiesCount", {count: documentCounts.properties}) }}</span>
          <span>{{ $t("standards.detail.rulesCount", {count: documentCounts.rules}) }}</span>
          <span>{{ $t("standards.detail.assetsCount", {count: documentCounts.assets}) }}</span>
        </div>
        <div v-if="detail.dependencies.length > 0" class="detail-dependencies">
          <h4>{{ $t("standards.detail.dependencies") }}</h4>
          <ul>
            <li v-for="dependency in detail.dependencies" :key="dependency.capability_id">
              {{ dependency.extension_id }} / {{ dependency.capability_id }} ≥ {{ dependency.min_version }}
            </li>
          </ul>
        </div>
      </template>
      <div v-if="versions.length > 0" class="detail-versions">
        <h4>{{ $t("standards.detail.versionHistory") }}</h4>
        <ul>
          <li v-for="entry in versions" :key="entry.version">
            <button type="button" class="version-link" @click="emit('openVersion', entry.version)">
              v{{ entry.version }} · {{ $t(entry.source === "official" ? "standards.library.sourceOfficial" : "standards.library.sourceUser") }}
            </button>
          </li>
        </ul>
      </div>
      <div class="detail-actions">
        <UiButton
          v-if="actions?.canEdit"
          variant="secondary"
          @click="emit('edit')"
        >{{ $t("standards.detail.edit") }}</UiButton>
        <UiButton v-if="actions?.canDerive" variant="secondary" @click="emit('derive')">{{ $t("standards.detail.derive") }}</UiButton>
        <UiButton v-if="actions?.canExport" variant="secondary" @click="emit('exportStandard')">{{ $t("standards.detail.export") }}</UiButton>
        <UiButton v-if="actions?.canExport" variant="secondary" @click="emit('useForCreate')">{{ $t("standards.detail.useForCreate") }}</UiButton>
        <UiButton v-if="actions?.canDelete" variant="secondary" @click="emit('deleteDraft')">{{ $t("standards.detail.delete") }}</UiButton>
      </div>
    </template>
  </section>
</template>
<style scoped>
.detail-pane{display:grid;gap:var(--space-3);align-content:start;min-width:0}
.detail-note{color:var(--color-text-secondary);font-size:var(--font-label);margin:0}
.detail-note.error{color:var(--color-danger)}
.detail-title{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.detail-reason{margin:0;font-size:var(--font-label);color:var(--color-text-secondary);border:1px dashed var(--color-border-strong);border-radius:var(--radius-md);padding:var(--space-2)}
.detail-identity{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2);margin:0}
.detail-identity dt{font-size:var(--font-label);color:var(--color-text-secondary)}
.detail-identity dd{margin:0;color:var(--color-text-primary);word-break:break-all}
.detail-counts{display:flex;gap:var(--space-3);font-size:var(--font-label);color:var(--color-text-secondary)}
.detail-dependencies h4,.detail-versions h4{margin:0 0 var(--space-1);font-size:var(--font-label);color:var(--color-text-secondary)}
.detail-dependencies ul,.detail-versions ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);font-size:var(--font-label)}
.version-link{background:none;border:none;padding:0;color:var(--color-accent);cursor:pointer;font-size:var(--font-label)}
.detail-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
</style>
