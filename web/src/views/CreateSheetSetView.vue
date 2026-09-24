<script setup lang="ts">
// 四阶段创建向导（SPEC-DM-018 §2–§5；PLAN-DM-036 Task 8）。
// 本任务实现前三阶段（选择标准 → 项目信息 → 图纸组）与全量 XLSX 导入；第四阶段
// 「检查并创建」的权威预览与执行由 Task 9 接入，这里只把四阶段壳与导航补齐。
// 页面只做编排：输入状态在 `features/creation/store.ts`，纯模型在 `inputModel.ts`，
// 各阶段界面在 `components/creation/`。前端不复制属性求值、编号、DWG 命名规则。
import {computed, onMounted, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../components/ui/UiButton.vue";
import StandardStep from "../components/creation/StandardStep.vue";
import ProjectStep from "../components/creation/ProjectStep.vue";
import GroupsStep from "../components/creation/GroupsStep.vue";
import XlsxImportDialog from "../components/creation/XlsxImportDialog.vue";
import {creationApi} from "../api/creation";
import {createCreationStore} from "../features/creation/store";
import type {ConfirmOptions} from "../composables/useConfirm";
import type {CreationStandardCandidate, CreationStep} from "../features/creation/types";
import type {StandardIdentity} from "../features/standards/types";

const props = defineProps<{
  confirmAction: (options: ConfirmOptions) => Promise<boolean>;
  /** 标准详情「用于创建」的一次性意图：固定该发布版本并直接进入第二阶段。 */
  entryIdentity?: StandardIdentity | null;
}>();
const emit = defineEmits<{back: []; standards: []}>();
const {t} = useI18n();

const store = createCreationStore(creationApi, {
  defaultFolderName: t("creation.project.folderDefault"),
});

// 四阶段固定顺序与后端 `CREATION_STEPS` 同口径；第一阶段只在尚未建立草稿时出现
const STEPS: CreationStep[] = ["standard", "project", "groups", "review"];
const STEP_KEYS: Record<CreationStep, string> = {
  standard: "creation.wizard.stepStandard",
  project: "creation.wizard.stepProject",
  groups: "creation.wizard.stepGroups",
  review: "creation.wizard.stepReview",
};
// 可恢复创建草稿：草稿 ID 记在本地（桌面壳 localStorage），恢复与放弃都由本页编排
const DRAFT_KEY = "dst-manager.creation-draft-id";
const stepIndex = computed(() => STEPS.indexOf(store.step));
const resumeVisible = ref(false);
const xlsxOpen = ref(false);
const hasStandard = computed(() => store.draftId !== "");
// 各阶段可返回修改：第二阶段可退回第一阶段重新选标准（切换时会提示并清除不兼容输入）
const canGoBack = computed(() => hasStandard.value && stepIndex.value > 0);
const canGoNext = computed(
  () => hasStandard.value && stepIndex.value >= 1 && stepIndex.value < STEPS.length - 1,
);
const stepLabels = computed(() => STEPS.map(step => t(STEP_KEYS[step])));
const fixedStandard = computed(() => {
  const identity = store.standard?.identity;
  if (identity === undefined || identity === null) return "";
  const name = store.standard?.name ?? "";
  // 名称缺失（标准详情入口指向的版本不在候选列表内）时以标准 ID 兜底，ID 始终可见
  return t("creation.wizard.fixedStandard", {
    name: name === "" ? identity.standardId : name,
    id: identity.standardId,
    version: identity.version,
  });
});

function readStoredDraftId(): string {
  try {
    return window.localStorage.getItem(DRAFT_KEY) ?? "";
  } catch {
    // 存储不可用（隐私模式等）：不阻断向导，只是失去跨会话恢复
    return "";
  }
}

function writeStoredDraftId(draftId: string): void {
  try {
    if (draftId === "") window.localStorage.removeItem(DRAFT_KEY);
    else window.localStorage.setItem(DRAFT_KEY, draftId);
  } catch {
    // 同上：本地身份写入失败不影响当前会话内的草稿操作
  }
}

// 草稿身份由 store 产生；本页只负责把它记到本地，供重新进入时提示「继续草稿」。
// 刻意不加 `immediate`：构造期的空 `draftId` 不是「放弃草稿」，立即写回会先清掉本地身份，
// 恢复流程随后就找不到草稿了；恢复失败与「重新开始」由本页显式清除。
watch(() => store.draftId, draftId => writeStoredDraftId(draftId));

/** 标准候选：列表里没有（例如详情入口指向的版本依赖不可用）时按身份合成一个空候选。 */
function candidateFor(identity: StandardIdentity): CreationStandardCandidate {
  const found = store.candidates.find(
    item => item.standard_id === identity.standardId && item.version === identity.version,
  );
  if (found !== undefined) return found;
  return {
    standard_id: identity.standardId,
    version: identity.version,
    name: "",
    supported_cad_versions: [],
    available: true,
    reasons: [],
    asset_options: [],
  };
}

async function confirmSwitchStandard(): Promise<boolean> {
  return props.confirmAction({
    title: t("creation.wizard.switchTitle"),
    message: t("creation.wizard.switchMessage"),
    confirmText: t("creation.wizard.switchConfirm"),
    cancelText: t("creation.wizard.cancel"),
    danger: true,
  });
}

/** 选择标准：同身份直接进入第二阶段；不同身份先确认再清除不兼容输入（不静默迁移）。 */
async function useStandard(candidate: CreationStandardCandidate): Promise<void> {
  const current = store.standard?.identity ?? null;
  const same =
    current !== null &&
    current.standardId === candidate.standard_id &&
    current.version === candidate.version;
  if (hasStandard.value && !same) {
    if (!(await confirmSwitchStandard())) return;
    await store.chooseStandard(candidate, {replace: true});
    return;
  }
  await store.chooseStandard(candidate);
}

/** 标准详情入口：固定版本后直接进入第二阶段；已有其他标准的草稿先确认再切换。 */
async function enterFromIdentity(identity: StandardIdentity): Promise<void> {
  const storedId = readStoredDraftId();
  if (storedId !== "") {
    const resumed = await store.resumeDraft(storedId);
    if (resumed) {
      const current = store.standard?.identity ?? null;
      if (current !== null && current.standardId === identity.standardId && current.version === identity.version) {
        await store.goToStep("project");
        return;
      }
      if (!(await confirmSwitchStandard())) return;
      if (!(await store.restart())) return;
    } else {
      writeStoredDraftId("");
    }
  }
  await store.chooseStandard(candidateFor(identity));
}

onMounted(async () => {
  await store.loadCandidates();
  if (props.entryIdentity !== undefined && props.entryIdentity !== null) {
    await enterFromIdentity(props.entryIdentity);
    return;
  }
  const storedId = readStoredDraftId();
  if (storedId === "") return;
  if (await store.resumeDraft(storedId)) resumeVisible.value = true;
  // 草稿已不存在或固定标准不可用：清掉本地身份，从第一阶段重新开始
  else writeStoredDraftId("");
});

function dismissResume(): void {
  resumeVisible.value = false;
}

async function restart(): Promise<void> {
  const confirmed = await props.confirmAction({
    title: t("creation.wizard.resumeConfirmTitle"),
    message: t("creation.wizard.resumeConfirmMessage"),
    confirmText: t("creation.wizard.resumeConfirmText"),
    cancelText: t("creation.wizard.cancel"),
    danger: true,
  });
  if (!confirmed) return;
  if (!(await store.restart())) return;
  resumeVisible.value = false;
  xlsxOpen.value = false;
}

/** 离开向导前先落盘：未保存的输入不得因返回欢迎页而静默丢失。 */
async function backToWelcome(): Promise<void> {
  await store.save();
  emit("back");
}
</script>
<template>
  <section class="create-wizard" role="region" :aria-label="$t('creation.wizard.region')">
    <header class="wizard-head">
      <div>
        <h1>{{ $t("creation.wizard.title") }}</h1>
        <p>{{ $t("creation.wizard.lead") }}</p>
      </div>
      <div class="wizard-actions">
        <span v-if="fixedStandard !== ''" class="badge" data-testid="creation-fixed-standard">{{ fixedStandard }}</span>
        <UiButton variant="secondary" :disabled="!hasStandard" @click="xlsxOpen = true">
          {{ $t("creation.xlsx.open") }}
        </UiButton>
        <UiButton variant="secondary" :disabled="!hasStandard" @click="restart">
          {{ $t("creation.wizard.restart") }}
        </UiButton>
        <UiButton variant="secondary" @click="backToWelcome">{{ $t("creation.wizard.backToWelcome") }}</UiButton>
      </div>
    </header>
    <nav class="stepper" :aria-label="$t('creation.wizard.stepsLabel')" data-testid="creation-stepper">
      <div
        v-for="(label, index) in stepLabels" :key="label" class="step"
        :class="{current: index === stepIndex, done: index < stepIndex}"
        :aria-current="index === stepIndex ? 'step' : undefined"
      >
        <span class="step-number" aria-hidden="true">{{ index + 1 }}</span>
        <span class="step-label">{{ label }}</span>
      </div>
    </nav>
    <p v-if="resumeVisible" class="banner" role="status" data-testid="creation-resume-banner">
      {{ $t("creation.wizard.resumeBanner", {step: stepLabels[stepIndex]}) }}
      <button type="button" @click="dismissResume">{{ $t("creation.wizard.resumeContinue") }}</button>
      <button type="button" @click="restart">{{ $t("creation.wizard.resumeRestart") }}</button>
    </p>
    <p v-if="store.error !== ''" class="banner error" role="alert" data-testid="creation-error">{{ store.error }}</p>
    <p v-if="store.pending" class="banner" role="status">{{ $t("creation.wizard.saving") }}</p>
    <StandardStep
      v-if="store.step === 'standard'"
      :store="store" @use="useStandard" @open-standards="emit('standards')"
    />
    <ProjectStep v-else-if="store.step === 'project'" :store="store" />
    <GroupsStep v-else-if="store.step === 'groups'" :store="store" />
    <section v-else class="card review-pending" role="region" :aria-label="$t('creation.wizard.stepPendingTitle')">
      <h2>{{ $t("creation.wizard.stepPendingTitle") }}</h2>
      <p>{{ $t("creation.wizard.stepPendingDesc") }}</p>
    </section>
    <footer class="wizard-foot">
      <UiButton variant="secondary" :disabled="!canGoBack" @click="store.goToStep(STEPS[stepIndex - 1] ?? 'standard')">
        {{ $t("creation.wizard.back") }}
      </UiButton>
      <UiButton variant="primary" :disabled="!canGoNext" @click="store.goToStep(STEPS[stepIndex + 1] ?? store.step)">
        {{ $t("creation.wizard.next") }}
      </UiButton>
    </footer>
    <XlsxImportDialog
      :store="store" :open="xlsxOpen" :confirm-action="confirmAction"
      @close="xlsxOpen = false"
    />
  </section>
</template>
<style scoped>
.create-wizard{width:100%;max-width:var(--shell-content-max-width,1200px);margin:0 auto;padding:var(--space-5);display:grid;gap:var(--space-4)}
.wizard-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}
.wizard-head h1{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.wizard-head p{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.wizard-actions{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap}
.badge{font-size:var(--font-caption);padding:var(--space-1) var(--space-2);border-radius:var(--radius-full);color:var(--color-info);background:var(--color-info-bg);font-family:var(--font-mono)}
.stepper{display:flex;gap:var(--space-2);flex-wrap:wrap;list-style:none;margin:0;padding:var(--space-3);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.step{display:flex;align-items:center;gap:var(--space-2);padding:var(--space-1) var(--space-3);border-radius:var(--radius-full);color:var(--color-text-muted);font-size:var(--font-label)}
.step.current{color:var(--color-on-accent);background:var(--color-accent)}
.step.done{color:var(--color-success)}
.step-number{display:inline-grid;place-items:center;width:var(--space-5);height:var(--space-5);border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-caption)}
.step.current .step-number{background:var(--color-on-accent);color:var(--color-accent)}
.banner{margin:0;display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;padding:var(--space-3);border-radius:var(--radius-md);background:var(--color-info-bg);color:var(--color-text-primary);font-size:var(--font-label)}
.banner.error{background:var(--color-danger-bg);color:var(--color-danger)}
.banner button{font-size:var(--font-label);padding:var(--space-1) var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg)}
.review-pending h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.review-pending p{margin:var(--space-2) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.7}
.wizard-foot{display:flex;justify-content:flex-end;gap:var(--space-2)}
</style>
