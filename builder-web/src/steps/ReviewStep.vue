<!-- 第 5 步 构建前检查（SPEC-DB-001 §2）：完整预览 → 提交修订（POST /api/plans）
     → 用户显式确认计划（POST /api/plans/{id}/confirm）。绝不自动确认；
     /api/plans 尚未进入 OpenAPI，响应类型在此最小声明，Task 9 接线后改为生成类型。 -->
<script setup lang="ts">
import GuidancePanel from "../components/GuidancePanel.vue";
import {computed, ref} from "vue";
import {requestJson} from "../api/client";
import {injectWizardStore, sheetNumber} from "../composables/useWizardStore";

const store = injectWizardStore();

interface PlanSubmitResponse {
  plan_id: string;
  revision_id: string;
  diagnostics: {code: string; severity: string; message: string; field?: string | null}[];
  preview: {sheet_number: string; layout_name: string; dwg_name: string; artifact_path: string};
}

const submitting = ref(false);
const submitError = ref("");
const plan = ref<PlanSubmitResponse | null>(null);
const confirming = ref(false);
const confirmError = ref("");

const preview = computed(() => {
  const number = sheetNumber(store.draft.numbering.prefix, store.draft.numbering.start, store.draft.numbering.width);
  const title = store.draft.sheets[0]?.title ?? "";
  if (number === null || title.trim().length === 0) {
    return null;
  }
  const layoutName = `${number} ${title}`;
  return {
    number,
    title,
    layoutName,
    dwgName: `${layoutName}.dwg`,
    artifactPath: `drawings/${layoutName}.dwg`,
    cadVersion: store.draft.cad_version,
    projectName: store.draft.project.name,
    discipline: store.draft.project.discipline,
  };
});

const blockingDiagnostics = computed(() =>
  (plan.value?.diagnostics ?? []).filter((diagnostic) => diagnostic.severity === "blocking"),
);

async function submitRevision(): Promise<void> {
  submitting.value = true;
  submitError.value = "";
  try {
    plan.value = await requestJson<PlanSubmitResponse>("/api/plans", {
      method: "POST",
      body: JSON.stringify({draft: store.draft}),
    });
  } catch (error) {
    submitError.value = (error as Error).message;
  } finally {
    submitting.value = false;
  }
}

async function confirmPlan(): Promise<void> {
  if (!plan.value) {
    return;
  }
  confirming.value = true;
  confirmError.value = "";
  try {
    await requestJson(`/api/plans/${encodeURIComponent(plan.value.plan_id)}/confirm`, {method: "POST"});
    store.planConfirmed.value = true;
  } catch (error) {
    confirmError.value = (error as Error).message;
  } finally {
    confirming.value = false;
  }
}
</script>

<template>
  <section aria-labelledby="review-title">
    <GuidancePanel
      title="第5步 构建前检查"
      goal="查看完整预览，提交修订并确认计划；确认后构建输入冻结。"
      :hints="['提交修订只生成预览计划；确认必须由您显式点击。']"
    />

    <table v-if="preview" data-testid="review-preview" class="preview-table">
      <tbody>
        <tr><th scope="row">工程名称</th><td>{{ preview.projectName }}</td></tr>
        <tr><th scope="row">专业</th><td>{{ preview.discipline }}</td></tr>
        <tr><th scope="row">图号</th><td>{{ preview.number }}</td></tr>
        <tr><th scope="row">图名</th><td>{{ preview.title }}</td></tr>
        <tr><th scope="row">布局名</th><td>{{ preview.layoutName }}</td></tr>
        <tr><th scope="row">DWG</th><td>{{ preview.dwgName }}</td></tr>
        <tr><th scope="row">目标路径</th><td>{{ preview.artifactPath }}</td></tr>
        <tr><th scope="row">AutoCAD 版本</th><td>{{ preview.cadVersion }}</td></tr>
      </tbody>
    </table>

    <div class="actions">
      <button
        type="button"
        class="primary"
        data-testid="submit-revision"
        :disabled="submitting || preview === null"
        @click="submitRevision"
      >
        提交修订
      </button>
      <p v-if="submitError" class="field-error" role="alert">{{ submitError }}</p>
    </div>

    <p v-if="!plan" data-testid="plan-pending" class="plan-state">尚未提交修订。</p>

    <div v-if="plan" data-testid="plan-preview" class="plan">
      <h3>计划预览</h3>
      <dl>
        <div><dt>计划 ID</dt><dd>{{ plan.plan_id }}</dd></div>
        <div><dt>修订 ID</dt><dd>{{ plan.revision_id }}</dd></div>
        <div><dt>图号</dt><dd>{{ plan.preview.sheet_number }}</dd></div>
        <div><dt>布局名</dt><dd>{{ plan.preview.layout_name }}</dd></div>
        <div><dt>目标 DWG</dt><dd>{{ plan.preview.artifact_path }}</dd></div>
      </dl>
      <ul v-if="blockingDiagnostics.length > 0" class="blocking">
        <li v-for="diagnostic in blockingDiagnostics" :key="diagnostic.code">
          {{ diagnostic.message }}
        </li>
      </ul>
      <p v-if="blockingDiagnostics.length > 0" class="field-error" role="alert">
        存在阻断诊断，不能确认计划。
      </p>
      <div v-else class="actions">
        <button
          type="button"
          class="primary"
          data-testid="confirm-plan"
          :disabled="confirming || store.planConfirmed.value"
          @click="confirmPlan"
        >
          确认计划
        </button>
        <p v-if="confirmError" class="field-error" role="alert">{{ confirmError }}</p>
      </div>
      <p v-if="store.planConfirmed.value" data-testid="plan-confirmed" class="confirmed" role="status">
        计划已确认，构建输入已冻结。
      </p>
    </div>
  </section>
</template>

<style scoped>
.preview-table {
  border-collapse: collapse;
  width: 100%;
  max-width: 560px;
  margin-bottom: var(--space-4);
}

.preview-table th,
.preview-table td {
  border: var(--border-width-1) solid var(--color-border-subtle);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  font-size: var(--font-size-13);
}

.preview-table th {
  color: var(--color-text-secondary);
  font-weight: 500;
  width: 140px;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.plan {
  border: var(--border-width-1) solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  max-width: 560px;
}

.plan h3 {
  font-size: var(--font-size-14);
  margin-bottom: var(--space-2);
}

.plan dl {
  margin: 0 0 var(--space-3);
}

.plan dt {
  font-size: var(--font-size-12);
  color: var(--color-text-secondary);
}

.plan dd {
  margin: 0 0 var(--space-2);
}

.blocking {
  color: var(--color-danger);
}

.confirmed {
  color: var(--color-success);
}

.plan-state {
  color: var(--color-text-muted);
}
</style>
