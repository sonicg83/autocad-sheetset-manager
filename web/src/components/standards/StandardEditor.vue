<script setup lang="ts">
// 标准草稿编辑器壳层（PLAN-DM-038 Task 9 / SPEC-DM-017 §2、§7）。
// 顶部固定显示标准名称、草稿标识、最近保存状态、「保存草稿」和「发布检查」；左侧六分区导航，
// 右侧只渲染当前分区。草稿采用直接保存模型：clean 用可聚焦的语义禁用（aria-disabled），
// dirty-valid 可保存，dirty-invalid 优先显示具体错误并禁止保存；保存成功后以服务端响应建立
// 新的可信基准。有未保存修改时离开编辑器走共享三选一门禁。
//
// 两段门禁：结构致命错误进保存门禁（`draftDiagnostics`），全部 error 进发布门禁
// （`publishIssues`）。草稿允许保存语义未完成的内容，发布前必须补齐。
//
// 缓冲所有权：本组件持有唯一可编辑缓冲（buffer），各分区组件共享同一对象就地修改，
// 因此分区切换不丢输入；未知顶层字段原样保留，保存时不丢数据。
import {computed, nextTick, ref, watch} from "vue";
import {ApiError} from "../../api/client";
import {i18n} from "../../i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UnsavedInputDialog from "../ui/UnsavedInputDialog.vue";
import StandardSectionNav from "./StandardSectionNav.vue";
import OrdinaryPropertyEditor from "./OrdinaryPropertyEditor.vue";
import DerivedPropertyEditor from "./DerivedPropertyEditor.vue";
import DwgNamingEditor from "./DwgNamingEditor.vue";
import TemplateAssetsEditor from "./TemplateAssetsEditor.vue";
import StandardPublishReview from "./StandardPublishReview.vue";
import {
  cloneDocument,
  draftDiagnostics,
  EDITOR_SECTIONS,
  isDerivedProperty,
  publishIssues,
  toDraftDocument,
  type DraftAsset,
  type DraftDiagnostic,
  type DraftDocument,
  type EditorSectionId,
  type PropertyReference,
} from "../../features/standards/draftModel";
import type {InspectionFailure, InspectionRecord, PublishTarget} from "../../features/standards/publishModel";
import {
  inspectionRecordMatches,
  inspectionRunIsCurrent,
  recordFailure,
  recordInspection,
  recordInspectedAt,
} from "../../features/standards/publishModel";
import type {AssetInspection, CopiedAssetFile, StandardDraft} from "../../features/standards/types";

type GuardChoice = "save" | "discard" | "stay";

/** 只在模态框里可修复的发布问题：跳转时直接打开对应模态框。 */
const MODAL_CODES = new Set([
  "STANDARD_MAPPING_TARGET_EMPTY",
  "STANDARD_MAPPING_SOURCE_DUPLICATE",
  "STANDARD_MAPPING_CONFIRMATION_REQUIRED",
]);

const props = defineProps<{
  draft: StandardDraft;
  /** 保存回写：成功时返回服务端文档（作为新的可信基准），失败时抛出。 */
  saveDraft: (document: Record<string, unknown>) => Promise<Record<string, unknown>>;
  /** 资产检查：按草稿与资产标识调用后端固定读取协议。 */
  inspectAsset: (assetId: string, cadVersion: string) => Promise<AssetInspection>;
  /** 本机模板受控复制：成功时返回受控副本路径与按需读取的非 Model 布局。 */
  copyAssetFile: (sourcePath: string, cadVersion: string) => Promise<CopiedAssetFile>;
  /** 发布：成功时后端已把草稿移入已发布目录（草稿不复存在）。 */
  publishDraft: () => Promise<void>;
  /** 官方标准的资产声明（只读参考）；无可对照官方标准时为空数组。 */
  officialAssets?: DraftAsset[];
  officialStandardId?: string;
}>();
const emit = defineEmits<{close: []}>();

// 基线必须与缓冲经过同一规范化：否则刚加载就会因补齐 `dwg_naming` 等默认键而被误判为
// 有未保存修改（假 dirty 会让保存按钮在白名单文档上提前可点）。
const baselineDocument = toDraftDocument(cloneDocument(props.draft.document));
const buffer = ref<DraftDocument>(toDraftDocument(cloneDocument(baselineDocument)));
const baseline = ref(JSON.stringify(baselineDocument));
const active = ref<EditorSectionId>("basic");
const saving = ref(false);
const saveError = ref("");
const guardOpen = ref(false);
/** 编辑分区视图与发布检查页（SPEC-DM-017 §7 的独立检查页）。 */
const view = ref<"sections" | "review">("sections");
/** 最近一次资产检查记录：绑定草稿身份与已保存快照，过期一律按“未检查”处理。 */
const inspectionRecord = ref<InspectionRecord | null>(null);
const inspectionPending = ref(false);
const publishPending = ref(false);
const publishError = ref("");
const deleteBlocked = ref("");
/** 检查运行代次：乱序返回时只接受最新一次运行的结果。 */
let inspectionGeneration = 0;
const focusRequest = ref<{
  section: EditorSectionId;
  propertyId?: string;
  itemId?: string;
  segmentIndex?: number;
  openEditor?: boolean;
} | null>(null);
let guardResolver: ((choice: GuardChoice) => void) | null = null;

// 同一草稿重新加载（相同 draft_id）不重置缓冲，避免覆盖用户正在进行的输入
watch(
  () => props.draft.draft_id,
  () => {
    buffer.value = toDraftDocument(cloneDocument(props.draft.document));
    baseline.value = JSON.stringify(buffer.value);
    saveError.value = "";
    deleteBlocked.value = "";
    // 切换草稿：在途检查作废（结果本来也会因身份不符而被判为过期）
    inspectionGeneration += 1;
    inspectionPending.value = false;
  },
);

const snapshot = computed(() => JSON.stringify(buffer.value));
const dirty = computed(() => snapshot.value !== baseline.value);
const diagnostics = computed<DraftDiagnostic[]>(() => draftDiagnostics(buffer.value));
const reviewIssues = computed<DraftDiagnostic[]>(() => publishIssues(buffer.value));
const invalid = computed(() => diagnostics.value.length > 0);
const sectionCounts = computed<Record<string, number>>(() => ({
  ordinary: buffer.value.properties.filter(
    property => property.kind === "text" || property.kind === "enum",
  ).length,
  derived: buffer.value.properties.filter(isDerivedProperty).length,
  dwgNaming: buffer.value.dwg_naming.segments.length > 0 ? 1 : 0,
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
/** 资产编辑器复制入口：附上当前 CAD 版本，复制后立即读取非 Model 布局供勾选。 */
function copyAssetFileWithVersion(sourcePath: string): Promise<CopiedAssetFile> {
  return props.copyAssetFile(sourcePath, cadVersion.value);
}
/** 打开编辑器时固定的草稿身份（F03）：检查与发布只用它，不从列表选择反推。 */
const draftId = computed(() => props.draft.draft_id);

/** 当前有效的检查记录：草稿身份或当前文档快照不匹配时按“未检查”处理。
 *  用缓冲快照（而非已保存基准）比对：编辑缓冲后发布将先落盘，旧结果不再对应将要发布的文档。 */
const currentRecord = computed<InspectionRecord | null>(() =>
  inspectionRecordMatches(inspectionRecord.value, draftId.value, snapshot.value)
    ? inspectionRecord.value
    : null,
);
const inspections = computed<AssetInspection[]>(() => currentRecord.value?.inspections ?? []);
const inspectionFailures = computed<InspectionFailure[]>(() => currentRecord.value?.failures ?? []);
const inspectedAt = computed(() => recordInspectedAt(currentRecord.value));

// 进入资产分区或发布检查页时自动做一次检查（尚未取得当前结果才跑）
watch([active, view], () => {
  if (view.value === "review") return; // 检查页自行触发并等待结果
  if (active.value !== "assets") return;
  if (currentRecord.value !== null || inspectionPending.value) return;
  void runInspections();
});

/** 诊断 → 分区定位：按诊断归属决定分区（属性按普通/派生再分）。 */
function sectionOfDiagnostic(item: DraftDiagnostic): EditorSectionId {
  if (item.owner === "asset") return "assets";
  if (item.owner === "dwgNaming") return "dwgNaming";
  if (item.owner === "document") return "basic";
  const property = buffer.value.properties.find(
    candidate => candidate.property_id === item.propertyId,
  );
  return property !== undefined && isDerivedProperty(property) ? "derived" : "ordinary";
}

async function jumpToDiagnostic(item: DraftDiagnostic): Promise<void> {
  view.value = "sections";
  const section = sectionOfDiagnostic(item);
  active.value = section;
  deleteBlocked.value = "";
  focusRequest.value = {
    section,
    propertyId: item.propertyId,
    itemId: item.itemId,
    segmentIndex: item.segmentIndex,
    openEditor: MODAL_CODES.has(item.code),
  };
  await nextTick();
}

/** 发布检查页的问题跳转：回到对应分区并聚焦属性行、派生模态框或命名令牌。 */
async function jumpFromReview(target: PublishTarget): Promise<void> {
  view.value = "sections";
  active.value = target.section;
  deleteBlocked.value = "";
  focusRequest.value = {
    section: target.section,
    propertyId: target.propertyId,
    itemId: target.itemId,
    segmentIndex: target.segmentIndex,
    openEditor: target.itemId !== undefined,
  };
  await nextTick();
}

/** 删除保护：分区组件已经就地提示，壳层再汇总一次引用方名称（滚动后仍可见）。 */
function onDeleteBlocked(payload: {propertyId: string; references: PropertyReference[]}): void {
  const owners = payload.references.map(reference => {
    if (reference.kind === "dwgNaming") return targetText("standards.ordinary.namingOwner");
    const owner = buffer.value.properties.find(item => item.property_id === reference.ownerId);
    return owner === undefined ? reference.ownerId : owner.name || reference.ownerId;
  });
  deleteBlocked.value = targetText("standards.ordinary.deleteBlocked", {
    count: owners.length,
    owners: [...new Set(owners)].join(targetText("standards.enumDialog.nameSeparator")),
  });
}

/**
 * 资产检查（PLAN-DM-040 Task 4）：先保证检查对象是**已保存**文档，再用代次与快照
 * 身份提交结果。结构无效或保存失败一律不发起检查并显示原因（不把旧结果显示为当前结果）。
 */
async function runInspections(): Promise<void> {
  if (inspectionPending.value) return;
  publishError.value = "";
  if (invalid.value) {
    publishError.value = targetText("standards.assets.inspectBlockedInvalid");
    return;
  }
  if (dirty.value && !(await save())) {
    // 保存失败：保留输入与 dirty 状态，检查停在旧快照上（结果会被判为过期）
    publishError.value = saveError.value || targetText("standards.assets.inspectBlockedSaveFailed");
    return;
  }
  const run = {
    generation: ++inspectionGeneration,
    draftId: draftId.value,
    documentSnapshot: snapshot.value,
  };
  inspectionPending.value = true;
  const results: AssetInspection[] = [];
  const failures: InspectionFailure[] = [];
  try {
    for (const asset of buffer.value.assets) {
      if (cadVersion.value === "") {
        failures.push({assetId: asset.asset_id, message: targetText("standards.assets.cadVersionMissing")});
        continue;
      }
      try {
        results.push(await props.inspectAsset(asset.asset_id, cadVersion.value));
      } catch (error) {
        failures.push({assetId: asset.asset_id, message: errorMessage(error)});
      }
    }
  } finally {
    inspectionPending.value = false;
  }
  const stillCurrent = inspectionRunIsCurrent(run, {
    generation: inspectionGeneration,
    draftId: draftId.value,
    documentSnapshot: snapshot.value,
  });
  if (!stillCurrent) return; // 乱序返回或检查期间继续编辑：丢弃本次结果
  inspectionRecord.value = {
    draftId: run.draftId,
    documentSnapshot: run.documentSnapshot,
    inspectedAt: new Date().toLocaleString(),
    inspections: results,
    failures,
  };
}

async function openReview(): Promise<void> {
  publishError.value = "";
  view.value = "review";
  await runInspections();
}

/** 发布：未保存修改先落盘；检查结果不对应当前快照时先重新检查，仍不一致则阻断。 */
async function publish(): Promise<void> {
  if (publishPending.value) return;
  publishError.value = "";
  if (dirty.value) {
    const saved = await save();
    if (!saved) return;
  }
  if (currentRecord.value === null) {
    await runInspections();
    if (currentRecord.value === null) {
      publishError.value = targetText("standards.assets.inspectBlockedStale");
      return;
    }
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

/** 三选一离开门禁（SPEC-DM-015 §5）：有未保存修改才拦截。 */
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

function targetText(key: string, params?: Record<string, string | number>): string {
  return i18n.global.t(key, params ?? {});
}

defineExpose({guard, isDirty: () => dirty.value});
</script>
<template>
  <section class="standard-editor" role="region" :aria-label="$t('standards.editor.region')">
    <!-- 三层结构（PLAN-DM-039 Task 2，对照 SPEC-DM-017 编辑器 Demo）：
         ① 标题栏：编辑标准 · {name}、说明与保存状态；
         ② 身份区：标准名称、草稿/版本标识与保存、发布检查、返回；
         ③ 工作区：左分区导航 + 右侧独立边框的内容面板。 -->
    <header class="editor-titlebar">
      <div>
        <h2 class="editor-heading">{{ $t("standards.editor.titleLabel") }} · {{ buffer.name }}</h2>
        <p class="editor-subtitle">{{ $t("standards.editor.subtitle") }}</p>
      </div>
      <p class="save-state" role="status" data-testid="editor-save-state">{{ $t(saveStateText) }}</p>
    </header>
    <div class="editor-identity">
      <UiInput v-model="buffer.name" :label="$t('standards.editor.nameLabel')" />
      <p class="draft-id">{{ $t("standards.editor.draftId") }}：{{ draft.draft_id }}</p>
      <div class="header-actions">
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
    </div>
    <p v-if="saveError" class="editor-error" role="alert" data-testid="editor-save-error">{{ $t("standards.editor.saveFailed", {message: saveError}) }}</p>
    <p v-if="deleteBlocked && view === 'sections'" class="editor-error" role="alert" data-testid="editor-delete-blocked">
      {{ deleteBlocked }}
    </p>
    <template v-if="view === 'review'">
      <StandardPublishReview
        :document="buffer"
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
            {{ $t(`standards.diagnostic.${item.code}`, {segment: item.segmentIndex === undefined ? "" : item.segmentIndex + 1, field: item.detail ?? "", source: item.detail ?? ""}) }}
          </button>
        </li>
      </ul>
    </div>
    <p v-else class="structure-ok" role="status">{{ $t("standards.editor.structureOk") }}</p>
    <div class="editor-workspace" data-testid="standards-editor-workspace" role="region" :aria-label="$t('standards.editor.workspaceRegion')">
      <StandardSectionNav class="editor-nav" :active="active" :sections="sections" @select="active = $event; deleteBlocked = ''" />
      <div class="editor-panel">
        <div class="editor-panel-body">
        <section v-if="active === 'basic'" class="basic-section" role="region" :aria-label="$t('standards.sections.basic')">
          <h3 class="section-title">{{ $t("standards.sections.basic") }}</h3>
          <!-- 身份由草稿本身决定：只读并在可见说明里给出原因（F11） -->
          <UiInput :model-value="buffer.standard_id" :label="$t('standards.detail.standardId')" readonly />
          <p class="identity-note" role="note" data-testid="identity-readonly-note">{{ $t("standards.editor.identityReadonlyHint") }}</p>
          <p class="pending-note" role="note" data-testid="version-assigned-note">{{ $t("standards.publish.versionAssignedByServer") }}</p>
          <UiInput v-model="cadVersionsText" :label="$t('standards.editor.cadVersionsLabel')" />
        </section>
        <OrdinaryPropertyEditor
          v-else-if="active === 'ordinary'"
          :document="buffer"
          :diagnostics="reviewIssues"
          :focus-request="focusRequest"
          @delete-blocked="onDeleteBlocked"
        />
        <DerivedPropertyEditor
          v-else-if="active === 'derived'"
          :document="buffer"
          :diagnostics="reviewIssues"
          :focus-request="focusRequest"
          @delete-blocked="onDeleteBlocked"
        />
        <DwgNamingEditor
          v-else-if="active === 'dwgNaming'"
          :document="buffer"
          :diagnostics="reviewIssues"
          :focus-request="focusRequest"
        />
        <TemplateAssetsEditor
          v-else-if="active === 'assets'"
          :document="buffer"
          :official-assets="officialAssets ?? []"
          :official-standard-id="officialStandardId ?? ''"
          :record="currentRecord"
          :pending="inspectionPending"
          :cad-version="cadVersion"
          :copy-asset-file="copyAssetFileWithVersion"
          @recheck="runInspections"
        />
        <section v-else class="publish-section" role="region" :aria-label="$t('standards.sections.publish')">
          <h3 class="section-title">{{ $t("standards.sections.publish") }}</h3>
          <p class="pending-note" role="note" data-testid="publish-version-note">{{ $t("standards.publish.versionAssignedByServer") }}</p>
          <UiButton variant="secondary" @click="openReview">{{ $t("standards.editor.publishCheck") }}</UiButton>
        </section>
        </div>
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
.editor-titlebar{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-4);flex-wrap:wrap;padding:var(--space-4) var(--space-4) 0}
.editor-heading{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.editor-subtitle{margin:var(--space-1) 0 0;font-size:var(--font-label);color:var(--color-text-secondary);line-height:1.6}
.save-state{margin:0;font-size:var(--font-label);color:var(--color-text-secondary);padding:var(--space-1) var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);white-space:nowrap}
.editor-identity{display:flex;align-items:flex-end;gap:var(--space-4);flex-wrap:wrap;padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);background:var(--color-bg-surface)}
.editor-identity :deep(.ui-input){flex:1 1 280px;min-width:0}
.draft-id{margin:0;font-size:var(--font-label);color:var(--color-text-secondary);white-space:nowrap}
.header-actions{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;margin-left:auto}
.editor-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
.structure-summary{display:grid;gap:var(--space-1)}
.summary-title{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.summary-list{list-style:none;margin:0;padding:0;display:flex;gap:var(--space-2);flex-wrap:wrap}
.summary-button{min-height:var(--min-tap-height);padding:var(--space-1) var(--space-2);border:1px solid var(--color-danger);border-radius:var(--radius-md);background:var(--color-danger-bg);color:var(--color-danger);cursor:pointer;font-size:var(--font-label)}
.structure-ok{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
/* 独立全宽工作台：238px 分区导航 + 自适应内容面板（SPEC-DM-017 编辑器 Demo） */
.editor-workspace{display:grid;grid-template-columns:238px minmax(0,1fr);gap:var(--space-4);align-items:start}
.editor-nav{position:sticky;top:0}
/* 分级响应式（PLAN-DM-039 Task 3，对照 SPEC-DM-017 编辑器 Demo）：
   标准视口 238px 导航；1050px 以下收窄到 210px；780px 以下才堆叠为单列。 */
@media (max-width: 1050px){
  .editor-workspace{grid-template-columns:210px minmax(0,1fr)}
}
@media (max-width: 780px){
  .editor-workspace{grid-template-columns:minmax(0,1fr)}
  .editor-nav{position:static}
}
.editor-panel{min-width:0;border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);background:var(--color-bg-surface)}
.editor-panel-body{padding:var(--space-4)}
.basic-section{display:grid;gap:var(--space-2);max-width:var(--card-max-width)}
.identity-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.publish-section{display:grid;gap:var(--space-2);max-width:var(--card-max-width)}
.section-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.pending-note{display:flex;align-items:center;gap:var(--space-2);margin:0;padding:var(--space-3);border:1px dashed var(--color-border-strong);border-radius:var(--radius-md);font-size:var(--font-label);color:var(--color-text-secondary)}
</style>
