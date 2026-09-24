<script setup lang="ts">
// 资产检查面板（PLAN-DM-035 Task 10 / SPEC-DM-016 §8.1–§8.2）：受控路径、资产身份、
// 引用关系、最近检查结果与重新检查动作。布局资产列出检查到的非 Model 布局，并与声明图幅
// 严格比较（不去空格、不转换大小写）；缺失与未声明都逐项显示。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import {declaredRoles, nonModelLayouts, compareLayouts, MODEL_LAYOUT_NAME, type AssetReference, type InspectionState} from "../../features/standards/publishModel";
import type {DraftAsset} from "../../features/standards/draftModel";
import type {AssetInspection} from "../../features/standards/types";
import type {InspectionFailure} from "../../features/standards/publishModel";

const props = defineProps<{
  asset: DraftAsset;
  /** 官方参考资产只读：面板不提供声明编辑，只呈现检查与引用。 */
  source: "user" | "official";
  /** 当前检查状态：未检查/检查失败/检查有问题/检查通过（F07：无结果不得当作“未发现问题”）。 */
  state: InspectionState;
  inspection?: AssetInspection;
  failure?: InspectionFailure;
  inspectedAt: string;
  pending: boolean;
  references: AssetReference[];
}>();
const emit = defineEmits<{recheck: []}>();

const declared = computed(() => declaredRoles(props.asset));
const actual = computed(() => nonModelLayouts(props.inspection?.layouts ?? []));
const diff = computed(() => compareLayouts(declared.value, actual.value));

function layoutState(name: string): "matched" | "missing" | "extra" {
  if (diff.value.missing.includes(name)) return "missing";
  if (diff.value.extra.includes(name)) return "extra";
  return "matched";
}
</script>
<template>
  <section class="inspection-panel" role="region" :aria-label="$t('standards.assets.panelTitle')" data-testid="asset-panel">
    <header class="panel-header">
      <div>
        <h4 class="panel-title">{{ $t("standards.assets.panelTitle") }}</h4>
        <p class="panel-identity" data-testid="asset-identity">
          {{ asset.asset_id }} · {{ $t(asset.kind === "layout-template" ? "standards.assets.kindLayout" : "standards.assets.kindBase") }}
          · {{ $t(source === "official" ? "standards.assets.sourceOfficialBadge" : "standards.assets.sourceUserBadge") }}
        </p>
      </div>
      <UiButton variant="secondary" :loading="pending" :disabled="source === 'official'" @click="emit('recheck')">
        {{ $t("standards.assets.inspect") }}
      </UiButton>
    </header>
    <p class="panel-note" role="status">
      {{ inspectedAt === "" ? $t("standards.assets.notInspected") : $t("standards.assets.inspectedAt", {time: inspectedAt}) }}
    </p>
    <div class="panel-block">
      <h5 class="block-title">{{ $t("standards.assets.paths") }}</h5>
      <ul class="path-list">
        <li v-for="(file, index) in asset.files" :key="index" class="path-row">
          <span class="path-value">{{ file.path || "—" }}</span>
          <span class="path-role">{{ file.role || "—" }}</span>
        </li>
      </ul>
      <p v-if="asset.files.length === 0" class="panel-note">{{ $t("standards.assets.noFiles") }}</p>
    </div>
    <div class="panel-block">
      <h5 class="block-title">{{ $t("standards.assets.referenceTitle") }}</h5>
      <p class="panel-note">{{ $t("standards.assets.referenceCount", {count: references.length}) }}</p>
      <ul v-if="references.length > 0" class="reference-list">
        <li v-for="(reference, index) in references" :key="index">
          {{ $t(`standards.assets.reference.${reference.kind}`, {ref: reference.ref, value: reference.value}) }}
        </li>
      </ul>
      <p v-else class="panel-note">{{ $t("standards.assets.noReference") }}</p>
    </div>
    <div class="panel-block">
      <h5 class="block-title">{{ $t("standards.assets.layoutsTitle") }}</h5>
      <p class="panel-note">{{ $t("standards.assets.modelExcluded", {model: MODEL_LAYOUT_NAME}) }}</p>
      <p v-if="pending" class="panel-note">{{ $t("standards.assets.inspectPending") }}</p>
      <p v-else-if="state === 'unchecked'" class="panel-note" data-testid="asset-layout-unchecked">
        {{ $t("standards.assets.uncheckedDiagnostics") }}
      </p>
      <template v-else>
        <table class="layout-table">
          <thead>
            <tr>
              <th scope="col">{{ $t("standards.assets.layoutDeclared") }}</th>
              <th scope="col">{{ $t("standards.assets.layoutActual") }}</th>
              <th scope="col">{{ $t("standards.assets.stateLabel") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in declared" :key="`declared-${role}`" :data-testid="`asset-layout-${role}`">
              <td>{{ role }}</td>
              <td>{{ actual.join(", ") || "—" }}</td>
              <td>
                <span class="layout-state" :class="layoutState(role)">
                  {{ $t(layoutState(role) === "matched" ? "standards.assets.layoutMatched" : "standards.assets.layoutMissing") }}
                </span>
              </td>
            </tr>
            <tr v-for="(name, index) in diff.extra" :key="`extra-${name}`" :data-testid="`asset-layout-extra-${index}`">
              <td>—</td>
              <td>{{ name }}</td>
              <td><span class="layout-state extra">{{ $t("standards.assets.layoutExtra") }}</span></td>
            </tr>
            <tr v-if="declared.length === 0 && actual.length === 0">
              <td colspan="3" class="panel-note">{{ $t("standards.assets.noLayouts") }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
    <div class="panel-block">
      <h5 class="block-title">{{ $t("standards.assets.diagnostics") }}</h5>
      <p v-if="failure" class="panel-error" role="alert" data-testid="asset-failure">
        {{ $t("standards.assets.failure", {message: failure.message}) }}
      </p>
      <p v-else-if="state === 'unchecked'" class="panel-note" data-testid="asset-unchecked">
        {{ $t("standards.assets.uncheckedDiagnostics") }}
      </p>
      <ul v-else-if="(inspection?.diagnostics ?? []).length > 0" class="diagnostic-list" role="alert">
        <li v-for="(diagnostic, index) in inspection?.diagnostics ?? []" :key="index" :data-testid="`asset-diagnostic-${index}`">
          {{ $t(`standards.diagnostic.${diagnostic.code}`, {layout: declared[0] ?? "", assetId: asset.asset_id}) }}
        </li>
      </ul>
      <p v-else class="panel-note">{{ $t("standards.assets.noDiagnostics") }}</p>
    </div>
  </section>
</template>
<style scoped>
.inspection-panel{display:grid;gap:var(--space-3);min-width:0}
.panel-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-2);flex-wrap:wrap}
.panel-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.panel-identity{margin:var(--space-1) 0 0;color:var(--color-text-primary);word-break:break-all}
.panel-note{margin:0;font-size:var(--font-label);color:var(--color-text-muted)}
.panel-error{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.panel-block{display:grid;gap:var(--space-1)}
.block-title{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.path-list,.reference-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);font-size:var(--font-label);color:var(--color-text-primary)}
.path-row{display:flex;gap:var(--space-2);justify-content:space-between;word-break:break-all}
.path-role{color:var(--color-text-secondary)}
.layout-table{width:100%;border-collapse:collapse;table-layout:fixed}
.layout-table th,.layout-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;font-size:var(--font-label);word-break:break-all}
.layout-table th{color:var(--color-text-secondary);font-weight:500}
.layout-state{color:var(--color-text-primary)}
.layout-state.missing,.layout-state.extra{color:var(--color-danger)}
.diagnostic-list{margin:0;padding-left:var(--space-4);color:var(--color-danger);font-size:var(--font-label)}
</style>
