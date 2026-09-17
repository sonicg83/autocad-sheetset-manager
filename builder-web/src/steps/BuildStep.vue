<!-- 第 6 步 构建成果（SPEC-DB-001 §2/§6）：启动构建、观察状态与进度、请求取消。
     状态轮询 GET /api/builds/{id}；/api/builds 端点 Task 9 才进入 OpenAPI，
     响应类型在此最小声明，接线后改为生成类型。 -->
<script setup lang="ts">
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed, onBeforeUnmount, ref} from "vue";
import {requestJson} from "../api/client";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

interface BuildStatusResponse {
  build_id: string;
  plan_id: string;
  status: string;
  progress: number;
  error_code: string | null;
  published_path: string | null;
}

const TERMINAL_STATUSES = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

const starting = ref(false);
const startError = ref("");
const build = ref<BuildStatusResponse | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const isTerminal = computed(() => build.value !== null && TERMINAL_STATUSES.has(build.value.status));
const canCancel = computed(
  () =>
    build.value !== null &&
    !isTerminal.value &&
    build.value.status !== "PUBLISHING",
);

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function refresh(): Promise<void> {
  if (!build.value) {
    return;
  }
  try {
    build.value = await requestJson<BuildStatusResponse>(
      `/api/builds/${encodeURIComponent(build.value.build_id)}`,
    );
    if (build.value.status === "SUCCEEDED") {
      store.buildSucceeded.value = true;
      stopPolling();
    } else if (TERMINAL_STATUSES.has(build.value.status)) {
      stopPolling();
    }
  } catch {
    // 轮询失败保持当前状态，下次周期继续
  }
}

async function startBuild(): Promise<void> {
  starting.value = true;
  startError.value = "";
  try {
    build.value = await requestJson<BuildStatusResponse>("/api/builds", {
      method: "POST",
      body: JSON.stringify({plan_id: "current"}),
    });
    pollTimer = setInterval(() => void refresh(), 500);
  } catch (error) {
    startError.value = (error as Error).message;
  } finally {
    starting.value = false;
  }
}

async function cancelBuild(): Promise<void> {
  if (!build.value) {
    return;
  }
  try {
    build.value = await requestJson<BuildStatusResponse>(
      `/api/builds/${encodeURIComponent(build.value.build_id)}/cancel`,
      {method: "POST"},
    );
  } catch (error) {
    startError.value = (error as Error).message;
  }
}

onBeforeUnmount(stopPolling);
</script>

<template>
  <section aria-labelledby="build-title">
    <GuidancePanel
      title="第6步 构建成果"
      goal="启动并观察构建；运行中计划冻结不可编辑。"
      :hints="['PUBLISHING 阶段不响应取消，避免与原子发布竞态。']"
    />

    <div v-if="!build" class="actions">
      <button type="button" class="primary" data-testid="start-build" :disabled="starting" @click="startBuild">
        启动构建
      </button>
      <p v-if="startError" class="field-error" role="alert">{{ startError }}</p>
    </div>

    <div v-else class="build-state">
      <p>
        状态：<output data-testid="build-status">{{ build.status }}</output>
      </p>
      <div
        data-testid="build-progress"
        role="progressbar"
        :aria-valuenow="build.progress"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-label="构建进度"
        class="progress"
      >
        <div class="progress-fill" :style="{width: `${build.progress}%`}"></div>
      </div>
      <p class="actions">
        <button
          v-if="!isTerminal"
          type="button"
          data-testid="cancel-build"
          :disabled="!canCancel"
          @click="cancelBuild"
        >
          取消构建
        </button>
        <span v-if="build.published_path" data-testid="published-path" role="status">
          已发布：{{ build.published_path }}
        </span>
      </p>
    </div>
  </section>
</template>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.progress {
  width: 100%;
  max-width: 420px;
  height: 12px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
  overflow: hidden;
  margin: var(--space-3) 0;
}

.progress-fill {
  height: 100%;
  background: var(--color-accent);
  transition: width 0.4s ease;
}
</style>
