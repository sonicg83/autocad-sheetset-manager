<script setup lang="ts">
// 模板资产编辑器（PLAN-DM-042 / SPEC-DM-016 §8.1）：基础/布局为主分类，官方/用户为筛选器，
// 列表显示名称、来源、状态与引用数；右侧为检查面板与编辑区。官方资产只读。
//
// 单文件结构：一个资产只对应一个 DWG/DWT 文件（包内受控副本名）。桌面壳可用时经固定
// `template` 文件种类选择本机文件，由后端复制进草稿受控目录并顺带读取非 Model 布局；
// 无壳本地开发态提供单独标明的「来源绝对路径」输入，调用同一端点。启用图幅不是手工输入，
// 而是从复制或检查读取到的布局中勾选声明；切换种类会清空勾选。
import {computed, ref, watch} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import AssetInspectionPanel from "./AssetInspectionPanel.vue";
import {ApiError} from "../../api/client";
import {i18n} from "../../i18n";
import {selectTemplatePath, shellReady} from "../../api/shell";
import {ASSET_KINDS, type DraftAsset, type DraftDocument} from "../../features/standards/draftModel";
import {
  MODEL_LAYOUT_NAME,
  assetReferences,
  nonModelLayouts,
  recordFailure,
  recordInspection,
  recordInspectionState,
  recordInspectedAt,
  type AssetReference,
  type InspectionFailure,
  type InspectionRecord,
  type InspectionState,
} from "../../features/standards/publishModel";
import type {AssetInspection, CopiedAssetFile} from "../../features/standards/types";

const props = defineProps<{
  document: DraftDocument;
  /** 官方标准的资产声明（只读参考）；无可对照官方标准时为空数组。 */
  officialAssets: DraftAsset[];
  officialStandardId: string;
  /** 当前有效的检查记录（已绑定草稿身份与已保存快照）；无有效记录时为 null。 */
  record: InspectionRecord | null;
  pending: boolean;
  cadVersion: string;
  /** 受控复制：把本机来源复制进草稿，返回包内相对路径与读取到的布局（失败抛出）。 */
  copyAssetFile: (sourcePath: string) => Promise<CopiedAssetFile>;
}>();
const emit = defineEmits<{recheck: []}>();

const sourceFilter = ref<"all" | "official" | "user">("all");
const selectedKey = ref<string | null>(null);
/** 无桌面壳时的来源绝对路径输入与就地错误（单值，切换资产时丢弃）。 */
const sourcePath = ref("");
const fileError = ref("");
const copying = ref(false);
/** 复制成功时按资产 ID 记录读取到的布局（跨选中切换保留，重新复制或删除资产时更新）。 */
const copiedLayouts = ref<Record<string, string[]>>({});
/** 复制成功但布局读取失败时按资产 ID 记录错误码。 */
const layoutsErrors = ref<Record<string, string>>({});

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

/** 可勾选的布局：复制读取、检查读取与已勾选的并集（排除 Model 与空串，保序去重）。 */
const availableLayouts = computed<string[]>(() => {
  const asset = selected.value?.asset;
  if (asset === undefined) return [];
  const seen = new Set<string>();
  const names: string[] = [];
  const push = (name: string): void => {
    if (name === "" || name === MODEL_LAYOUT_NAME || seen.has(name)) return;
    seen.add(name);
    names.push(name);
  };
  for (const name of copiedLayouts.value[asset.asset_id] ?? []) push(name);
  for (const name of nonModelLayouts(inspectionOf(asset.asset_id)?.layouts ?? [])) push(name);
  for (const name of asset.paper_layouts) push(name);
  return names;
});

function nextAssetId(kind: string): string {
  const used = new Set(props.document.assets.map(asset => asset.asset_id));
  const base = kind === "layout-template" ? "layout-template" : "base-template";
  let index = 1;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

function addAsset(kind: string): void {
  const asset: DraftAsset = {asset_id: nextAssetId(kind), kind, file: "", paper_layouts: []};
  props.document.assets.push(asset);
  selectedKey.value = `user/${asset.asset_id}`;
}

function removeAsset(asset: DraftAsset): void {
  const index = props.document.assets.indexOf(asset);
  if (index >= 0) props.document.assets.splice(index, 1);
  const copied = {...copiedLayouts.value};
  delete copied[asset.asset_id];
  copiedLayouts.value = copied;
  const errors = {...layoutsErrors.value};
  delete errors[asset.asset_id];
  layoutsErrors.value = errors;
  selectedKey.value = null;
}

/** 改名时迁移按资产 ID 键控的会话态，避免改名后丢失复制读取的布局。 */
function renameAsset(asset: DraftAsset, value: unknown): void {
  const previous = asset.asset_id;
  asset.asset_id = String(value);
  if (asset.asset_id === previous) return;
  if (copiedLayouts.value[previous] !== undefined) {
    const moved = {...copiedLayouts.value};
    moved[asset.asset_id] = moved[previous];
    delete moved[previous];
    copiedLayouts.value = moved;
  }
  if (layoutsErrors.value[previous] !== undefined) {
    const moved = {...layoutsErrors.value};
    moved[asset.asset_id] = moved[previous];
    delete moved[previous];
    layoutsErrors.value = moved;
  }
  selectedKey.value = `user/${asset.asset_id}`;
}

/** 种类切换即清空勾选：启用图幅只对布局模板有意义，且必须来自当前文件的布局。 */
function onKindChange(asset: DraftAsset, event: Event): void {
  const kind = (event.target as HTMLSelectElement).value;
  if (kind === asset.kind) return;
  asset.kind = kind;
  asset.paper_layouts = [];
}

function toggleLayout(asset: DraftAsset, name: string, checked: boolean): void {
  if (checked) {
    if (!asset.paper_layouts.includes(name)) asset.paper_layouts = [...asset.paper_layouts, name];
  } else {
    asset.paper_layouts = asset.paper_layouts.filter(item => item !== name);
  }
}

function selectAllLayouts(asset: DraftAsset): void {
  asset.paper_layouts = [...availableLayouts.value];
}

function clearAllLayouts(asset: DraftAsset): void {
  asset.paper_layouts = [];
}

// 切换选中资产时丢弃单值的临时输入与错误（不把上一个资产的输入带到下一个）
watch(
  () => (selected.value === null ? "" : rowKey(selected.value)),
  () => {
    sourcePath.value = "";
    fileError.value = "";
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

/** 有壳：固定 `template` 文件种类选择本机文件；取消不发请求。 */
async function pickTemplate(asset: DraftAsset): Promise<void> {
  const picked = await selectTemplatePath(targetText("standards.assets.templateDialogDescription"));
  if (picked === undefined || picked === null) return;
  await applyCopy(asset, picked);
}

/** 无壳：显式来源绝对路径，调用同一受控复制端点。 */
async function copyFromPath(asset: DraftAsset): Promise<void> {
  const source = sourcePath.value.trim();
  if (source === "") {
    fileError.value = targetText("standards.assets.sourcePathRequired");
    return;
  }
  await applyCopy(asset, source);
}

/** 只有复制成功才修改编辑缓冲；失败保留旧声明与 dirty 状态并就地显示错误。 */
async function applyCopy(asset: DraftAsset, source: string): Promise<void> {
  if (copying.value) return;
  copying.value = true;
  fileError.value = "";
  try {
    const copied = await props.copyAssetFile(source);
    asset.file = copied.path;
    const id = asset.asset_id;
    if (copied.layouts_error !== null && copied.layouts_error !== "") {
      const cleared = {...copiedLayouts.value};
      delete cleared[id];
      copiedLayouts.value = cleared;
      layoutsErrors.value = {...layoutsErrors.value, [id]: copied.layouts_error};
    } else {
      const cleared = {...layoutsErrors.value};
      delete cleared[id];
      layoutsErrors.value = cleared;
      copiedLayouts.value = {...copiedLayouts.value, [id]: copied.layouts};
    }
  } catch (error) {
    fileError.value = errorText(error);
  } finally {
    copying.value = false;
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
          <select :id="`asset-kind-${selected.asset.asset_id}`" :value="selected.asset.kind" class="field-select" @change="onKindChange(selected.asset, $event)">
            <option v-for="kind in ASSET_KINDS" :key="kind" :value="kind">
              {{ $t(kind === "layout-template" ? "standards.assets.kindLayout" : "standards.assets.kindBase") }}
            </option>
          </select>
          <div class="file-block">
            <h5 class="group-title">{{ $t("standards.assets.paths") }}</h5>
            <div class="file-row">
              <UiInput
                :model-value="selected.asset.file"
                :label="$t('standards.assets.filePath')"
                :hint="$t('standards.assets.filePathHint')"
                :placeholder="$t('standards.assets.filePathPlaceholder')"
                readonly
                data-testid="asset-file-path"
              />
              <div class="file-actions">
                <UiButton
                  v-if="shellReady"
                  variant="secondary"
                  :loading="copying"
                  data-testid="asset-file-pick"
                  @click="pickTemplate(selected.asset)"
                >{{ selected.asset.file === "" ? $t("standards.assets.chooseTemplate") : $t("standards.assets.replaceFile") }}</UiButton>
                <template v-else>
                  <UiInput
                    :model-value="sourcePath"
                    :label="$t('standards.assets.sourcePathLabel')"
                    :hint="$t('standards.assets.sourcePathHint')"
                    data-testid="asset-file-source"
                    @update:model-value="(value: string) => sourcePath = value"
                  />
                  <UiButton
                    variant="secondary"
                    :loading="copying"
                    data-testid="asset-file-copy"
                    @click="copyFromPath(selected.asset)"
                  >{{ selected.asset.file === "" ? $t("standards.assets.copyTemplate") : $t("standards.assets.replaceFile") }}</UiButton>
                </template>
              </div>
            </div>
            <p v-if="fileError" class="file-error" role="alert" data-testid="asset-file-error">{{ fileError }}</p>
          </div>
          <div v-if="selected.asset.kind === 'layout-template'" class="paper-block">
            <div class="paper-header">
              <h5 class="group-title">{{ $t("standards.assets.paperLayouts") }}</h5>
              <div class="paper-actions">
                <UiButton variant="secondary" data-testid="asset-layout-select-all" @click="selectAllLayouts(selected.asset)">
                  {{ $t("standards.assets.selectAll") }}
                </UiButton>
                <UiButton variant="secondary" data-testid="asset-layout-clear-all" @click="clearAllLayouts(selected.asset)">
                  {{ $t("standards.assets.clearAll") }}
                </UiButton>
              </div>
            </div>
            <p class="section-note">{{ $t("standards.assets.paperLayoutsHint") }}</p>
            <p v-if="layoutsErrors[selected.asset.asset_id]" class="file-error" role="alert">
              {{ $t("standards.assets.layoutsReadFailed", {code: layoutsErrors[selected.asset.asset_id]}) }}
            </p>
            <div v-if="availableLayouts.length > 0" class="paper-list" data-testid="asset-paper-layouts">
              <label v-for="name in availableLayouts" :key="name" class="layout-hit">
                <input
                  type="checkbox"
                  class="layout-check"
                  :checked="selected.asset.paper_layouts.includes(name)"
                  :data-testid="`asset-paper-layout-${name}`"
                  @change="toggleLayout(selected.asset, name, ($event.target as HTMLInputElement).checked)"
                />
                <span class="layout-name">{{ name }}</span>
              </label>
            </div>
            <p v-else class="section-note" data-testid="asset-paper-layouts-empty">{{ $t("standards.assets.paperLayoutsUnavailable") }}</p>
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
.file-block{display:grid;gap:var(--space-1)}
.file-row{display:grid;grid-template-columns:minmax(0,2fr) auto;gap:var(--space-2);align-items:end}
.file-actions{display:grid;gap:var(--space-2);align-items:end;min-width:0}
.file-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
.paper-block{display:grid;gap:var(--space-1);padding-top:var(--space-2);border-top:1px solid var(--color-border-subtle)}
.paper-header{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);flex-wrap:wrap}
.paper-actions{display:flex;gap:var(--space-2);flex-wrap:wrap}
.paper-list{display:flex;flex-wrap:wrap;gap:var(--space-1)}
.layout-hit{display:inline-flex;align-items:center;gap:var(--space-2);min-height:var(--tap-target-min);padding:0 var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface);cursor:pointer}
.layout-hit:hover{background:var(--color-bg-muted)}
.layout-check{box-sizing:border-box;width:var(--checkbox-size);height:var(--checkbox-size);margin:0;padding:0;flex:none}
.layout-name{font-size:var(--font-label);color:var(--color-text-primary)}
@media (max-width: 959px){
  .assets-split{grid-template-columns:minmax(0,1fr)}
}
</style>
