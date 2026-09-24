<script setup lang="ts">
// 模板资产编辑器（PLAN-DM-035 Task 10 / SPEC-DM-016 §8.1 / PLAN-DM-040 Task 3）：
// 基础/布局为主分类，官方/用户为筛选器（不是两个彼此隔离的页面），列表显示名称、
// 来源、状态与引用数；右侧为检查面板。官方资产只读；用户资产允许添加、替换与移除。
//
// 文件本体：草稿文件行只保存**包内受控副本名**。桌面壳可用时经固定 `template`
// 文件种类选择本机 DWG/DWT，由后端复制进草稿受控目录；无壳本地开发态提供单独标明
// 的「来源绝对路径」输入，调用同一端点。本机绝对路径不写入缓冲，也不进草稿文档。
import {computed, ref, watch} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import AssetInspectionPanel from "./AssetInspectionPanel.vue";
import {ApiError} from "../../api/client";
import {i18n} from "../../i18n";
import {selectTemplatePath, shellReady} from "../../api/shell";
import {ASSET_KINDS, type DraftAsset, type DraftDocument} from "../../features/standards/draftModel";
import {
  assetReferences,
  recordFailure,
  recordInspection,
  recordInspectionState,
  recordInspectedAt,
  type AssetReference,
  type InspectionFailure,
  type InspectionRecord,
  type InspectionState,
} from "../../features/standards/publishModel";
import type {AssetInspection} from "../../features/standards/types";

const props = defineProps<{
  document: DraftDocument;
  /** 官方标准的资产声明（只读参考）；无可对照官方标准时为空数组。 */
  officialAssets: DraftAsset[];
  officialStandardId: string;
  /** 当前有效的检查记录（已绑定草稿身份与已保存快照）；无有效记录时为 null。 */
  record: InspectionRecord | null;
  pending: boolean;
  cadVersion: string;
  /** 受控复制：把本机来源复制进草稿，返回包内相对路径（失败抛出）。 */
  copyAssetFile: (sourcePath: string) => Promise<string>;
}>();
const emit = defineEmits<{recheck: []}>();

const sourceFilter = ref<"all" | "official" | "user">("all");
const selectedKey = ref<string | null>(null);
/** 无桌面壳时的来源绝对路径输入与就地错误（按文件行下标隔离）。 */
const sourcePaths = ref<Record<number, string>>({});
const fileErrors = ref<Record<number, string>>({});
const copyingIndex = ref<number | null>(null);

interface AssetRow {
  asset: DraftAsset;
  source: "user" | "official";
  references: AssetReference[];
}

const rows = computed<AssetRow[]>(() => [
  ...props.document.assets.map(asset => ({asset, source: "user" as const, references: assetReferences(props.document, asset)})),
  ...props.officialAssets.map(asset => ({asset, source: "official" as const, references: assetReferences(props.document, asset)})),
]);
const filtered = computed(() => rows.value.filter(row => sourceFilter.value === "all" || row.source === sourceFilter.value));
const groups = computed(() => [
  {key: "base", labelKey: "standards.assets.classification.base", rows: filtered.value.filter(row => row.asset.kind !== "layout-template")},
  {key: "layout", labelKey: "standards.assets.classification.layout", rows: filtered.value.filter(row => row.asset.kind === "layout-template")},
]);
const selected = computed<AssetRow | null>(() => {
  const current = filtered.value.find(row => rowKey(row) === selectedKey.value);
  return current ?? filtered.value[0] ?? null;
});

function rowKey(row: AssetRow): string {
  return `${row.source}/${row.asset.asset_id}`;
}

function stateOf(row: AssetRow): string {
  const key: Record<InspectionState, string> = {
    unchecked: "standards.assets.stateUnchecked",
    failed: "standards.assets.stateFailed",
    error: "standards.assets.stateError",
    passed: "standards.assets.statePassed",
  };
  return key[recordInspectionState(props.record, row.asset.asset_id)];
}

function inspectionOf(assetId: string): AssetInspection | undefined {
  return recordInspection(props.record, assetId);
}

function failureOf(assetId: string): InspectionFailure | undefined {
  return recordFailure(props.record, assetId);
}

function nextAssetId(kind: string): string {
  const used = new Set(props.document.assets.map(asset => asset.asset_id));
  const base = kind === "layout-template" ? "layout-template" : "base-template";
  let index = 1;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

function addAsset(kind: string): void {
  const asset: DraftAsset = {asset_id: nextAssetId(kind), kind, files: [{path: "", role: ""}]};
  props.document.assets.push(asset);
  selectedKey.value = `user/${asset.asset_id}`;
}

function removeAsset(asset: DraftAsset): void {
  const index = props.document.assets.indexOf(asset);
  if (index >= 0) props.document.assets.splice(index, 1);
  selectedKey.value = null;
}

function addFile(asset: DraftAsset): void {
  asset.files.push({path: "", role: ""});
}

function removeFile(asset: DraftAsset, index: number): void {
  asset.files.splice(index, 1);
}

function renameAsset(asset: DraftAsset, value: unknown): void {
  asset.asset_id = String(value);
  selectedKey.value = `user/${asset.asset_id}`;
}

// 切换选中资产时丢弃按行下标的临时输入与错误（不把上一个资产的输入带到下一个）
watch(
  () => (selected.value === null ? "" : rowKey(selected.value)),
  () => {
    sourcePaths.value = {};
    fileErrors.value = {};
  },
);

function targetText(key: string, params?: Record<string, string | number>): string {
  return i18n.global.t(key, params ?? {});
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.rawMessage || error.message;
    return error.code ? `${error.code}｜${detail}` : detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

/** 有壳：固定 `template` 文件种类选择本机模板；取消不发请求。 */
async function pickTemplate(asset: DraftAsset, index: number): Promise<void> {
  const picked = await selectTemplatePath(targetText("standards.assets.templateDialogDescription"));
  if (picked === undefined || picked === null) return;
  await applyCopy(asset, index, picked);
}

/** 无壳：显式来源绝对路径，调用同一受控复制端点。 */
async function copyFromPath(asset: DraftAsset, index: number): Promise<void> {
  const source = (sourcePaths.value[index] ?? "").trim();
  if (source === "") {
    fileErrors.value = {...fileErrors.value, [index]: targetText("standards.assets.sourcePathRequired")};
    return;
  }
  await applyCopy(asset, index, source);
}

/** 只有复制成功才修改编辑缓冲；失败保留旧声明与 dirty 状态并就地显示错误。 */
async function applyCopy(asset: DraftAsset, index: number, sourcePath: string): Promise<void> {
  if (copyingIndex.value !== null) return;
  copyingIndex.value = index;
  const cleared = {...fileErrors.value};
  delete cleared[index];
  fileErrors.value = cleared;
  try {
    const controlled = await props.copyAssetFile(sourcePath);
    asset.files[index].path = controlled;
  } catch (error) {
    fileErrors.value = {...fileErrors.value, [index]: errorText(error)};
  } finally {
    copyingIndex.value = null;
  }
}
</script>
<template>
  <section class="assets-editor" role="region" :aria-label="$t('standards.assets.title')">
    <header class="section-header">
      <div>
        <h3 class="section-title">{{ $t("standards.assets.title") }}</h3>
        <p class="section-hint">{{ $t("standards.assets.hint") }}</p>
      </div>
      <div class="section-actions">
        <UiButton variant="secondary" @click="addAsset('base-template')">{{ $t("standards.assets.addBase") }}</UiButton>
        <UiButton variant="secondary" @click="addAsset('layout-template')">{{ $t("standards.assets.addLayout") }}</UiButton>
      </div>
    </header>
    <p class="section-note" role="note">{{ $t("standards.assets.declarationHint") }}</p>
    <div class="filter-row">
      <UiSelect v-model="sourceFilter" :label="$t('standards.assets.sourceFilter')">
        <option value="all">{{ $t("standards.assets.sourceAll") }}</option>
        <option value="user">{{ $t("standards.assets.sourceUser") }}</option>
        <option value="official">{{ $t("standards.assets.sourceOfficial") }}</option>
      </UiSelect>
      <p class="section-note" role="status">
        {{ recordInspectedAt(record) === "" ? $t("standards.assets.notInspected") : $t("standards.assets.inspectedAt", {time: recordInspectedAt(record)}) }}
      </p>
    </div>
    <p v-if="document.assets.length === 0 && officialAssets.length === 0" class="section-empty">{{ $t("standards.assets.empty") }}</p>
    <p v-else-if="filtered.length === 0" class="section-empty">{{ $t("standards.assets.noMatch") }}</p>
    <div v-else class="assets-split">
      <div class="asset-groups">
        <section v-for="group in groups" :key="group.key" class="asset-group">
          <h4 class="group-title">{{ $t(group.labelKey) }}</h4>
          <p v-if="group.rows.length === 0" class="section-note">{{ $t("standards.assets.emptyGroup") }}</p>
          <ul class="asset-list">
            <li v-for="row in group.rows" :key="rowKey(row)">
              <button
                type="button"
                class="asset-item"
                :class="{active: selected !== null && rowKey(selected) === rowKey(row)}"
                :data-testid="`asset-row-${row.source}-${row.asset.asset_id}`"
                @click="selectedKey = rowKey(row)"
              >
                <span class="asset-name">{{ row.asset.asset_id }}</span>
                <span class="asset-meta">
                  <span class="asset-badge">{{ $t(row.source === "official" ? "standards.assets.sourceOfficialBadge" : "standards.assets.sourceUserBadge") }}</span>
                  <span class="asset-state">{{ $t(stateOf(row)) }}</span>
                  <span class="asset-count">{{ $t("standards.assets.referenceCount", {count: row.references.length}) }}</span>
                </span>
              </button>
            </li>
          </ul>
        </section>
      </div>
      <div v-if="selected" class="asset-detail">
        <AssetInspectionPanel
          :asset="selected.asset"
          :source="selected.source"
          :state="recordInspectionState(record, selected.asset.asset_id)"
          :inspection="inspectionOf(selected.asset.asset_id)"
          :failure="failureOf(selected.asset.asset_id)"
          :inspected-at="recordInspectedAt(record)"
          :pending="pending"
          :references="selected.references"
          @recheck="emit('recheck')"
        />
        <div v-if="selected.source === 'user'" class="asset-editor">
          <UiInput
            :model-value="selected.asset.asset_id"
            :label="$t('standards.assets.assetId')"
            @update:model-value="renameAsset(selected.asset, $event)"
          />
          <label class="field-label" :for="`asset-kind-${selected.asset.asset_id}`">{{ $t("standards.assets.kind") }}</label>
          <select :id="`asset-kind-${selected.asset.asset_id}`" v-model="selected.asset.kind" class="field-select">
            <option v-for="kind in ASSET_KINDS" :key="kind" :value="kind">
              {{ $t(kind === "layout-template" ? "standards.assets.kindLayout" : "standards.assets.kindBase") }}
            </option>
          </select>
          <div class="file-header">
            <h5 class="group-title">{{ $t("standards.assets.files") }}</h5>
            <UiButton variant="secondary" @click="addFile(selected.asset)">{{ $t("standards.assets.addFile") }}</UiButton>
          </div>
          <div v-for="(file, index) in selected.asset.files" :key="index" class="file-block">
            <div class="file-row">
              <UiInput
                :model-value="file.path"
                :label="$t('standards.assets.filePath')"
                :hint="$t('standards.assets.filePathHint')"
                :placeholder="$t('standards.assets.filePathPlaceholder')"
                readonly
                :data-testid="`asset-file-path-${index}`"
              />
              <UiInput v-model="file.role" :label="$t('standards.assets.fileRole')" placeholder="A3" />
              <div class="file-actions">
                <UiButton
                  v-if="shellReady"
                  variant="secondary"
                  :loading="copyingIndex === index"
                  :data-testid="`asset-file-pick-${index}`"
                  @click="pickTemplate(selected.asset, index)"
                >{{ file.path === "" ? $t("standards.assets.chooseTemplate") : $t("standards.assets.replaceFile") }}</UiButton>
                <template v-else>
                  <UiInput
                    :model-value="sourcePaths[index] ?? ''"
                    :label="$t('standards.assets.sourcePathLabel')"
                    :hint="$t('standards.assets.sourcePathHint')"
                    :data-testid="`asset-file-source-${index}`"
                    @update:model-value="(value: string) => sourcePaths[index] = value"
                  />
                  <UiButton
                    variant="secondary"
                    :loading="copyingIndex === index"
                    :data-testid="`asset-file-copy-${index}`"
                    @click="copyFromPath(selected.asset, index)"
                  >{{ file.path === "" ? $t("standards.assets.copyTemplate") : $t("standards.assets.replaceFile") }}</UiButton>
                </template>
              </div>
              <UiIconButton icon="close" :label="$t('standards.assets.removeFile', {row: index + 1})" @click="removeFile(selected.asset, index)" />
            </div>
            <p v-if="fileErrors[index]" class="file-error" role="alert" :data-testid="`asset-file-error-${index}`">
              {{ fileErrors[index] }}
            </p>
          </div>
          <UiButton variant="secondary" @click="removeAsset(selected.asset)">{{ $t("standards.assets.remove") }}</UiButton>
        </div>
        <p v-else class="section-note" role="note">{{ $t("standards.assets.officialReadOnly") }}</p>
      </div>
    </div>
  </section>
</template>
<style scoped>
.assets-editor{display:grid;gap:var(--space-3);min-width:0}
.section-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.section-hint{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-note{margin:0;font-size:var(--font-label);color:var(--color-text-muted)}
.section-empty{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.section-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
.filter-row{display:flex;align-items:end;gap:var(--space-3);flex-wrap:wrap}
.assets-split{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:var(--space-4);align-items:start}
.asset-groups{display:grid;gap:var(--space-3)}
.group-title{margin:0 0 var(--space-1);font-size:var(--font-label);color:var(--color-text-secondary)}
.asset-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.asset-item{width:100%;display:grid;gap:var(--space-1);text-align:left;padding:var(--space-2) var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);cursor:pointer}
.asset-item.active{border-color:var(--color-accent);box-shadow:inset 0 0 0 1px var(--color-accent)}
.asset-name{color:var(--color-text-primary);word-break:break-all}
.asset-meta{display:flex;gap:var(--space-2);flex-wrap:wrap;font-size:var(--font-label);color:var(--color-text-secondary)}
.asset-badge{border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);padding:0 var(--space-2)}
.asset-detail{display:grid;gap:var(--space-3);min-width:0}
.asset-editor{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.field-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.field-select{box-sizing:border-box;width:100%;height:var(--input-height);padding:0 var(--space-2);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary)}
.file-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2)}
.file-block{display:grid;gap:var(--space-1)}
.file-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) auto auto;gap:var(--space-2);align-items:end}
.file-actions{display:grid;gap:var(--space-2);align-items:end;min-width:0}
.file-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
@media (max-width: 959px){
  .assets-split{grid-template-columns:minmax(0,1fr)}
}
</style>
