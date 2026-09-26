<script setup lang="ts">
// 资产检查面板（PLAN-DM-042 / SPEC-DM-016 §8.1–§8.2）：单文件受控路径、资产身份、
// 引用关系、最近检查结果与重新检查动作。布局表按「已启用 / 未启用 / 启用但缺失」三态
// 呈现勾选图幅与实际布局的包含关系（精确字符串比较；Model 永不参与）；未勾选的布局
// 只是不启用，不再是问题。PAPER_LAYOUT_MISSING 诊断由三态表呈现，不在诊断列表重复。
import {computed} from "vue";
import UiButton from "../ui/UiButton.vue";
import {
  MODEL_LAYOUT_NAME,
  PAPER_LAYOUT_MISSING_CODE,
  declaredPaperLayouts,
  missingPaperLayouts,
  nonModelLayouts,
  type AssetReference,
  type InspectionState,
} from "../../features/standards/publishModel";
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

const checked = computed(() => declaredPaperLayouts(props.asset));
const actual = computed(() => nonModelLayouts(props.inspection?.layouts ?? []));
const missing = computed(() => missingPaperLayouts(checked.value, actual.value));

type LayoutRowState = "enabled" | "not-enabled" | "missing";

/** 布局表行：勾选在前、实际布局补充在后，每行给出三态之一。 */
const layoutRows = computed<Array<{name: string; state: LayoutRowState}>>(() =>
  [...checked.value, ...actual.value.filter(name => !checked.value.includes(name))].map(name => ({
    name,
    state: checked.value.includes(name)
      ? (actual.value.includes(name) ? "enabled" : "missing")
      : "not-enabled",
  })),
);

function stateText(state: LayoutRowState): string {
  if (state === "enabled") return "standards.assets.layoutEnabled";
  if (state === "missing") return "standards.assets.layoutMissing";
  return "standards.assets.layoutNotEnabled";
}

/** 勾选图幅在文件中缺失的问题已由三态表逐项呈现，诊断列表不再重复。 */
const visibleDiagnostics = computed(() =>
  (props.inspection?.diagnostics ?? []).filter(diagnostic => diagnostic.code !== PAPER_LAYOUT_MISSING_CODE),
);
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
      <p class="path-value">{{ asset.file || "—" }}</p>
      <p v-if="asset.file === ''" class="panel-note">{{ $t("standards.assets.noFiles") }}</p>
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
      <!-- 无可用结果（未检查或检查失败）时不得给出「启用但缺失」这类结构性结论 -->
      <p v-else-if="state === 'unchecked' || state === 'error'" class="panel-note" data-testid="asset-layout-unchecked">
        {{ $t("standards.assets.uncheckedDiagnostics") }}
      </p>
      <template v-else>
        <table class="layout-table">
          <thead>
            <tr>
              <th scope="col">{{ $t("standards.assets.paperLayouts") }}</th>
              <th scope="col">{{ $t("standards.assets.stateLabel") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in layoutRows" :key="row.name" :data-testid="`asset-layout-${row.name}`">
              <td>{{ row.name }}</td>
              <td><span class="layout-state" :class="row.state">{{ $t(stateText(row.state)) }}</span></td>
            </tr>
            <tr v-if="layoutRows.length === 0">
              <td colspan="2" class="panel-note">{{ $t("standards.assets.noLayouts") }}</td>
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
      <ul v-else-if="visibleDiagnostics.length > 0" class="diagnostic-list" role="alert">
        <li v-for="(diagnostic, index) in visibleDiagnostics" :key="index" :data-testid="`asset-diagnostic-${index}`">
          {{ $t(`standards.diagnostic.${diagnostic.code}`, {assetId: asset.asset_id}) }}
        </li>
      </ul>
      <p v-else-if="(inspection?.diagnostics ?? []).length > 0" class="panel-note">
        {{ $t("standards.assets.diagnosticsFiltered") }}
      </p>
      <p v-else class="panel-note">{{ $t("standards.assets.noDiagnostics") }}</p>
      <p v-if="!failure && state !== 'unchecked' && missing.length > 0" class="panel-error" role="alert">
        {{ $t(`standards.diagnostic.${PAPER_LAYOUT_MISSING_CODE}`, {assetId: asset.asset_id, layout: missing.join("、")}) }}
      </p>
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
.path-value,.reference-list{font-size:var(--font-label);color:var(--color-text-primary)}
.path-value{margin:0;word-break:break-all}
.reference-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.layout-table{width:100%;border-collapse:collapse;table-layout:fixed}
.layout-table th,.layout-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left;font-size:var(--font-label);word-break:break-all}
.layout-table th{color:var(--color-text-secondary);font-weight:500}
.layout-state{color:var(--color-text-primary)}
.layout-state.not-enabled{color:var(--color-text-secondary)}
.layout-state.missing{color:var(--color-danger)}
.diagnostic-list{margin:0;padding-left:var(--space-4);color:var(--color-danger);font-size:var(--font-label)}
</style>
