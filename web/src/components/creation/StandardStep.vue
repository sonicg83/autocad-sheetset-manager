<script setup lang="ts">
// 第一阶段：选择已发布标准（SPEC-DM-018 §2.1–§2.2；PLAN-DM-036 Task 8）。
// 只列**已发布且依赖、模板资产可用**的候选；一个可用候选都没有时集中说明不可用原因，
// 并给出前往标准库的入口（不提供无标准创建）。标准草稿不在此列表内——候选端点只返回
// 已发布版本。本组件只发事件，草稿建立与切换确认由向导编排。
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import type {CreationStandardCandidate} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{store: CreationStore}>();
const emit = defineEmits<{
  use: [candidate: CreationStandardCandidate];
  openStandards: [];
}>();
const {t} = useI18n();

const available = computed(() => props.store.candidates.filter(item => item.available));
/** 不可用原因按去重后集中呈现：每个候选自己的原因在列表外逐条说明，不静默隐藏候选。 */
const unavailableReasons = computed(() => [
  ...new Set(props.store.candidates.flatMap(item => item.reasons)),
]);
const focusedKey = ref("");

/** 详情面板：优先显示最近指向的候选，否则显示当前草稿固定的标准，再次是首个候选。 */
const preview = computed<CreationStandardCandidate | null>(() => {
  const focused = available.value.find(item => keyOf(item) === focusedKey.value);
  if (focused !== undefined) return focused;
  const fixed = props.store.standard?.identity;
  if (fixed !== undefined && fixed !== null) {
    const current = available.value.find(
      item => item.standard_id === fixed.standardId && item.version === fixed.version,
    );
    if (current !== undefined) return current;
  }
  return available.value[0] ?? null;
});
const isFixed = computed(() => {
  const fixed = props.store.standard?.identity;
  const candidate = preview.value;
  return (
    fixed !== undefined &&
    fixed !== null &&
    candidate !== null &&
    fixed.standardId === candidate.standard_id &&
    fixed.version === candidate.version
  );
});
const counts = computed(() => {
  const standard = props.store.standard;
  const options = standard?.asset_options ?? [];
  return {
    sheetset: standard?.sheetset_properties.length ?? 0,
    sheet: standard?.sheet_properties.length ?? 0,
    derived: standard?.derived_properties.length ?? 0,
    base: options.filter(item => item.kind === "base-template").length,
    layout: options.filter(item => item.kind === "layout-template").length,
  };
});

function keyOf(candidate: CreationStandardCandidate): string {
  return `${candidate.standard_id}@${candidate.version}`;
}
</script>
<template>
  <section class="standard-step" role="region" :aria-label="$t('creation.standard.region')">
    <section class="card">
      <header class="card-head">
        <h2>{{ $t("creation.standard.title") }}</h2>
        <p>{{ $t("creation.standard.lead") }}</p>
      </header>
      <p v-if="store.candidatesPending" class="note" role="status">{{ $t("creation.standard.loading") }}</p>
      <p v-else-if="store.candidatesError" class="note error" role="alert">
        {{ $t("creation.standard.listError", {message: store.candidatesError}) }}
      </p>
      <template v-else-if="available.length > 0">
        <ul class="candidate-list" data-testid="creation-standard-list">
          <li v-for="candidate in available" :key="keyOf(candidate)">
            <button
              type="button" class="candidate" :class="{'is-fixed': isFixed && preview !== null && keyOf(preview) === keyOf(candidate)}"
              @click="focusedKey = keyOf(candidate); emit('use', candidate)"
              @mouseenter="focusedKey = keyOf(candidate)"
              @focus="focusedKey = keyOf(candidate)"
            >
              <strong>{{ candidate.name }}</strong>
              <small>{{ candidate.standard_id }} · v{{ candidate.version }}</small>
              <span class="badge">{{ $t("creation.standard.available") }}</span>
            </button>
          </li>
        </ul>
      </template>
      <div v-else class="empty" role="status">
        <p>{{ $t("creation.standard.empty") }}</p>
        <ul v-if="unavailableReasons.length > 0" class="reasons">
          <li v-for="reason in unavailableReasons" :key="reason">{{ reason }}</li>
        </ul>
        <UiButton variant="secondary" @click="emit('openStandards')">
          {{ $t("creation.standard.emptyAction") }}
        </UiButton>
      </div>
    </section>
    <section class="card" data-testid="creation-standard-detail">
      <header class="card-head">
        <h2>{{ $t("creation.standard.detailTitle") }}</h2>
        <p>{{ $t("creation.standard.detailLead") }}</p>
      </header>
      <p v-if="preview === null" class="note">{{ $t("creation.standard.detailEmpty") }}</p>
      <template v-else>
        <h3 class="detail-name">{{ preview.name }}</h3>
        <dl class="identity">
          <div>
            <dt>{{ $t("creation.standard.version") }}</dt>
            <dd>{{ preview.standard_id }} · v{{ preview.version }}</dd>
          </div>
          <div>
            <dt>{{ $t("creation.standard.cadVersions") }}</dt>
            <dd>{{ preview.supported_cad_versions.join(" / ") }}</dd>
          </div>
        </dl>
        <ul class="counts">
          <li>{{ $t("creation.standard.properties", {sheetset: counts.sheetset, sheet: counts.sheet}) }}</li>
          <li>{{ $t("creation.standard.templates", {base: counts.base, layout: counts.layout}) }}</li>
          <li>{{ $t("creation.standard.derived", {count: counts.derived}) }}</li>
        </ul>
        <p v-if="isFixed" class="note">{{ $t("creation.standard.selected") }}</p>
      </template>
    </section>
  </section>
</template>
<style scoped>
.standard-step{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:var(--space-4);align-items:start}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);display:grid;gap:var(--space-3)}
.card-head h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.card-head p{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.note{margin:0;color:var(--color-text-secondary);font-size:var(--font-label)}
.note.error{color:var(--color-danger)}
.candidate-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2)}
.candidate{width:100%;display:grid;gap:var(--space-1);text-align:left;padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-family:var(--font-ui)}
.candidate:hover{border-color:var(--color-accent);background:var(--color-bg-muted)}
.candidate.is-fixed{border-color:var(--color-accent)}
.candidate strong{font-size:var(--font-label);font-weight:500}
.candidate small{color:var(--color-text-secondary);font-family:var(--font-mono);font-size:var(--font-caption)}
.badge{justify-self:start;font-size:var(--font-caption);padding:2px var(--space-2);border-radius:var(--radius-full);color:var(--color-success);background:var(--color-success-bg)}
.empty{display:grid;gap:var(--space-3);justify-items:start}
.empty p{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.7}
.reasons{margin:0;padding-left:var(--space-5);color:var(--color-text-muted);font-size:var(--font-caption);line-height:1.7;display:grid;gap:var(--space-1)}
.detail-name{margin:0;font-size:var(--font-panel-title);color:var(--color-text-primary)}
.identity{display:grid;gap:var(--space-2);margin:0}
.identity dt{color:var(--color-text-secondary);font-size:var(--font-caption)}
.identity dd{margin:0;color:var(--color-text-primary);font-family:var(--font-mono);font-size:var(--font-label);word-break:break-all}
.counts{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
@media (max-width: 900px){
  .standard-step{grid-template-columns:minmax(0,1fr)}
}
</style>
