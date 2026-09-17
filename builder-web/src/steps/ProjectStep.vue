<!-- 第 1 步 创建项目（SPEC-DB-001 §2）：项目目录 + 工程名称/阶段/专业/成果目录。
     未创建项目时为创建模式（POST /api/projects）；创建后字段编辑走草稿自动保存。 -->
<script setup lang="ts">
import FieldDiagnostics from "../components/FieldDiagnostics.vue";
import GuidancePanel from "../components/GuidancePanel.vue";
import {reactive} from "vue";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

const createForm = reactive({
  projectRoot: "",
  name: "",
  stage: "",
  discipline: "",
  outputPath: "",
});

async function submitCreate(): Promise<void> {
  await store.createProject(createForm);
}
</script>

<template>
  <section aria-labelledby="project-title">
    <GuidancePanel
      title="第1步 创建项目"
      goal="选择自包含项目目录，填写工程名称、阶段、专业和成果目录。"
      :hints="['创建后将在项目目录生成 project.dstb 项目库。', '成果目录应是不存在的新目录，首期不覆盖既有成果。']"
    />
    <FieldDiagnostics />

    <form v-if="!store.project.value" class="fields" @submit.prevent="submitCreate">
      <p class="field">
        <label class="field-label" for="f-project-root">项目目录</label>
        <input id="f-project-root" v-model="createForm.projectRoot" data-field="project_root" type="text" />
      </p>
      <p class="field">
        <label class="field-label" for="f-name">工程名称</label>
        <input id="f-name" v-model="createForm.name" data-field="project.name" type="text" required />
      </p>
      <p class="field">
        <label class="field-label" for="f-stage">阶段</label>
        <input id="f-stage" v-model="createForm.stage" data-field="project.stage" type="text" required />
      </p>
      <p class="field">
        <label class="field-label" for="f-discipline">专业</label>
        <input id="f-discipline" v-model="createForm.discipline" data-field="project.discipline" type="text" required />
      </p>
      <p class="field">
        <label class="field-label" for="f-output">成果目录</label>
        <input id="f-output" v-model="createForm.outputPath" data-field="project.output_path" type="text" required />
      </p>
      <p v-if="store.createProjectError.value" class="field-error" role="alert">
        {{ store.createProjectError.value }}
      </p>
      <button class="primary" type="submit" data-testid="create-project">创建项目</button>
    </form>

    <div v-else class="fields">
      <p class="field">
        <label class="field-label" for="e-name">工程名称</label>
        <input
          id="e-name"
          v-model="store.draft.project.name" :disabled="store.buildRunning.value"
          data-field="project.name"
          type="text"
        />
      </p>
      <p class="field">
        <label class="field-label" for="e-stage">阶段</label>
        <input id="e-stage" v-model="store.draft.project.stage" data-field="project.stage" type="text" :disabled="store.buildRunning.value" />
      </p>
      <p class="field">
        <label class="field-label" for="e-discipline">专业</label>
        <input
          id="e-discipline"
          v-model="store.draft.project.discipline" :disabled="store.buildRunning.value"
          data-field="project.discipline"
          type="text"
        />
      </p>
      <p class="field">
        <label class="field-label" for="e-output">成果目录</label>
        <input
          id="e-output"
          v-model="store.draft.project.output_path" :disabled="store.buildRunning.value"
          data-field="project.output_path"
          type="text"
          :aria-invalid="store.fieldErrors.value.some((e) => e.field === 'project.output_path') ? 'true' : undefined"
          :aria-describedby="store.fieldErrors.value.some((e) => e.field === 'project.output_path') ? 'e-output-error' : undefined"
        />
        <span
          v-if="store.fieldErrors.value.some((e) => e.field === 'project.output_path')"
          id="e-output-error"
          class="field-error"
          role="alert"
        >
          {{ store.fieldErrors.value.find((e) => e.field === "project.output_path")?.message }}
        </span>
      </p>
    </div>
  </section>
</template>
