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
import StandardEditor from "../components/standards/StandardEditor.vue";
import StandardImportDialog from "../components/standards/StandardImportDialog.vue";
import {selectStandardPackagePath, shellReady} from "../api/shell";
import {DEFAULT_FILTERS, detailActions, type StandardFilters} from "../components/standards/standardLibraryModel";
import {blankStandardDocument, draftKey, toDraftDocument, type DraftAsset} from "../features/standards/draftModel";
import type {AssetInspection} from "../features/standards/types";
import type {
  CreateMode,
  ImportPreviewResult,
  PublishedStandard,
  StandardIdentity,
  StandardSummary,
} from "../features/standards/types";
import type {StandardsEntryIntent} from "../composables/useStartNavigation";
// 「用于创建」把固定发布版本交给创建向导（PLAN-DM-036 Task 8）：本页只转发身份，
// 不持有创建草稿状态。
defineEmits<{back: []; openCreateSheetset: [identity: StandardIdentity]} >();
const props = defineProps<{
  confirmAction: (options: {title: string; message: string; confirmText: string; cancelText?: string; danger?: boolean}) => Promise<boolean>;
  /** 欢迎页「导入标准包」的一次性意图（PLAN-DM-039 Task 1）：只决定是否直接打开既有导入对话框。 */
  entryIntent?: StandardsEntryIntent;
}>();

const {t} = useI18n();
const store = createStandardStore(standardsApi);
const filters = ref<StandardFilters>({...DEFAULT_FILTERS});
const selectedKey = ref<string | null>(null);
const createDialogOpen = ref(false);
const createMode = ref<CreateMode>("blank");
const importDialogOpen = ref(false);
/** 收起的归集组（标准 ID）：导入成功后要展开目标组（PLAN-DM-041 Task 7）。 */
const collapsedGroups = ref<string[]>([]);
// 欢迎页「导入标准包」直接落到同一个导入对话框（不新增第二套导入表单或导入状态）。
// 只在组件创建时读一次意图：App 在 `v-if` 分支上重新挂载本页，因此每次进入都是新实例；
// 意图是“一次性”的，用户关掉对话框后不得再被重新打开。
if (props.entryIntent === "import-package") importDialogOpen.value = true;
const narrow = ref(window.matchMedia("(max-width: 959px)").matches);
window.matchMedia("(max-width: 959px)").addEventListener("change", event => {narrow.value = event.matches;});
/** 窄视口两级视图状态（宽视口忽略）：选中即进详情，返回列表保留选择与筛选。 */
const narrowPane = ref<"list" | "detail">("list");

onMounted(() => {void store.refresh();});

function keyOf(summary: StandardSummary): string {
  return draftKey(summary);
}

const selected = computed<StandardSummary | null>(() =>
  store.summaries.value.find(item => keyOf(item) === selectedKey.value) ?? null,
);

// —— 草稿编辑器接线（Task 9）：仅用户草稿可编辑，且离开编辑器要过未保存修改三选一门禁 ——
const editorOpen = ref(false);
const editorRef = ref<{guard: (next: () => void | Promise<void>) => Promise<void>} | null>(null);
/** 打开编辑器时固定的草稿身份：检查/发布/复制只用它，不从列表选择反推（F03）。 */
const editorDraftId = ref("");
/** 同名官方标准声明的资产（只读参考）；无可对照官方标准时为空。 */
const officialAssets = ref<DraftAsset[]>([]);
const officialStandardId = ref("");

async function openEditor(): Promise<void> {
  const summary = selected.value;
  if (summary?.draft_id === null || summary?.draft_id === undefined) return;
  const loaded = await store.loadDraft(summary.draft_id);
  if (loaded === null) return; // 加载失败：错误留到草稿错误区，不进入空编辑器
  officialAssets.value = [];
  officialStandardId.value = "";
  editorDraftId.value = loaded.draft_id;
  editorOpen.value = true;
  await loadOfficialReference(String(loaded.document["standard_id"] ?? ""));
}

/** 编辑器操作目标：未进入编辑器时一律拒绝，绝不回退到列表选中项。 */
function editorDraft(): string {
  if (editorDraftId.value === "") throw new Error("STANDARD_DRAFT_NOT_FOUND");
  return editorDraftId.value;
}

/** 标准库中存在同名官方已发布版本时，取其资产声明作为只读对照（不修改草稿）。 */
async function loadOfficialReference(standardId: string): Promise<void> {
  const reference = store.summaries.value.find(item =>
    item.source === "official"
    && item.status === "published"
    && item.standard_id === standardId
    && item.version !== null);
  if (reference === undefined || reference.version === null || standardId === "") return;
  try {
    await store.open({standardId: reference.standard_id, version: reference.version});
    const document = store.detail.value?.document;
    officialAssets.value = document === undefined ? [] : toDraftDocument(document).assets;
    officialStandardId.value = reference.standard_id;
  } catch {
    // 官方对照加载失败不影响编辑：来源筛选退化为仅本草稿资产
    officialAssets.value = [];
  }
}

async function leaveEditor(): Promise<void> {
  editorOpen.value = false;
  editorDraftId.value = "";
  store.closeDraft();
  officialAssets.value = [];
  officialStandardId.value = "";
  await store.refresh();
  // 退出编辑器后回到列表选中项的详情：草稿没有发布详情，清掉对照官方详情避免越权展示
  if (selected.value?.status === "draft") store.clearDetail();
}

/** 编辑器内保存：走草稿级路由，身份固定为打开编辑器时的 draft_id（F11）。 */
async function saveEditorDocument(document: Record<string, unknown>): Promise<Record<string, unknown>> {
  const saved = await store.saveDraft({draftId: editorDraft(), document});
  return saved.document;
}

/** 资产检查：后端固定读取协议，失败抛出交由编辑器归为「检查本身失败」。 */
async function inspectEditorAsset(assetId: string, cadVersion: string): Promise<AssetInspection> {
  return store.inspectAsset({draftId: editorDraft(), assetId, cadVersion});
}

/** 本机模板受控复制：只把后端生成的包内相对路径交给编辑器缓冲。 */
async function copyEditorAssetFile(sourcePath: string): Promise<string> {
  const copied = await store.copyAssetFile({draftId: editorDraft(), sourcePath});
  return copied.path;
}

/** 发布：成功时后端把草稿移入已发布目录，需退出编辑器并定位到新版本只读详情。 */
async function publishEditorDraft(): Promise<void> {
  const published = await store.publish({draftId: editorDraft()});
  await leaveEditor();
  // 发布总是写入用户已发布根：按返回的 standard_id/version 精确选中新发布版本
  selectedKey.value = draftKey({
    source: "user",
    standard_id: published.standard_id,
    draft_id: null,
    version: published.version,
  });
  await store.open({standardId: published.standard_id, version: published.version});
}

async function select(summary: StandardSummary): Promise<void> {
  const apply = async () => {
    selectedKey.value = keyOf(summary);
    if (editorOpen.value) await leaveEditor();
    if (summary.status === "published" && summary.version !== null) {
      await store.open({standardId: summary.standard_id, version: summary.version});
    } else {
      // 草稿无发布详情：清空详情并让在途发布详情响应失效，避免只读边界漂移
      store.clearDetail();
    }
    narrowPane.value = "detail"; // 窄视口：选中即进入详情页
  };
  // 编辑器在场且有未保存修改时，切换选中项必须先过三选一门禁
  if (editorOpen.value) await editorRef.value?.guard(apply);
  else await apply();
}

/** 详情重试：只重发当前选择的详情请求（列表与选择保持不变）。 */
async function retryDetail(): Promise<void> {
  const summary = selected.value;
  if (summary === null || summary.status !== "published" || summary.version === null) return;
  await store.open({standardId: summary.standard_id, version: summary.version});
}

/** 清除筛选：恢复默认筛选，不改变当前选择。 */
function clearFilters(): void {
  filters.value = {...DEFAULT_FILTERS};
}

function openVersion(entry: {source: "official" | "user"; standard_id: string; version: number; name: string}): void {
  // 版本历史跳转：按条目自身身份选中（跨官方/用户来源时不得沿用当前来源）
  const known = store.summaries.value.find(item =>
    item.status === "published"
    && item.source === entry.source
    && item.standard_id === entry.standard_id
    && item.version === entry.version,
  );
  const summary: StandardSummary = known ?? {
    source: entry.source,
    status: "published",
    standard_id: entry.standard_id,
    version: entry.version,
    name: entry.name,
    draft_id: null,
  };
  void select(summary);
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

async function submitCreate(payload: {name: string; dstPath: string}): Promise<void> {
  const origin = createMode.value === "derive" ? selected.value : null;
  let created: {draft_id: string; document: Record<string, unknown>};
  try {
    if (origin !== null && origin.version !== null) {
      // 派生只消费身份匹配且已完成加载的详情：B 在途/加载失败时绝不复制 A（F08）
      const identity: StandardIdentity = {standardId: origin.standard_id, version: origin.version};
      const base = store.detailMatches(identity) ? store.detail.value?.document : undefined;
      if (base === undefined) {
        // 派生必须基于已加载的发布版本文档：缺详情不提交，保留对话框与可见原因
        store.actionError.value = t("standards.create.deriveNeedsDetail");
        return;
      }
      // 草稿不携带版本：派生时也要去掉源版本的 version（SPEC-DM-019 §2.3）。
      const derived: Record<string, unknown> = {...base, standard_id: origin.standard_id, name: payload.name};
      delete derived.version;
      created = await store.createDraft({document: derived});
    } else if (createMode.value === "from-dst") {
      created = await store.createDraftFromDst({dstPath: payload.dstPath});
    } else {
      created = await store.createDraft({
        document: blankStandardDocument({
          standardId: defaultStandardId(payload.name),
          name: payload.name,
        }),
      });
    }
  } catch {
    // 创建失败（重复身份/非法 DST 等）保留对话框与当前选择，错误经 actionError 呈现
    return;
  }
  // 创建后直接进入编辑器：草稿身份已经由创建响应给出，不再多发一次 GET
  store.adoptDraft(created);
  editorDraftId.value = created.draft_id;
  editorOpen.value = true;
  createDialogOpen.value = false;
  // 选中身份必须指向新草稿：否则标题栏/列表刷新后仍停留在旧草稿，检查与发布会打错目标
  selectedKey.value = draftKey({
    source: "user",
    standard_id: String(created.document["standard_id"] ?? ""),
    draft_id: created.draft_id,
    version: null,
  });
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
  // 选中项已删除：窄视口必须回到列表，否则停在无可返回入口的空白详情（详情面板的空态无返回按钮）
  narrowPane.value = "list";
  await store.refresh();
}

// —— 标准包导入（PLAN-DM-041 Task 5/7）：预检 → 凭证确认 ——
/** 预检：后端把选定的包复制到限时快照并返回候选身份、诊断与可否导入。 */
async function previewImport(path: string): Promise<ImportPreviewResult> {
  return store.previewImport({path});
}

/** 确认导入：只消费预检凭证（服务端不接受路径）。 */
async function confirmImport(previewId: string): Promise<PublishedStandard> {
  return store.confirmImport({previewId});
}

/** 取消预检：删除服务端快照；失败不影响用户继续操作（过期后服务端自行清理）。 */
async function cancelImport(previewId: string): Promise<void> {
  return store.cancelImport(previewId);
}

/** 原生选择：桥不可用时返回 undefined，弹窗切到明确标注的本机路径开发态。 */
async function selectImportPath(localizedDescription: string): Promise<string | null | undefined> {
  return selectStandardPackagePath(localizedDescription);
}

function toggleGroup(standardId: string): void {
  const next = new Set(collapsedGroups.value);
  if (next.has(standardId)) next.delete(standardId);
  else next.add(standardId);
  collapsedGroups.value = [...next];
}

/** 导入成功：刷新列表、展开目标 ID 组并定位到导入版本详情。
 *
 * 弹窗保持打开并显示成功状态（用户自行关闭），因此刷新与定位在成功响应时立即完成。
 */
async function onImported(published: PublishedStandard): Promise<void> {
  collapsedGroups.value = collapsedGroups.value.filter(id => id !== published.standard_id);
  await store.refresh();
  selectedKey.value = draftKey({
    source: "user",
    standard_id: published.standard_id,
    version: published.version,
    draft_id: null,
  });
  await store.open({standardId: published.standard_id, version: published.version});
  narrowPane.value = "detail";
}

// 已发布标准包导出：拼后端下载地址并以带 download 的临时链接触发下载（不把 zip 读进内存）。
function exportSelectedStandard(): void {
  const summary = selected.value;
  if (summary === null || summary.status !== "published" || summary.version === null) return;
  const anchor = document.createElement("a");
  anchor.href = standardExportUrl({standardId: summary.standard_id, version: summary.version});
  anchor.download = `${summary.standard_id}-v${summary.version}.dststandard`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

const selectedActions = computed(() => selected.value === null ? null : detailActions(selected.value));
</script>
<template>
  <section class="standards-page" :class="{'is-editor': editorOpen}" role="region" :aria-label="$t('standards.title')">
    <!-- 互斥页面状态（PLAN-DM-039 Task 2）：编辑器打开时用 Vue 分支**卸载**标准库与详情，
         不靠 CSS 隐藏——否则会残留重复地标、不可见可聚焦元素与屏幕阅读器重复内容。
         返回时 store、selectedKey、filters 仍由本组件持有，选择/筛选/详情不重建。 -->
    <StandardEditor
      v-if="editorOpen && store.draft.value"
      ref="editorRef"
      data-testid="standards-editor-mode"
      :draft="store.draft.value"
      :save-draft="saveEditorDocument"
      :inspect-asset="inspectEditorAsset"
      :copy-asset-file="copyEditorAssetFile"
      :publish-draft="publishEditorDraft"
      :official-assets="officialAssets"
      :official-standard-id="officialStandardId"
      @close="leaveEditor"
    />
    <template v-else>
      <div class="standards-header">
        <h2 class="standards-title">{{ $t("standards.title") }}</h2>
        <UiButton variant="secondary" @click="$emit('back')">{{ $t("standards.back") }}</UiButton>
      </div>
      <p v-if="store.actionError.value" class="standards-error" role="alert">{{ store.actionError.value }}</p>
      <div class="library-split" data-testid="standards-library-mode" :class="{'detail-open': narrow && narrowPane === 'detail'}">
        <StandardLibraryPane
          class="library-col"
          :items="store.summaries.value"
          :filters="filters"
          :selected-key="selectedKey"
          :list-pending="store.listPending.value"
          :list-error="store.listError.value"
          :collapsed-groups="collapsedGroups"
          @select="select"
          @update-filters="filters = $event"
          @import-package="importDialogOpen = true"
          @create-new="openCreateDialog"
          @retry="store.refresh()"
          @clear-filters="clearFilters"
          @toggle-group="toggleGroup"
        />
        <StandardDetailPane
          class="detail-col"
          :summary="selected"
          :detail="store.detail.value"
          :detail-pending="store.detailPending.value"
          :detail-error="store.detailError.value || store.draftError.value"
          :items="store.summaries.value"
          :narrow="narrow"
          @edit="openEditor"
          @derive="startCreate('derive')"
          @export-standard="exportSelectedStandard"
          @delete-draft="deleteSelectedDraft"
          @use-for-create="$emit('openCreateSheetset', $event)"
          @open-version="openVersion"
          @retry="retryDetail"
          @back-to-list="narrowPane = 'list'"
        />
      </div>
    </template>
    <StandardCreateDialog
      :open="createDialogOpen"
      :mode="createMode"
      :origin="selected"
      :default-draft-name="defaultDraftName"
      @close="createDialogOpen = false"
      @submit="submitCreate"
    />
    <StandardImportDialog
      :open="importDialogOpen"
      :shell-available="shellReady"
      :select-path="selectImportPath"
      :preview-import="previewImport"
      :confirm-import="confirmImport"
      :cancel-import="cancelImport"
      @close="importDialogOpen = false"
      @imported="onImported"
    />
  </section>
</template>
<style scoped>
.standards-page{width:100%;max-width:var(--shell-content-max-width,1200px);margin:0 auto;padding:var(--space-5);display:grid;gap:var(--space-4)}
/* 编辑器模式：标准页只渲染独立工作台，不再被主从分栏的固定左栏挤压（PLAN-DM-039 Task 2）。
   `width:100%` 是必要的：壳层 `main` 是列向 flex 容器，配合 `margin:0 auto` 时子项
   会按内容宽度收缩（实测标准库模式仅 666px），显式宽度才让 `max-width` 真正成为唯一上限。
   编辑器**不**放开 `max-width`：宽屏（2560 实测）下必须仍受 `--shell-content-max-width` 约束，
   否则八列表格被拉散（对照 SPEC-DM-017 Demo 的 `min(1400px,100%)`）。 */
.standards-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3)}
.standards-title{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.standards-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
.library-split{display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:var(--space-4);align-items:start}
.library-col,.detail-col{border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);padding:var(--space-4);background:var(--color-bg-surface)}
/* 900×768（窄视口）：列表 ↔ 详情两级互斥视图；详情页提供可见返回按钮 */
@media (max-width: 959px){
  .library-split{grid-template-columns:minmax(0,1fr)}
  .library-split:not(.detail-open) .detail-col{display:none}
  .library-split.detail-open .library-col{display:none}
}
</style>
