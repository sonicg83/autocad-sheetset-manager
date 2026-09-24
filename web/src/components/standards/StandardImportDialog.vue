<script setup lang="ts">
// 标准包导入弹窗（PLAN-DM-041 Task 7）：唯一导入入口，覆盖「选择文件 → 预检 →
// 确认导入」三步与全部可见状态。桌面壳用固定种类 `dststandard` 的原生选择器并只读
// 显示已选路径；无桌面壳的本地开发态改用明确标注的本机路径输入（同一预检端点）。
// 渲染层不复制任何后端规则：可否导入、诊断与候选身份全部来自预检响应。
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import {FOCUSABLE_SELECTOR, useDialogFocus} from "../ui/dialogFocus";
import {formatStandardVersion} from "./standardLibraryModel";
import type {
  ImportPreviewResult,
  PublishedStandard,
} from "../../features/standards/types";

const props = defineProps<{
  open: boolean;
  /** 桌面壳可用（桥已就绪）；为 false 时显示明确标注的本机路径开发态回退。 */
  shellAvailable: boolean;
  /** 原生选择：undefined = 桥不可用（切到开发态回退），null = 用户取消，string = 选中路径。 */
  selectPath: (localizedDescription: string) => Promise<string | null | undefined>;
  previewImport: (path: string) => Promise<ImportPreviewResult>;
  confirmImport: (previewId: string) => Promise<PublishedStandard>;
  cancelImport: (previewId: string) => Promise<void>;
}>();
const emit = defineEmits<{close: []; imported: [standard: PublishedStandard]}>();

const {t} = useI18n();

type ImportPhase = "idle" | "previewing" | "confirmable" | "blocked" | "importing" | "success";

const card = ref<HTMLElement | null>(null);
const path = ref("");
const phase = ref<ImportPhase>("idle");
const result = ref<ImportPreviewResult | null>(null);
const errorText = ref("");
/** 无壳回退模式：桥不可用或被显式降级时显示路径输入（挂载即按当前桥状态求值）。 */
const devFallback = ref(!props.shellAvailable);
const now = ref(Date.now());
let expiryTimer: ReturnType<typeof setInterval> | null = null;

// 焦点契约（PLAN-DM-040 Task 9 同源）：初始焦点是弹窗内首个停靠点，Tab/Shift+Tab
// 圈闭，Escape 关闭并归还焦点。Escape 走关闭流程，确保在途预检凭证被清理。
const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  onEscape: event => {
    event.stopPropagation();
    void close();
  },
});

// 欢迎页「导入标准包」会以 open=true 直接挂载本组件；此时 useDialogFocus 的
// immediate 初始聚焦执行时刻容器尚未渲染，焦点会留在弹窗外，导致 Tab 圈闭与
// Escape 同时静默失效（modal 可见却不可键盘操作）。容器就绪后补一次聚焦。
onMounted(async () => {
  await nextTick();
  if (!props.open) return;
  if (card.value === null) return;
  if (card.value.contains(document.activeElement)) return;
  card.value.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus({preventScroll: true});
});

function stopExpiryTimer(): void {
  if (expiryTimer !== null) {
    clearInterval(expiryTimer);
    expiryTimer = null;
  }
}

/** 丢弃当前预检：尽力取消服务端凭证与快照，并清空本地预检状态。 */
async function dropPreview(): Promise<void> {
  const current = result.value;
  result.value = null;
  if (current?.preview_id != null) {
    try {
      await props.cancelImport(current.preview_id);
    } catch {
      // 取消失败只影响快照清理时机（服务端过期后自会清理），不阻断用户操作
    }
  }
}

function expired(): boolean {
  if (result.value?.expires_at == null) return false;
  return new Date(result.value.expires_at).getTime() <= now.value;
}

function reset(): void {
  stopExpiryTimer();
  path.value = "";
  phase.value = "idle";
  result.value = null;
  errorText.value = "";
  // 桥迟到注入后必须离开无壳模式：每次打开按当前桥状态重算。
  devFallback.value = !props.shellAvailable;
}

watch(
  () => props.open,
  open => {
    if (open) reset();
    else {
      stopExpiryTimer();
      void dropPreview();
    }
  },
  {immediate: true},
);

// 桥迟到注入（pywebviewready）：桥可用时离开开发态回退，改走原生选择器。
watch(
  () => props.shellAvailable,
  available => {
    if (available) devFallback.value = false;
  },
);

const canPreview = computed(
  () => path.value.trim().length > 0 && phase.value !== "previewing" && phase.value !== "importing",
);
const canConfirm = computed(() => phase.value === "confirmable" && result.value?.preview_id != null);
const busy = computed(() => phase.value === "previewing" || phase.value === "importing");

function startExpiryTimer(): void {
  stopExpiryTimer();
  now.value = Date.now();
  expiryTimer = setInterval(() => {
    now.value = Date.now();
    if (expired()) {
      // 凭证过期即清除旧预检：确认按钮随之不可用，用户必须重新预检。
      void dropPreview();
      phase.value = "idle";
      errorText.value = t("standards.import.expired");
      stopExpiryTimer();
    }
  }, 15000);
}

async function chooseFile(): Promise<void> {
  const picked = await props.selectPath(t("standards.import.pickTitle"));
  if (picked === undefined) {
    // 桥不可用：切到明确标注的本机路径开发态
    devFallback.value = true;
    return;
  }
  if (picked === null) return; // 取消：不发起预检、不清除已有选择
  await setPath(picked);
}

async function setPath(next: string): Promise<void> {
  // 换文件必须清除旧预检：否则会拿 A 的凭证确认 B 的快照。
  await dropPreview();
  phase.value = "idle";
  errorText.value = "";
  path.value = next;
}

async function runPreview(): Promise<void> {
  if (!canPreview.value) return;
  errorText.value = "";
  phase.value = "previewing";
  try {
    const preview = await props.previewImport(path.value.trim());
    result.value = preview;
    phase.value = preview.can_import ? "confirmable" : "blocked";
    if (preview.can_import) startExpiryTimer();
  } catch (exc) {
    phase.value = "idle";
    errorText.value = messageOf(exc);
  }
}

async function runConfirm(): Promise<void> {
  const previewId = result.value?.preview_id;
  if (!canConfirm.value || previewId == null) return;
  errorText.value = "";
  phase.value = "importing";
  try {
    const published = await props.confirmImport(previewId);
    stopExpiryTimer();
    phase.value = "success";
    emit("imported", published);
  } catch (exc) {
    // 确认失败（冲突/凭证失效/发布故障）留在弹窗内：保留路径，允许重新预检或重试。
    await dropPreview();
    phase.value = "idle";
    errorText.value = messageOf(exc);
  }
}

async function close(): Promise<void> {
  await dropPreview();
  reset();
  emit("close");
}

function messageOf(exc: unknown): string {
  if (exc instanceof Error && exc.message.length > 0) return exc.message;
  return t("errors.ui.unknownSummary");
}

const diagnostics = computed(() => result.value?.diagnostics ?? []);
const existingText = computed(() => {
  const versions = result.value?.existing_versions ?? [];
  if (versions.length === 0) return t("standards.import.existingNone");
  return t("standards.import.existing", {
    versions: versions.map(item => `${formatStandardVersion(item.version)}(${item.source})`).join("、"),
  });
});

onBeforeUnmount(() => {
  stopExpiryTimer();
});
</script>
<template>
  <div v-if="open" class="import-backdrop" @click.self="close" @keydown="onDialogKeydown">
    <section
      ref="card"
      class="import-dialog"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-label="$t('standards.import.title')"
      data-testid="standard-import-dialog"
    >
      <h3>{{ $t("standards.import.title") }}</h3>
      <p v-if="devFallback" class="import-note" role="note" data-testid="import-dev-fallback">
        {{ $t("standards.import.devFallback") }}
      </p>
      <UiButton
        v-if="!devFallback"
        variant="secondary"
        :disabled="busy"
        data-testid="import-choose-file"
        @click="chooseFile"
      >
        {{ $t("standards.import.choose") }}
      </UiButton>
      <UiInput
        v-if="devFallback"
        :model-value="path"
        :label="$t('standards.import.pathLabel')"
        :placeholder="$t('standards.import.pathPlaceholder')"
        :disabled="busy"
        @update:model-value="setPath(String($event))"
      />
      <UiInput
        v-else
        :model-value="path"
        :label="$t('standards.import.pathLabel')"
        readonly
        data-testid="import-selected-path"
      />
      <p class="import-note" role="note">{{ $t("standards.import.changeFile") }}</p>

      <p v-if="phase === 'idle' && path.trim() === ''" class="import-note" role="status">
        {{ $t("standards.import.selectFirst") }}
      </p>
      <p v-if="phase === 'previewing'" class="import-note" role="status">{{ $t("standards.import.previewing") }}</p>
      <p v-if="phase === 'importing'" class="import-note" role="status">{{ $t("standards.import.importing") }}</p>

      <div v-if="result !== null" class="import-preview" data-testid="import-preview">
        <p class="import-identity">
          {{ $t("standards.import.identity", {
            id: result.standard_id,
            version: result.version,
            name: result.name,
          }) }}
        </p>
        <p class="import-note">{{ existingText }}</p>
        <p v-if="phase === 'blocked'" class="import-blocked">{{ $t("standards.import.blocked") }}</p>
        <ul v-if="diagnostics.length > 0" class="import-diagnostics" data-testid="import-diagnostics">
          <li v-for="item in diagnostics" :key="`${item.code}-${item.message}`">
            <code>{{ item.code }}</code> · {{ item.message }}
          </li>
        </ul>
      </div>
      <p v-if="phase === 'success'" class="import-success" role="status" data-testid="import-success">
        {{ $t("standards.import.success", {id: result?.standard_id ?? "", version: result?.version ?? 0}) }}
      </p>

      <p v-if="errorText" class="import-error" role="alert" data-testid="import-error">{{ errorText }}</p>

      <div class="import-actions">
        <UiButton variant="secondary" :disabled="busy" @click="close">
          {{ phase === "success" ? $t("standards.import.close") : $t("standards.import.cancel") }}
        </UiButton>
        <UiButton
          variant="secondary"
          :disabled="!canPreview"
          data-testid="import-preview-button"
          @click="runPreview"
        >
          {{ result === null ? $t("standards.import.preview") : $t("standards.import.repreview") }}
        </UiButton>
        <UiButton
          variant="primary"
          :disabled="!canConfirm"
          data-testid="import-confirm-button"
          @click="runConfirm"
        >
          {{ $t("standards.import.confirm") }}
        </UiButton>
      </div>
    </section>
  </div>
</template>
<style scoped>
.import-backdrop{position:fixed;inset:0;background:rgb(0 0 0 / 0.4);display:grid;place-items:center;z-index:60}
.import-dialog{width:min(520px,calc(100vw - 32px));display:grid;gap:var(--space-3);padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1)}
.import-dialog h3{margin:0;font-size:var(--font-page-title)}
.import-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.import-preview{display:grid;gap:var(--space-2);padding:var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.import-identity{margin:0;font-size:var(--font-label);color:var(--color-text-primary)}
.import-blocked{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.import-diagnostics{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1);font-size:var(--font-label);color:var(--color-text-secondary)}
.import-success{margin:0;font-size:var(--font-label);color:var(--color-accent)}
.import-error{margin:0;font-size:var(--font-label);color:var(--color-danger)}
.import-actions{display:flex;gap:var(--space-2);justify-content:flex-end;flex-wrap:wrap}
</style>
