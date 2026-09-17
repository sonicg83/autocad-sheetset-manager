<!-- 第 7 步 验收与交接（SPEC-DB-001 §2/§10）：查看验证结果与发布位置，
     调用 Builder 本机 Manager 交接适配器。/api/builds/{id}/handoff 端点
     Task 10 才进入 OpenAPI；本步骤先用真实 buildId（store 上收）发起调用。 -->
<script setup lang="ts">
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed, ref} from "vue";
import {requestJson} from "../api/client";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

interface HandoffResponse {
  handoff_path: string;
  workspace_id?: string;
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
    handoffError.value = (error as Error).message;
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
      交接完成：{{ result.handoff_path }}
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
