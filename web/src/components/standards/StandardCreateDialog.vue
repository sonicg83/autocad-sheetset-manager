<script setup lang="ts">
// 新建草稿对话框（PLAN-DM-035 Task 8 Step 4）：只负责三个起点——
// 空白草稿 / 复制发布版本 / 从 DST 提取；具体内容编辑由分区编辑器承接。
import {computed, reactive, watch} from "vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import type {CreateMode, StandardSummary} from "../../features/standards/types";

const props = defineProps<{
  open: boolean;
  mode: CreateMode;
  origin: StandardSummary | null;
  defaultDraftName: string;
}>();
const emit = defineEmits<{close: []; submit: [payload: {name: string; version: string; dstPath: string}]}>();

const form = reactive({name: "", version: "0.1.0", dstPath: ""});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    form.name = props.defaultDraftName;
    form.version = props.mode === "derive" ? deriveVersion(props.origin?.version ?? "1.0.0") : "0.1.0";
    form.dstPath = "";
  },
);

// 复制发布版本：新版本取现有三段版本号的补丁位 +1（1.2.3 -> 1.2.4）。
function deriveVersion(version: string): string {
  const parts = version.split(".");
  if (parts.length !== 3 || parts.some(part => !/^\d+$/.test(part))) return "0.1.0";
  const patch = Number(parts[2]) + 1;
  return `${parts[0]}.${parts[1]}.${String(patch)}`;
}

const canSubmit = computed(() => {
  if (!/^\d+\.\d+\.\d+$/.test(form.version.trim())) return false;
  if (!form.name.trim()) return false;
  if (props.mode === "from-dst") return form.dstPath.trim().length > 0;
  return true;
});

function submit(): void {
  if (!canSubmit.value) return;
  emit("submit", {name: form.name.trim(), version: form.version.trim(), dstPath: form.dstPath.trim()});
}
</script>
<template>
  <div v-if="open" class="create-dialog-backdrop" @click.self="emit('close')">
    <section class="create-dialog" role="dialog" aria-modal="true" :aria-label="$t('standards.create.title')">
      <h3>{{ $t("standards.create.title") }}</h3>
      <p v-if="mode === 'derive'" class="create-origin">
        {{ $t("standards.create.deriveFrom", {id: origin?.standard_id ?? "", version: origin?.version ?? ""}) }}
      </p>
      <UiInput v-model="form.name" :label="$t('standards.create.nameLabel')" />
      <UiInput v-model="form.version" :label="$t('standards.create.versionLabel')" />
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
.create-actions{display:flex;gap:var(--space-2);justify-content:flex-end}
</style>
