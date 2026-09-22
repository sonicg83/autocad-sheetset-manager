<script setup lang="ts">
// 模板资产编辑器（PLAN-DM-035 Task 10 / SPEC-DM-016 §8.1）：基础/布局为主分类，
// 官方/用户为筛选器（不是两个彼此隔离的页面），列表显示名称、来源、状态与引用数；
// 右侧为检查面板。官方资产只读；用户资产允许添加、替换（改声明）与移除。
//
// 当前范围边界（后端无资产文件上传端点）：本分区编辑的是**资产声明**（受控路径 + 图幅 role）。
// 文件本体随标准包提供，声明了但不在草稿受控目录内的文件由检查报告 STANDARD_ASSET_FILE_MISSING，
// 并阻断发布；不伪造“已替换文件”的假象。
import {computed, ref} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import AssetInspectionPanel from "./AssetInspectionPanel.vue";
import {ASSET_KINDS, type DraftAsset, type DraftDocument} from "../../features/standards/draftModel";
import {assetReferences, type AssetReference, type InspectionFailure} from "../../features/standards/publishModel";
import type {AssetInspection} from "../../features/standards/types";

const props = defineProps<{
  document: DraftDocument;
  /** 官方标准的资产声明（只读参考）；无可对照官方标准时为空数组。 */
  officialAssets: DraftAsset[];
  officialStandardId: string;
  inspections: AssetInspection[];
  inspectionFailures: InspectionFailure[];
  inspectedAt: string;
  pending: boolean;
  cadVersion: string;
}>();
const emit = defineEmits<{recheck: []}>();

const sourceFilter = ref<"all" | "official" | "user">("all");
const selectedKey = ref<string | null>(null);

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
  if (props.inspectionFailures.some(item => item.assetId === row.asset.asset_id)) return "standards.assets.stateError";
  const inspection = props.inspections.find(item => item.asset_id === row.asset.asset_id);
  if (inspection === undefined) return "standards.assets.stateUnchecked";
  return inspection.diagnostics.length > 0 ? "standards.assets.stateFailed" : "standards.assets.statePassed";
}

function inspectionOf(assetId: string): AssetInspection | undefined {
  return props.inspections.find(item => item.asset_id === assetId);
}

function failureOf(assetId: string): InspectionFailure | undefined {
  return props.inspectionFailures.find(item => item.assetId === assetId);
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
        {{ inspectedAt === "" ? $t("standards.assets.notInspected") : $t("standards.assets.inspectedAt", {time: inspectedAt}) }}
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
          :inspection="inspectionOf(selected.asset.asset_id)"
          :failure="failureOf(selected.asset.asset_id)"
          :inspected-at="inspectedAt"
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
          <div v-for="(file, index) in selected.asset.files" :key="index" class="file-row">
            <UiInput v-model="file.path" :label="$t('standards.assets.filePath')" placeholder="assets/template.dwg" />
            <UiInput v-model="file.role" :label="$t('standards.assets.fileRole')" placeholder="A3" />
            <UiIconButton icon="close" :label="$t('standards.assets.removeFile', {row: index + 1})" @click="removeFile(selected.asset, index)" />
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
.file-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) auto;gap:var(--space-2);align-items:end}
@media (max-width: 959px){
  .assets-split{grid-template-columns:minmax(0,1fr)}
}
</style>
