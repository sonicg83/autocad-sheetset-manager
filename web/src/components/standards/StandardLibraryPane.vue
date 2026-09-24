<script setup lang="ts">
// 标准库左栏（PLAN-DM-035 Task 8；PLAN-DM-041 Task 6）：搜索、来源/状态筛选与
// 按 `standard_id` 归集的版本列表。空库与筛选无结果必须区分呈现（用户不知道是
// "没有标准"还是"筛没了"）；组内版本整数降序，展示为 `v<n>`。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiIcon from "../ui/UiIcon.vue";
import {
  buildLibraryState,
  formatStandardVersion,
  type StandardFilters,
  type StandardGroup,
} from "./standardLibraryModel";
import {draftKey} from "../../features/standards/draftModel";
import type {StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  items: StandardSummary[];
  filters: StandardFilters;
  selectedKey: string | null;
  listPending: boolean;
  listError: string;
  /** 收起的归集组（标准 ID）；由页面持有，便于导入成功后展开目标组。 */
  collapsedGroups: string[];
}>();
const emit = defineEmits<{
  select: [summary: StandardSummary];
  updateFilters: [filters: StandardFilters];
  importPackage: [];
  createNew: [];
  /** 列表加载失败就地重试：只重发列表请求。 */
  retry: [];
  /** 筛选无结果：恢复默认筛选，不改变当前选择。 */
  clearFilters: [];
  /** 收起/展开一个归集组（键盘可达的组头按钮）。 */
  toggleGroup: [standardId: string];
}>();

const state = computed(() => buildLibraryState(props.items, props.filters));
// 组默认展开；收起状态由页面按标准 ID 持有，键盘可达（组头是带 aria-expanded 的按钮）。
function isCollapsed(standardId: string): boolean {
  return props.collapsedGroups.includes(standardId);
}

function toggle(standardId: string): void {
  emit("toggleGroup", standardId);
}

function entries(group: StandardGroup): StandardSummary[] {
  return [...group.versions, ...group.drafts];
}

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
    <ul v-else class="library-groups" data-testid="library-list">
      <li v-for="group in state.groups" :key="group.standard_id" class="library-group" data-testid="library-group">
        <button
          type="button"
          class="group-header"
          data-testid="library-group-header"
          :aria-expanded="!isCollapsed(group.standard_id)"
          :aria-controls="`library-group-${group.standard_id}`"
          @click="toggle(group.standard_id)"
        >
          <UiIcon class="group-chevron" :name="isCollapsed(group.standard_id) ? 'chevron-right' : 'chevron-down'" aria-hidden="true" />
          <span class="group-title">{{ group.title }}</span>
          <span class="group-id">{{ group.standard_id }}</span>
          <span v-if="group.versions.length > 0" class="badge">{{ formatStandardVersion(group.versions[0].version ?? 0) }}</span>
          <span v-if="group.drafts.length > 0" class="badge draft">{{ $t("standards.library.statusDraftBadge") }}</span>
        </button>
        <ul
          v-show="!isCollapsed(group.standard_id)"
          :id="`library-group-${group.standard_id}`"
          class="group-entries"
        >
          <li v-for="item in entries(group)" :key="draftKey(item)">
            <button
              type="button"
              class="library-item"
              data-testid="library-item"
              :class="{selected: selectedKey===draftKey(item)}"
              @click="emit('select', item)"
            >
              <span class="library-name">{{ item.name }}</span>
              <span class="library-meta">
                <span class="badge" :class="item.source">{{ $t(item.source==='official' ? 'standards.library.sourceOfficialBadge' : 'standards.library.sourceUserBadge') }}</span>
                <span class="badge" :class="item.status">{{ $t(item.status==='draft' ? 'standards.library.statusDraftBadge' : 'standards.library.statusPublishedBadge') }}</span>
                <span v-if="item.status==='published'" class="library-version">{{ formatStandardVersion(item.version ?? 0) }}</span>
              </span>
            </button>
          </li>
        </ul>
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
.library-groups{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2);overflow:auto}
.library-group{display:grid;gap:var(--space-1)}
.group-header{width:100%;display:flex;gap:var(--space-2);align-items:center;text-align:left;padding:var(--space-2);background:transparent;border:1px solid transparent;border-radius:var(--radius-md);cursor:pointer}
.group-header:hover{border-color:var(--color-border-subtle)}
.group-chevron{color:var(--color-text-secondary)}
.group-title{font-weight:600;color:var(--color-text-primary)}
.group-id{font-size:var(--font-label);color:var(--color-text-secondary)}
.group-entries{list-style:none;margin:0;padding:0 0 0 var(--space-3);display:grid;gap:var(--space-1)}
.badge.draft{border-color:var(--color-warning, var(--color-border-subtle))}
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
