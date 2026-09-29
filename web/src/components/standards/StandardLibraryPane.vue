<script setup lang="ts">
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import {buildLibraryState, formatPublishedAt, type StandardFilters} from "./standardLibraryModel";
import {draftKey} from "../../features/standards/draftModel";
import type {StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  items: StandardSummary[];
  filters: StandardFilters;
  selectedKey: string | null;
  listPending: boolean;
  listError: string;
}>();
const emit = defineEmits<{
  select: [summary: StandardSummary];
  updateFilters: [filters: StandardFilters];
  retry: [];
  clearFilters: [];
}>();
const {t} = useI18n();

const state = computed(() => buildLibraryState(props.items, props.filters));

function update(partial: Partial<StandardFilters>): void {
  emit("updateFilters", {...props.filters, ...partial});
}

function description(item: StandardSummary): string {
  return item.description.trim() === "" ? t("standards.library.noDescription") : item.description;
}
</script>
<template>
  <section class="library-pane" role="region" :aria-label="$t('standards.library.region')">
    <div class="library-toolbar">
      <UiInput
        :model-value="filters.query"
        :label="$t('standards.library.searchLabel')"
        :placeholder="$t('standards.library.searchPlaceholder')"
        @update:model-value="update({query: String($event)})"
      />
      <UiSelect
        :model-value="filters.source"
        :label="$t('standards.library.sourceLabel')"
        @update:model-value="update({source: ($event as StandardFilters['source'])})"
      >
        <option value="all">{{ $t("standards.library.sourceAll") }}</option>
        <option value="official">{{ $t("standards.library.sourceOfficial") }}</option>
        <option value="user">{{ $t("standards.library.sourceUser") }}</option>
      </UiSelect>
      <UiSelect
        :model-value="filters.status"
        :label="$t('standards.library.statusLabel')"
        @update:model-value="update({status: ($event as StandardFilters['status'])})"
      >
        <option value="all">{{ $t("standards.library.statusAll") }}</option>
        <option value="published">{{ $t("standards.library.statusPublished") }}</option>
        <option value="draft">{{ $t("standards.library.statusDraft") }}</option>
      </UiSelect>
    </div>
    <p v-if="listPending" class="library-status" role="status">{{ $t("standards.library.loading") }}</p>
    <template v-else-if="listError">
      <p class="library-status error" role="alert">{{ $t("standards.library.loadFailed", {message: listError}) }}</p>
      <UiButton variant="secondary" :disabled="listPending" @click="emit('retry')">
        {{ $t("standards.library.retry") }}
      </UiButton>
    </template>
    <p v-else-if="state.kind==='empty-library'" class="library-status">{{ $t("standards.library.empty") }}</p>
    <template v-else-if="state.kind==='empty-filter'">
      <p class="library-status">{{ $t("standards.library.noMatch") }}</p>
      <UiButton variant="secondary" @click="emit('clearFilters')">
        {{ $t("standards.library.clearFilters") }}
      </UiButton>
    </template>
    <ul v-else class="library-list" data-testid="library-list">
      <li v-for="item in state.items" :key="draftKey(item)">
        <button
          type="button"
          class="library-item"
          data-testid="library-item"
          :class="{selected: selectedKey===draftKey(item)}"
          :aria-label="$t('standards.library.itemAccessible', {
            name: item.name,
            source: $t(item.source==='official' ? 'standards.library.sourceOfficial' : 'standards.library.sourceUser'),
            status: $t(item.status==='draft' ? 'standards.library.statusDraft' : 'standards.library.statusPublished'),
            description: description(item),
            publishedAt: item.status==='published' ? (formatPublishedAt(item.published_at) ?? $t('standards.library.noPublishedAt')) : '',
          })"
          @click="emit('select', item)"
        >
          <span class="library-heading">
            <span class="library-name">{{ item.name }}</span>
            <span class="library-meta">
              <span class="badge" :class="item.source">{{ $t(item.source==='official' ? 'standards.library.sourceOfficialBadge' : 'standards.library.sourceUserBadge') }}</span>
              <span class="badge" :class="item.status">{{ $t(item.status==='draft' ? 'standards.library.statusDraftBadge' : 'standards.library.statusPublishedBadge') }}</span>
            </span>
          </span>
          <span class="library-description" :title="description(item)">{{ description(item) }}</span>
          <time v-if="item.status==='published'" class="library-time">
            {{ formatPublishedAt(item.published_at) ?? $t("standards.library.noPublishedAt") }}
          </time>
        </button>
      </li>
    </ul>
  </section>
</template>
<style scoped>
.library-pane{display:flex;flex-direction:column;gap:var(--space-3);min-width:0;min-height:0;height:100%}
.library-toolbar{display:grid;gap:var(--space-2);flex:none}
.library-status{color:var(--color-text-secondary);font-size:var(--font-label);margin:0}
.library-status.error{color:var(--color-danger)}
.library-list{list-style:none;margin:0;padding:0;display:grid;align-content:start;gap:var(--space-2);overflow:auto;min-height:0;flex:1}
.library-item{width:100%;display:grid;gap:var(--space-1);text-align:left;padding:var(--space-2) var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);cursor:pointer;min-width:0}
.library-item:hover{border-color:var(--color-border-strong)}
.library-item.selected{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.library-heading{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);min-width:0}
.library-name{font-weight:600;color:var(--color-text-primary);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.library-meta{display:flex;gap:var(--space-1);align-items:center;flex:none}
.library-description{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--color-text-secondary);font-size:var(--font-label);min-width:0}
.library-time{color:var(--color-text-muted);font-size:var(--font-caption);font-variant-numeric:tabular-nums}
.badge{font-size:var(--font-caption);padding:0 var(--space-2);border-radius:var(--radius-full);border:1px solid var(--color-border-subtle);color:var(--color-text-secondary);white-space:nowrap}
.badge.official{border-color:var(--color-accent);color:var(--color-accent)}
.badge.draft{border-color:var(--color-warning, var(--color-border-subtle))}
@media (max-width:959px){
  .library-toolbar{grid-template-columns:repeat(2,minmax(0,1fr));align-items:end}
  .library-toolbar>:first-child{grid-column:1/-1}
}
</style>
