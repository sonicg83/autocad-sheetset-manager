<script setup lang="ts">
// 标准管理页（PLAN-DM-035 Task 8）：主从分栏标准库与只读边界。
// 左栏搜索/筛选/列表，右栏身份/能力摘要/版本历史/动作；900×768 收窄为
// "列表 → 详情"分级视图。页面级状态经 createStandardStore 持有。
import {computed, onMounted, ref} from "vue";
import {useI18n} from "vue-i18n";
import {createStandardStore} from "../features/standards/store";
import {standardExportUrl, standardsApi} from "../api/standards";
import UiButton from "../components/ui/UiButton.vue";
import StandardLibraryPane from "../components/standards/StandardLibraryPane.vue";
import StandardDetailPane from "../components/standards/StandardDetailPane.vue";
import StandardCreateDialog from "../components/standards/StandardCreateDialog.vue";
import {DEFAULT_FILTERS, detailActions, type StandardFilters} from "../components/standards/standardLibraryModel";
import type {CreateMode, StandardSummary} from "../features/standards/types";

defineEmits<{back: []; openCreateSheetset: []}>();
const props = defineProps<{confirmAction: (options: {title: string; message: string; confirmText: string; cancelText?: string; danger?: boolean}) => Promise<boolean>}>();

const {t} = useI18n();
const store = createStandardStore(standardsApi);
const filters = ref<StandardFilters>({...DEFAULT_FILTERS});
const selectedKey = ref<string | null>(null);
const createDialogOpen = ref(false);
const createMode = ref<CreateMode>("blank");
const importDialogOpen = ref(false);
const importPath = ref("");
const narrow = ref(window.matchMedia("(max-width: 959px)").matches);
window.matchMedia("(max-width: 959px)").addEventListener("change", event => {narrow.value = event.matches;});

onMounted(() => {void store.refresh();});

function keyOf(summary: StandardSummary): string {
  return `${summary.source}/${summary.draft_id ?? summary.version}`;
}

const selected = computed<StandardSummary | null>(() =>
  store.summaries.value.find(item => keyOf(item) === selectedKey.value) ?? null,
);

async function select(summary: StandardSummary): Promise<void> {
  selectedKey.value = keyOf(summary);
  if (summary.status === "published") {
    await store.open({standardId: summary.standard_id, version: summary.version});
  } else {
    // 草稿无发布详情：清空详情并让在途发布详情响应失效，避免只读边界漂移
    store.clearDetail();
  }
}

function openVersion(version: string): void {
  if (selected.value === null) return;
  void select({...selected.value, status: "published", version, draft_id: null});
}

const draftCount = computed(() => store.summaries.value.filter(item => item.status === "draft").length);
const defaultDraftName = computed(() => t("standards.create.defaultName", {count: draftCount.value + 1}));

function startCreate(mode: CreateMode): void {
  createMode.value = mode;
  createDialogOpen.value = true;
}

function openCreateDialog(): void {
  startCreate("blank");
}

async function submitCreate(payload: {name: string; version: string; dstPath: string}): Promise<void> {
  const origin = createMode.value === "derive" ? selected.value : null;
  try {
    if (origin !== null) {
      const base = store.detail.value?.document;
      if (base === undefined) {
        // 派生必须基于已加载的发布版本文档：缺详情不提交，保留对话框与可见原因
        store.actionError.value = t("standards.create.deriveNeedsDetail");
        return;
      }
      await store.createDraft({
        document: {...base, standard_id: origin.standard_id, version: payload.version, name: payload.name},
      });
    } else if (createMode.value === "from-dst") {
      await store.createDraftFromDst({dstPath: payload.dstPath});
    } else {
      await store.createDraft({
        document: {
          schema_version: 1,
          standard_id: defaultStandardId(payload.name),
          version: payload.version,
          name: payload.name,
          supported_cad_versions: ["2020"],
          properties: [],
          rules: [],
          assets: [],
          numbering: {sequence_field: "subset.sequence", digits: 2},
        },
      });
    }
  } catch {
    // 创建失败（重复身份/非法 DST 等）保留对话框与当前选择，错误经 actionError 呈现
    return;
  }
  createDialogOpen.value = false;
  await store.refresh();
}

function defaultStandardId(name: string): string {
  const ascii = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return ascii.length > 0 ? `user.${ascii}` : "user.draft";
}

async function deleteSelectedDraft(): Promise<void> {
  const summary = selected.value;
  if (summary?.draft_id === null || summary?.draft_id === undefined) return;
  const confirmed = await props.confirmAction({
    title: t("standards.delete.title"),
    message: t("standards.delete.message", {name: summary.name}),
    confirmText: t("standards.delete.confirm"),
    cancelText: t("standards.create.cancel"),
    danger: true,
  });
  if (!confirmed) return;
  try {
    await store.deleteDraft(summary.draft_id);
  } catch {
    // 删除失败保留当前选择，错误经 actionError 呈现
    return;
  }
  selectedKey.value = null;
  store.clearDetail();
  await store.refresh();
}

async function importPackage(): Promise<void> {
  if (!importPath.value.trim()) return;
  try {
    await store.importPackage({path: importPath.value.trim()});
    importDialogOpen.value = false;
    importPath.value = "";
    await store.refresh();
  } catch {
    // 导入碰撞/校验失败不改变列表选择：错误留在 actionError，当前选择保持
  }
}

// 已发布标准包导出：拼后端下载地址并以带 download 的临时链接触发下载（不把 zip 读进内存）。
function exportSelectedStandard(): void {
  const summary = selected.value;
  if (summary === null || summary.status !== "published") return;
  const anchor = document.createElement("a");
  anchor.href = standardExportUrl({standardId: summary.standard_id, version: summary.version});
  anchor.download = `${summary.standard_id}-${summary.version}.dststandard`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

const selectedActions = computed(() => selected.value === null ? null : detailActions(selected.value));

// 编辑动作由 Task 9 的 StandardEditor 承接：本任务中 editorAvailable 恒为 false，
// 草稿的"编辑"按钮不可用并附可见原因（standards.detail.editorPending）。
const editorAvailable = false;
</script>
<template>
  <section class="standards-page" role="region" :aria-label="$t('standards.title')">
    <div class="standards-header">
      <h2 class="standards-title">{{ $t("standards.title") }}</h2>
      <UiButton variant="secondary" @click="$emit('back')">{{ $t("standards.back") }}</UiButton>
    </div>
    <p v-if="store.actionError.value" class="standards-error" role="alert">{{ store.actionError.value }}</p>
    <div class="library-split" :class="{'detail-open': narrow && selected !== null}">
      <StandardLibraryPane
        class="library-col"
        :items="store.summaries.value"
        :filters="filters"
        :selected-key="selectedKey"
        :list-pending="store.listPending.value"
        :list-error="store.listError.value"
        @select="select"
        @update-filters="filters = $event"
        @import-package="importDialogOpen = true"
        @create-new="openCreateDialog"
      />
      <StandardDetailPane
        class="detail-col"
        :summary="selected"
        :detail="store.detail.value"
        :detail-pending="store.detailPending.value"
        :detail-error="store.detailError.value"
        :items="store.summaries.value"
        :editor-available="editorAvailable"
        @derive="startCreate('derive')"
        @export-standard="exportSelectedStandard"
        @delete-draft="deleteSelectedDraft"
        @use-for-create="$emit('openCreateSheetset')"
        @open-version="openVersion"
      />
    </div>
    <StandardCreateDialog
      :open="createDialogOpen"
      :mode="createMode"
      :origin="selected"
      :default-draft-name="defaultDraftName"
      @close="createDialogOpen = false"
      @submit="submitCreate"
    />
    <div v-if="importDialogOpen" class="import-backdrop" @click.self="importDialogOpen = false">
      <section class="import-dialog" role="dialog" aria-modal="true" :aria-label="$t('standards.import.title')">
        <h3>{{ $t("standards.import.title") }}</h3>
        <label class="import-label" for="import-path-input">{{ $t("standards.import.pathLabel") }}</label>
        <input id="import-path-input" v-model="importPath" type="text">
        <div class="import-actions">
          <UiButton variant="secondary" @click="importDialogOpen = false">{{ $t("standards.create.cancel") }}</UiButton>
          <UiButton variant="secondary" :disabled="!importPath.trim()" @click="importPackage">{{ $t("standards.import.confirm") }}</UiButton>
        </div>
      </section>
    </div>
  </section>
</template>
<style scoped>
.standards-page{max-width:var(--shell-content-max-width,1200px);margin:0 auto;padding:var(--space-5);display:grid;gap:var(--space-4)}
.standards-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3)}
.standards-title{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.standards-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
.library-split{display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:var(--space-4);align-items:start}
.library-col,.detail-col{border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);padding:var(--space-4);background:var(--color-bg-surface)}
.import-backdrop{position:fixed;inset:0;background:rgb(0 0 0 / 0.4);display:grid;place-items:center;z-index:60}
.import-dialog{width:min(420px,calc(100vw - 32px));display:grid;gap:var(--space-3);padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.import-dialog h3{margin:0;font-size:var(--font-page-title)}
.import-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.import-dialog input{height:var(--control-height-default,38px);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:0 var(--space-3)}
.import-actions{display:flex;gap:var(--space-2);justify-content:flex-end}
/* 900×768（窄视口）：列表 → 详情分级视图；选中前只显示列表 */
@media (max-width: 959px){
  .library-split{grid-template-columns:minmax(0,1fr)}
  .library-split:not(.detail-open) .detail-col{display:none}
}
</style>
