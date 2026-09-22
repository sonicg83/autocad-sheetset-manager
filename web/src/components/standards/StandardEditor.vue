<script setup lang="ts">
// 标准草稿编辑器壳层（PLAN-DM-035 Task 9 / SPEC-DM-016 §6）：顶部固定显示标准名称、
// 草稿标识、最近保存状态、“保存草稿”和“发布检查”；左侧分区导航，右侧只渲染当前分区。
// 草稿采用直接保存模型（SPEC-DM-015 §5）：clean 用可聚焦的语义禁用（aria-disabled），
// dirty-valid 可保存，dirty-invalid 优先显示具体错误并禁止保存；保存成功后以服务端响应
// 建立新的可信基准。有未保存修改时离开编辑器走共享三选一门禁。
//
// 缓冲所有权：本组件持有唯一可编辑缓冲（buffer），各分区组件共享同一对象就地修改，
// 因此分区切换不丢输入；未知顶层字段原样保留，保存时不丢数据。
import {computed, nextTick, ref, watch} from "vue";
import {ApiError} from "../../api/client";
import {i18n} from "../../i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UnsavedInputDialog from "../ui/UnsavedInputDialog.vue";
import StandardSectionNav from "./StandardSectionNav.vue";
import StandardPropertyEditor from "./StandardPropertyEditor.vue";
import StandardRulesEditor from "./StandardRulesEditor.vue";
import MappingTableEditor from "./MappingTableEditor.vue";
import CompositionEditor from "./CompositionEditor.vue";
import TemplateAssetsEditor from "./TemplateAssetsEditor.vue";
import StandardPublishReview from "./StandardPublishReview.vue";
import {
  cloneDocument,
  EDITOR_SECTIONS,
  ORDINARY_RULE_KINDS,
  COMPOSITION_RULE_KINDS,
  toDraftDocument,
  validateDraftStructure,
  type DraftAsset,
  type DraftDocument,
  type EditorSectionId,
  type StructureDiagnostic,
} from "../../features/standards/draftModel";
import type {InspectionFailure, PublishTarget} from "../../features/standards/publishModel";
import type {AssetInspection, StandardDraft} from "../../features/standards/types";

type GuardChoice = "save" | "discard" | "stay";

const props = defineProps<{
  draft: StandardDraft;
  /** 保存回写：成功时返回服务端文档（作为新的可信基准），失败时抛出。 */
  saveDraft: (document: Record<string, unknown>) => Promise<Record<string, unknown>>;
  /** 资产检查：按草稿与资产标识调用后端固定读取协议。 */
  inspectAsset: (assetId: string, cadVersion: string) => Promise<AssetInspection>;
  /** 发布：成功时后端已把草稿移入已发布目录（草稿不复存在）。 */
  publishDraft: () => Promise<void>;
  /** 官方标准的资产声明（只读参考）；无可对照官方标准时为空数组。 */
  officialAssets?: DraftAsset[];
  officialStandardId?: string;
}>();
const emit = defineEmits<{close: []}>();

// 基线必须与缓冲经过同一规范化：否则刚加载就会因补齐 `dependencies` 等默认键而被误判为
// 有未保存修改（假 dirty 会让保存按钮在白名单文档上提前可点）。
const baselineDocument = toDraftDocument(cloneDocument(props.draft.document));
const buffer = ref<DraftDocument>(toDraftDocument(cloneDocument(baselineDocument)));
const baseline = ref(JSON.stringify(baselineDocument));
const active = ref<EditorSectionId>("basic");
const saving = ref(false);
const saveError = ref("");
const guardOpen = ref(false);
/** 编辑分区视图与发布检查页（SPEC-DM-016 §9.1 的独立检查页）。 */
const view = ref<"sections" | "review">("sections");
const inspections = ref<AssetInspection[]>([]);
const inspectionFailures = ref<InspectionFailure[]>([]);
const inspectionPending = ref(false);
const inspectedAt = ref("");
const publishPending = ref(false);
const publishError = ref("");
const focusRequest = ref<{section: EditorSectionId; ruleId?: string; row?: number | null} | null>(null);
let guardResolver: ((choice: GuardChoice) => void) | null = null;

// 同一草稿重新加载（相同 draft_id）不重置缓冲，避免覆盖用户正在进行的输入
watch(
  () => props.draft.draft_id,
  () => {
    buffer.value = toDraftDocument(cloneDocument(props.draft.document));
    baseline.value = JSON.stringify(buffer.value);
    saveError.value = "";
  },
);

const snapshot = computed(() => JSON.stringify(buffer.value));
const dirty = computed(() => snapshot.value !== baseline.value);
const diagnostics = computed<StructureDiagnostic[]>(() => validateDraftStructure(buffer.value));
const invalid = computed(() => diagnostics.value.length > 0);
const sectionCounts = computed<Record<string, number>>(() => ({
  properties: buffer.value.properties.length,
  rules: buffer.value.rules.filter(rule => ORDINARY_RULE_KINDS.includes(rule.kind)).length,
  mapping: buffer.value.rules.filter(rule => rule.kind === "mapping").length,
  composition: buffer.value.rules.filter(rule => COMPOSITION_RULE_KINDS.includes(rule.kind)).length,
  assets: buffer.value.assets.length,
}));
const sections = computed(() =>
  EDITOR_SECTIONS.map(section => ({...section, count: sectionCounts.value[section.id]})),
);
const saveStateText = computed(() => {
  if (saving.value) return "standards.editor.saving";
  if (invalid.value) return "standards.editor.invalidHint";
  // clean = 缓冲与可信基准一致：草稿已保存，无需写操作（直接保存模型）
  return dirty.value ? "standards.editor.dirtyHint" : "standards.editor.saved";
});
const cadVersionsText = computed({
  get: () => buffer.value.supported_cad_versions.join(", "),
  set: (value: string) => {
    buffer.value.supported_cad_versions = String(value).split(",").map(item => item.trim()).filter(Boolean);
  },
});
/** 版本说明：草稿文档的自由文本字段（不进入领域 Schema，随草稿本体保存与导出）。 */
const releaseNotes = computed({
  get: () => typeof buffer.value.release_notes === "string" ? buffer.value.release_notes : "",
  set: (value: string) => { buffer.value.release_notes = value; },
});
const cadVersion = computed(() => buffer.value.supported_cad_versions[0] ?? "");

// 进入资产分区或发布检查页时自动做一次检查（尚未检查过才跑），避免面板停在「尚未检查」
watch([active, view], () => {
  if (view.value === "review") return; // 检查页自行触发并等待结果
  if (active.value !== "assets") return;
  if (inspectedAt.value !== "" || inspectionPending.value) return;
  void runInspections();
});

/** 诊断 → 分区定位：按规则种类决定跳转分区，行级诊断带上行号。 */
function sectionOfDiagnostic(item: StructureDiagnostic): EditorSectionId {
  const rule = buffer.value.rules.find(candidate => candidate.rule_id === item.ruleId);
  if (rule === undefined) return "rules";
  if (rule.kind === "mapping") return "mapping";
  if (COMPOSITION_RULE_KINDS.includes(rule.kind)) return "composition";
  return "rules";
}

async function jumpToDiagnostic(item: StructureDiagnostic): Promise<void> {
  const section = sectionOfDiagnostic(item);
  active.value = section;
  focusRequest.value = {section, ruleId: item.ruleId, row: item.row ?? null};
  await nextTick();
  if (section === "mapping") return; // 行内组件自行聚焦（行号或未覆盖摘要）
  focusRequest.value = null;
}

/** 发布检查页的问题跳转：回到对应分区并聚焦到映射行/未覆盖摘要。 */
async function jumpFromReview(target: PublishTarget): Promise<void> {
  view.value = "sections";
  active.value = target.section;
  focusRequest.value = target.section === "mapping"
    ? {section: "mapping", ruleId: target.ruleId, row: target.row ?? null}
    : null;
  await nextTick();
}

/** 资产检查：逐个声明资产调用后端固定读取协议；检查失败与标准错误分开记录。 */
async function runInspections(): Promise<void> {
  if (inspectionPending.value) return;
  inspectionPending.value = true;
  inspections.value = [];
  const failures: InspectionFailure[] = [];
  for (const asset of buffer.value.assets) {
    if (cadVersion.value === "") {
      failures.push({assetId: asset.asset_id, message: targetText("standards.assets.cadVersionMissing")});
      continue;
    }
    try {
      inspections.value = [...inspections.value, await props.inspectAsset(asset.asset_id, cadVersion.value)];
    } catch (error) {
      failures.push({assetId: asset.asset_id, message: errorMessage(error)});
    }
  }
  inspectionFailures.value = failures;
  inspectedAt.value = new Date().toLocaleString();
  inspectionPending.value = false;
}

async function openReview(): Promise<void> {
  publishError.value = "";
  view.value = "review";
  await runInspections();
}

/** 发布：未保存修改先落盘（发布的是服务端草稿），失败保留在检查页。 */
async function publish(): Promise<void> {
  if (publishPending.value) return;
  publishError.value = "";
  if (dirty.value) {
    const saved = await save();
    if (!saved) return;
  }
  publishPending.value = true;
  try {
    // 发布成功后由父层完成导航（退出编辑器 + 定位新版本只读详情），此处不自行切视图
    await props.publishDraft();
  } catch (error) {
    publishError.value = errorMessage(error);
  } finally {
    publishPending.value = false;
  }
}

async function save(): Promise<boolean> {
  if (saving.value || invalid.value || !dirty.value) return false;
  saving.value = true;
  saveError.value = "";
  try {
    const saved = await props.saveDraft({...buffer.value});
    buffer.value = toDraftDocument(cloneDocument(saved));
    baseline.value = JSON.stringify(buffer.value);
    return true;
  } catch (error) {
    // 保存失败/修订冲突保留输入与 dirty 状态，只呈现错误（不静默覆盖）
    const conflict = error instanceof ApiError && error.code === "STANDARD_VERSION_IMMUTABLE"
      ? `｜${targetText("standards.editor.conflictHint")}`
      : "";
    saveError.value = `${errorMessage(error)}${conflict}`;
    return false;
  } finally {
    saving.value = false;
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    // 未知错误只给本地化摘要：把稳定码与后端原始文本一并展示，否则无法定位被拒绝的具体原因
    const detail = error.rawMessage || error.message;
    return error.code ? `${error.code}｜${detail}` : detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

/** 三选一离开门禁（SPEC-DM-015 §5 / SPEC-DM-016 §6.1）：有未保存修改才拦截。 */
async function guard(next: () => void | Promise<void>): Promise<void> {
  if (guardOpen.value) return;
  if (!dirty.value) {
    await next();
    return;
  }
  guardOpen.value = true;
  const choice = await new Promise<GuardChoice>(resolve => { guardResolver = resolve; });
  guardOpen.value = false;
  guardResolver = null;
  if (choice === "stay") return;
  if (choice === "discard") {
    buffer.value = toDraftDocument(cloneDocument(JSON.parse(baseline.value) as Record<string, unknown>));
    saveError.value = "";
    await next();
    return;
  }
  const saved = await save();
  if (!saved) return; // 保存失败不能继续离开
  await next();
}

function resolveGuard(choice: GuardChoice): void {
  guardResolver?.(choice);
}

function targetText(key: string): string {
  return i18n.global.t(key);
}

defineExpose({guard, isDirty: () => dirty.value});
</script>
<template>
  <section class="standard-editor" role="region" :aria-label="$t('standards.editor.region')">
    <header class="editor-header">
      <div class="identity">
        <p class="draft-id">{{ $t("standards.editor.draftId") }}：{{ draft.draft_id }}</p>
        <UiInput v-model="buffer.name" :label="$t('standards.editor.nameLabel')" />
      </div>
      <div class="header-actions">
        <p class="save-state" role="status" data-testid="editor-save-state">{{ $t(saveStateText) }}</p>
        <UiButton
          variant="secondary"
          :loading="saving"
          :disabled="invalid"
          :aria-disabled="!dirty && !saving"
          @click="save"
        >{{ $t("standards.editor.saveDraft") }}</UiButton>
        <UiButton v-if="view === 'sections'" variant="secondary" @click="openReview">
          {{ $t("standards.editor.publishCheck") }}
        </UiButton>
        <UiButton variant="secondary" @click="guard(() => emit('close'))">{{ $t("standards.editor.back") }}</UiButton>
      </div>
    </header>
    <p v-if="saveError" class="editor-error" role="alert" data-testid="editor-save-error">{{ $t("standards.editor.saveFailed", {message: saveError}) }}</p>
    <template v-if="view === 'review'">
      <StandardPublishReview
        :document="buffer"
        :structure="diagnostics"
        :assets="inspections"
        :inspection-failures="inspectionFailures"
        :inspection-pending="inspectionPending"
        :publish-pending="publishPending"
        :publish-error="publishError"
        :release-notes="releaseNotes"
        @publish="publish"
        @close="view = 'sections'"
        @recheck="runInspections"
        @jump="jumpFromReview"
        @update:release-notes="releaseNotes = $event"
      />
    </template>
    <template v-else>
    <div v-if="diagnostics.length > 0" class="structure-summary">
      <p class="summary-title" role="status">{{ $t("standards.editor.structureSummary", {count: diagnostics.length}) }}</p>
      <ul class="summary-list">
        <li v-for="(item, index) in diagnostics" :key="index">
          <button
            type="button"
            class="summary-button"
            :data-testid="`structure-diagnostic-${index}`"
            @click="jumpToDiagnostic(item)"
          >
            {{ $t(`standards.diagnostic.${item.code}`, {field: item.field ?? "", row: item.row ?? ""}) }}
          </button>
        </li>
      </ul>
    </div>
    <p v-else class="structure-ok" role="status">{{ $t("standards.editor.structureOk") }}</p>
    <div class="editor-split">
      <StandardSectionNav :active="active" :sections="sections" @select="active = $event" />
      <div class="editor-body">
        <section v-if="active === 'basic'" class="basic-section" role="region" :aria-label="$t('standards.sections.basic')">
          <h3 class="section-title">{{ $t("standards.sections.basic") }}</h3>
          <UiInput v-model="buffer.standard_id" :label="$t('standards.detail.standardId')" />
          <UiInput v-model="buffer.version" :label="$t('standards.editor.versionLabel')" />
          <UiInput v-model="cadVersionsText" :label="$t('standards.editor.cadVersionsLabel')" />
        </section>
        <StandardPropertyEditor v-else-if="active === 'properties'" :document="buffer" />
        <StandardRulesEditor v-else-if="active === 'rules'" :document="buffer" :diagnostics="diagnostics" />
        <MappingTableEditor
          v-else-if="active === 'mapping'"
          :document="buffer"
          :focus-request="focusRequest"
        />
        <CompositionEditor v-else-if="active === 'composition'" :document="buffer" :diagnostics="diagnostics" />
        <TemplateAssetsEditor
          v-else-if="active === 'assets'"
          :document="buffer"
          :official-assets="officialAssets ?? []"
          :official-standard-id="officialStandardId ?? ''"
          :inspections="inspections"
          :inspection-failures="inspectionFailures"
          :inspected-at="inspectedAt"
          :pending="inspectionPending"
          :cad-version="cadVersion"
          @recheck="runInspections"
        />
        <section v-else class="publish-section" role="region" :aria-label="$t('standards.sections.publish')">
          <h3 class="section-title">{{ $t("standards.sections.publish") }}</h3>
          <UiInput :model-value="buffer.version" :label="$t('standards.publish.versionLabel')" disabled />
          <p class="pending-note" role="note">{{ $t("standards.publish.versionHint") }}</p>
          <UiButton variant="secondary" @click="openReview">{{ $t("standards.editor.publishCheck") }}</UiButton>
        </section>
      </div>
    </div>
    </template>
    <UnsavedInputDialog
      :open="guardOpen"
      :summary="$t('standards.editor.unsavedSummary')"
      :message="$t('standards.editor.unsavedMessage', {summary: $t('standards.editor.unsavedSummary')})"
      :save-label="$t('standards.editor.saveAndLeave')"
      :can-save="!invalid"
      @save-and-continue="resolveGuard('save')"
      @discard="resolveGuard('discard')"
      @stay="resolveGuard('stay')"
    />
  </section>
</template>
<style scoped>
.standard-editor{display:grid;gap:var(--space-3);min-width:0}
.editor-header{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap;padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);background:var(--color-bg-surface)}
.identity{display:grid;gap:var(--space-1);flex:1}
.draft-id{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.header-actions{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.save-state{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.editor-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
.structure-summary{display:grid;gap:var(--space-1)}
.summary-title{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.summary-list{list-style:none;margin:0;padding:0;display:flex;gap:var(--space-2);flex-wrap:wrap}
.summary-button{min-height:var(--min-tap-height);padding:var(--space-1) var(--space-2);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);cursor:pointer;font-size:var(--font-label)}
.structure-ok{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.editor-split{display:grid;grid-template-columns:minmax(200px,260px) minmax(0,1fr);gap:var(--space-4);align-items:start}
.editor-body{display:grid;gap:var(--space-3);min-width:0}
.basic-section{display:grid;gap:var(--space-2);max-width:var(--card-max-width)}
.publish-section{display:grid;gap:var(--space-2);max-width:var(--card-max-width)}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.pending-note{display:flex;align-items:center;gap:var(--space-2);margin:0;padding:var(--space-3);border:1px dashed var(--color-border-strong);border-radius:var(--radius-md);font-size:var(--font-label);color:var(--color-text-secondary)}
@media (max-width: 959px){
  .editor-split{grid-template-columns:minmax(0,1fr)}
}
</style>
