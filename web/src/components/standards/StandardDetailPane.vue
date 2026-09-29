<script setup lang="ts">
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import {detailActions, formatPublishedAt} from "./standardLibraryModel";
import type {StandardDetail, StandardIdentity, StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  summary: StandardSummary | null;
  detail: StandardDetail | null;
  detailPending: boolean;
  detailError: string;
  deleteImpactCount?: number | null;
  deleteNotice?: string;
  narrow?: boolean;
}>();
const emit = defineEmits<{
  derive: [];
  exportStandard: [];
  deleteDraft: [];
  deleteStandard: [];
  edit: [];
  useForCreate: [identity: StandardIdentity];
  retry: [];
  backToList: [];
}>();
const {t} = useI18n();
const copied = ref(false);

const actions = computed(() => (props.summary === null ? null : detailActions(props.summary)));
const createIdentity = computed<StandardIdentity | null>(() => {
  const summary = props.summary;
  if (summary === null || summary.status !== "published" || summary.published_at === null) return null;
  return {standardId: summary.standard_id};
});
const documentCounts = computed(() => {
  const document = props.detail?.document;
  if (!document) return null;
  const count = (value: unknown): number => (Array.isArray(value) ? value.length : 0);
  const properties = Array.isArray(document["properties"]) ? document["properties"] : [];
  const ordinary = properties.filter(item => {
    const kind = (item as {kind?: string}).kind;
    return kind === "text" || kind === "enum";
  }).length;
  return {ordinary, derived: properties.length - ordinary, assets: count(document["assets"])};
});

async function copyStandardId(): Promise<void> {
  const standardId = props.summary?.standard_id;
  if (!standardId || !navigator.clipboard) return;
  try {
    await navigator.clipboard.writeText(standardId);
    copied.value = true;
    window.setTimeout(() => {copied.value = false;}, 1600);
  } catch {
    copied.value = false;
  }
}
</script>
<template>
  <section class="detail-pane" role="region" :aria-label="$t('standards.detail.region')">
    <p v-if="summary === null" class="detail-note">{{ $t("standards.detail.empty") }}</p>
    <template v-else>
      <UiButton
        v-if="narrow === true"
        variant="secondary"
        data-testid="back-to-list"
        @click="emit('backToList')"
      >{{ $t("standards.detail.backToList") }}</UiButton>
      <h3 class="detail-title">{{ summary.name }}</h3>
      <p v-if="actions?.readOnlyReason" class="detail-reason" role="note">
        {{ $t(actions.readOnlyReason === "official" ? "standards.detail.readOnlyOfficial" : "standards.detail.readOnlyPublished") }}
      </p>
      <section class="detail-section">
        <h4>{{ $t("standards.detail.basics") }}</h4>
        <dl class="detail-identity">
          <div class="identity-id">
            <dt>{{ $t("standards.detail.standardId") }}</dt>
            <dd>{{ summary.standard_id }}
              <UiButton variant="secondary" class="copy-id" :aria-label="$t('standards.detail.copyId')" @click="copyStandardId">
                {{ copied ? $t("standards.detail.copied") : $t("standards.detail.copyId") }}
              </UiButton>
            </dd>
          </div>
          <div>
            <dt>{{ $t("standards.detail.status") }}</dt>
            <dd>{{ $t(summary.status === "draft" ? "standards.library.statusDraft" : "standards.library.statusPublished") }}</dd>
          </div>
          <div>
            <dt>{{ $t("standards.detail.source") }}</dt>
            <dd>{{ $t(summary.source === "official" ? "standards.library.sourceOfficial" : "standards.library.sourceUser") }}</dd>
          </div>
          <div v-if="summary.status === 'published'">
            <dt>{{ $t("standards.detail.publishedAt") }}</dt>
            <dd>{{ formatPublishedAt(summary.published_at) ?? $t("standards.library.noPublishedAt") }}</dd>
          </div>
        </dl>
        <p v-if="copied" class="copy-status" role="status">{{ $t("standards.detail.copied") }}</p>
      </section>
      <section class="detail-section detail-overview">
        <h4>{{ $t("standards.detail.overview") }}</h4>
        <p>{{ summary.description || $t("standards.library.noDescription") }}</p>
      </section>
      <p v-if="detailPending" class="detail-note" role="status">{{ $t("standards.detail.loading") }}</p>
      <template v-else-if="detailError">
        <p class="detail-note error" role="alert" data-testid="detail-error">{{ detailError }}</p>
        <UiButton v-if="summary.status === 'published'" variant="secondary" :disabled="detailPending" @click="emit('retry')">
          {{ $t("standards.detail.retry") }}
        </UiButton>
      </template>
      <template v-else-if="detail">
        <section v-if="documentCounts" class="detail-section">
          <h4>{{ $t("standards.detail.contents") }}</h4>
          <div class="detail-counts">
            <span>{{ $t("standards.detail.ordinaryCount", {count: documentCounts.ordinary}) }}</span>
            <span>{{ $t("standards.detail.derivedCount", {count: documentCounts.derived}) }}</span>
            <span>{{ $t("standards.detail.assetsCount", {count: documentCounts.assets}) }}</span>
          </div>
        </section>
        <section v-if="detail.dependencies.length > 0" class="detail-section detail-dependencies">
          <h4>{{ $t("standards.detail.dependencies") }}</h4>
          <ul>
            <li v-for="dependency in detail.dependencies" :key="dependency.capability_id">
              {{ dependency.extension_id }} / {{ dependency.capability_id }} ≥ {{ dependency.min_version }}
            </li>
          </ul>
        </section>
      </template>
      <p v-if="deleteImpactCount !== null && deleteImpactCount !== undefined" class="delete-impact" role="status">
        {{ $t("standards.delete.impactCount", {count: deleteImpactCount}) }}
      </p>
      <p v-if="deleteNotice" class="detail-note error" role="alert" data-testid="standard-delete-notice">{{ deleteNotice }}</p>
      <div class="detail-actions">
        <UiButton v-if="actions?.canEdit" variant="secondary" @click="emit('edit')">{{ $t("standards.detail.edit") }}</UiButton>
        <UiButton v-if="actions?.canDerive" variant="secondary" @click="emit('derive')">{{ $t("standards.detail.derive") }}</UiButton>
        <UiButton v-if="actions?.canExport" variant="secondary" @click="emit('exportStandard')">{{ $t("standards.detail.export") }}</UiButton>
        <UiButton v-if="createIdentity !== null" variant="secondary" @click="emit('useForCreate', createIdentity)">{{ $t("standards.detail.useForCreate") }}</UiButton>
        <UiButton v-if="actions?.canDelete && summary.status === 'draft'" variant="secondary" @click="emit('deleteDraft')">{{ $t("standards.detail.delete") }}</UiButton>
        <UiButton v-if="actions?.canDelete && summary.status === 'published'" variant="secondary" @click="emit('deleteStandard')">{{ $t("standards.detail.delete") }}</UiButton>
      </div>
    </template>
  </section>
</template>
<style scoped>
.detail-pane{display:grid;gap:var(--space-3);align-content:start;min-width:0;min-height:0;overflow:auto}
.detail-title{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.detail-note{color:var(--color-text-secondary);font-size:var(--font-label);margin:0}
.detail-note.error{color:var(--color-danger)}
.detail-reason{margin:0;font-size:var(--font-label);color:var(--color-text-secondary);border:1px dashed var(--color-border-strong);border-radius:var(--radius-md);padding:var(--space-2)}
.detail-section{display:grid;gap:var(--space-2);min-width:0}
.detail-section h4{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.detail-section p{margin:0;color:var(--color-text-primary);font-size:var(--font-label);line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.detail-identity{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2);margin:0}
.detail-identity dt{font-size:var(--font-caption);color:var(--color-text-secondary)}
.detail-identity dd{display:flex;align-items:center;gap:var(--space-2);margin:0;color:var(--color-text-primary);overflow-wrap:anywhere}
.detail-identity .identity-id{grid-column:1/-1}
.copy-id{flex:none;font-size:var(--font-caption);padding:var(--space-1) var(--space-2)}
.copy-status{margin:0;color:var(--color-success);font-size:var(--font-caption)}
.detail-counts{display:flex;gap:var(--space-3);font-size:var(--font-label);color:var(--color-text-secondary);flex-wrap:wrap}
.detail-dependencies ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);font-size:var(--font-label)}
.delete-impact{margin:0;color:var(--color-text-secondary);font-size:var(--font-label)}
.detail-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
</style>
