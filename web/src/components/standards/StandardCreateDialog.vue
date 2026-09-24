<script setup lang="ts">
// 新建草稿对话框（PLAN-DM-035 Task 8 Step 4）：只负责三个起点——
// 空白草稿 / 复制发布版本 / 从 DST 提取；具体内容编辑由分区编辑器承接。
import {computed, reactive, ref, watch} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import type {CreateMode, StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  open: boolean;
  mode: CreateMode;
  origin: StandardSummary | null;
  defaultDraftName: string;
}>();
const emit = defineEmits<{close: []; submit: [payload: {name: string; dstPath: string}]}>();

// 草稿不填写版本（SPEC-DM-019 §2.3）：正式版本由服务端在发布时分配。
const form = reactive({name: "", dstPath: ""});

// 焦点契约（PLAN-DM-040 Task 9，F13）：与 UnsavedInputDialog/ConfirmModal 同源。
// 初始焦点是弹窗内首个停靠点（标准名称输入框），Tab/Shift+Tab 在弹窗内圈闭，
// Escape 关闭并把焦点归还给打开按钮。
const card = ref<HTMLElement | null>(null);
const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  onEscape: event => {
    event.stopPropagation();
    emit("close");
  },
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    form.name = props.defaultDraftName;
    form.dstPath = "";
  },
);

const canSubmit = computed(() => {
  if (!form.name.trim()) return false;
  if (props.mode === "from-dst") return form.dstPath.trim().length > 0;
  return true;
});

function submit(): void {
  if (!canSubmit.value) return;
  emit("submit", {name: form.name.trim(), dstPath: form.dstPath.trim()});
}
</script>
<template>
  <div v-if="open" class="create-dialog-backdrop" @click.self="emit('close')" @keydown="onDialogKeydown">
    <section ref="card" class="create-dialog" role="dialog" aria-modal="true" tabindex="-1" :aria-label="$t('standards.create.title')">
      <h3>{{ $t("standards.create.title") }}</h3>
      <p v-if="mode === 'derive'" class="create-origin">
        {{ $t("standards.create.deriveFrom", {id: origin?.standard_id ?? "", version: origin?.version ?? ""}) }}
      </p>
      <UiInput v-model="form.name" :label="$t('standards.create.nameLabel')" />
      <p class="create-note" role="note">{{ $t("standards.create.versionAssignedByServer") }}</p>
      <UiInput
        v-if="mode === 'from-dst'"
        v-model="form.dstPath"
        :label="$t('standards.create.dstPathLabel')"
        placeholder="C:\\project\\test.dst"
      />
      <div class="create-actions">
        <UiButton variant="secondary" @click="emit('close')">{{ $t("standards.create.cancel") }}</UiButton>
        <UiButton variant="secondary" :disabled="!canSubmit" @click="submit">{{ $t("standards.create.confirm") }}</UiButton>
      </div>
    </section>
  </div>
</template>
<style scoped>
.create-dialog-backdrop{position:fixed;inset:0;background:rgb(0 0 0 / 0.4);display:grid;place-items:center;z-index:60}
.create-dialog{width:min(420px,calc(100vw - 32px));display:grid;gap:var(--space-3);padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1)}
.create-dialog h3{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.create-origin{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.create-note{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.create-actions{display:flex;gap:var(--space-2);justify-content:flex-end}
</style>
