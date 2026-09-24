<script setup lang="ts">
// 标准库左栏（PLAN-DM-035 Task 8）：搜索、来源/状态筛选与列表。
// 空库与筛选无结果必须区分呈现（用户不知道是"没有标准"还是"筛没了"）。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import {buildLibraryState, type StandardFilters} from "./standardLibraryModel";
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
  importPackage: [];
  createNew: [];
}>();

const state = computed(() => buildLibraryState(props.items, props.filters));

function update(partial: Partial<StandardFilters>): void {
  emit("updateFilters", {...props.filters, ...partial});
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
    <p v-else-if="listError" class="library-status error" role="alert">{{ $t("standards.library.loadFailed", {message: listError}) }}</p>
    <p v-else-if="state.kind==='empty-library'" class="library-status">{{ $t("standards.library.empty") }}</p>
    <p v-else-if="state.kind==='empty-filter'" class="library-status">{{ $t("standards.library.noMatch") }}</p>
    <ul v-else class="library-list" data-testid="library-list">
      <li v-for="item in state.items" :key="draftKey(item)">
        <button
          type="button"
          class="library-item"
          :class="{selected: selectedKey===draftKey(item)}"
          @click="emit('select', item)"
        >
          <span class="library-name">{{ item.name }}</span>
          <span class="library-meta">
            <span class="badge" :class="item.source">{{ $t(item.source==='official' ? 'standards.library.sourceOfficialBadge' : 'standards.library.sourceUserBadge') }}</span>
            <span class="badge" :class="item.status">{{ $t(item.status==='draft' ? 'standards.library.statusDraftBadge' : 'standards.library.statusPublishedBadge') }}</span>
            <span v-if="item.status==='published'" class="library-version">{{ item.version }}</span>
          </span>
        </button>
      </li>
    </ul>
    <div class="library-actions">
      <UiButton variant="secondary" @click="emit('createNew')">{{ $t("standards.library.newDraft") }}</UiButton>
      <UiButton variant="secondary" @click="emit('importPackage')">{{ $t("standards.library.import") }}</UiButton>
    </div>
  </section>
</template>
<style scoped>
.library-pane{display:grid;gap:var(--space-3);align-content:start;min-width:0}
.library-toolbar{display:grid;gap:var(--space-2)}
.library-status{color:var(--color-text-secondary);font-size:var(--font-label);margin:0}
.library-status.error{color:var(--color-danger)}
.library-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);overflow:auto}
.library-item{width:100%;display:grid;gap:var(--space-1);text-align:left;padding:var(--space-2) var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);cursor:pointer}
.library-item:hover{border-color:var(--color-border-strong)}
.library-item.selected{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.library-name{font-weight:500;color:var(--color-text-primary)}
.library-meta{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap}
.library-version{font-size:var(--font-label);color:var(--color-text-secondary)}
.badge{font-size:var(--font-label);padding:0 var(--space-2);border-radius:var(--radius-full);border:1px solid var(--color-border-subtle);color:var(--color-text-secondary)}
.badge.official{border-color:var(--color-accent);color:var(--color-accent)}
.library-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
</style>
