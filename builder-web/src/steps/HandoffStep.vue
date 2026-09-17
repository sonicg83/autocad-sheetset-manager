<!-- 第 7 步 验收与交接（SPEC-DB-001 §2/§10）：查看验证结果与发布位置，
     调用 Builder 的 POST /api/builds/{id}/handoff——显式适配器转发本机
     Manager 的 POST /api/handoffs/open。Manager 不可用时已发布成果包原样
     保留，错误负载携带可执行的恢复动作（Task 10 接线）。 -->
<script setup lang="ts">
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed, ref} from "vue";
import {BuilderApiError, requestJson} from "../api/client";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

interface HandoffResponse {
  handoff_path: string;
  workspace_id: string;
  revision_id: string;
  kind: string;
  idempotent?: boolean;
}

const handingOff = ref(false);
const handoffError = ref("");
const result = ref<HandoffResponse | null>(null);

const summary = computed(() => {
  if (!store.buildSucceeded.value) {
    return null;
  }
  return {
    message: "构建成功，成果包已通过完整验证并原子发布。",
  };
});

async function handoffToManager(): Promise<void> {
  if (!store.buildId.value) {
    handoffError.value = "尚无构建记录：请先在第 6 步完成构建";
    return;
  }
  handingOff.value = true;
  handoffError.value = "";
  try {
    result.value = await requestJson<HandoffResponse>(
      `/api/builds/${encodeURIComponent(store.buildId.value)}/handoff`,
      {method: "POST"},
    );
    store.handoffDone.value = true;
  } catch (error) {
    // 交接失败不影响已发布成果包：按 §11 错误负载展示可执行恢复动作。
    if (error instanceof BuilderApiError && error.recoveryAction) {
      handoffError.value = `${error.message}${error.recoveryAction ? "。" + error.recoveryAction : ""}`;
    } else {
      handoffError.value = (error as Error).message;
    }
  } finally {
    handingOff.value = false;
  }
}
</script>

<template>
  <section aria-labelledby="handoff-title">
    <GuidancePanel
      title="第7步 验收与交接"
      goal="查看验证结果，发布并交接给 DST Manager。"
      :hints="['Manager 只读取 handoff.json 及其引用的包内元数据。']"
    />

    <p v-if="summary" data-testid="build-summary" class="summary" role="status">{{ summary.message }}</p>

    <div class="actions">
      <button
        type="button"
        class="primary"
        data-testid="handoff-button"
        :disabled="handingOff || !store.buildSucceeded.value"
        @click="handoffToManager"
      >
        交接给 DST Manager
      </button>
      <p v-if="handoffError" class="field-error" role="alert">{{ handoffError }}</p>
    </div>

    <p v-if="result" data-testid="handoff-result" class="result" role="status">
      交接完成：{{ result.handoff_path }}（工作区 {{ result.workspace_id }}）
    </p>
  </section>
</template>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.summary {
  color: var(--color-success);
}

.result {
  margin-top: var(--space-4);
  color: var(--color-success);
}
</style>
