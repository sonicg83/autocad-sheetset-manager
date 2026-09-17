<!-- 步骤导航（ARCH-DB-001 §7）：已完成步骤可回访；后续步骤仅在前置门禁满足后开放。 -->
<script setup lang="ts">
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

const STEP_NAMES = ["创建项目", "配置规则", "编排图纸", "匹配模板", "构建前检查", "构建成果", "验收与交接"] as const;

function stepLabel(index: number): string {
  const ordinal = index + 1;
  if (store.completion.value[index]) {
    return `第${ordinal}步 ${STEP_NAMES[index]}（已完成）`;
  }
  if (store.step.value === ordinal) {
    return `第${ordinal}步 ${STEP_NAMES[index]}（进行中）`;
  }
  return `第${ordinal}步 ${STEP_NAMES[index]}`;
}

function stepState(index: number): string {
  if (store.completion.value[index]) {
    return "已完成";
  }
  if (store.step.value === index + 1) {
    return "进行中";
  }
  return "未开放";
}
</script>

<template>
  <nav aria-label="引导步骤" class="rail">
    <ol>
      <li v-for="(name, index) in STEP_NAMES" :key="name">
        <button
          :data-testid="`rail-step-${index + 1}`"
          type="button"
          :disabled="!store.canEnter(index + 1)"
          :aria-current="store.step.value === index + 1 ? 'step' : undefined"
          @click="store.visit(index + 1)"
        >
          <span class="state" :data-state="stepState(index)">{{ stepState(index) }}</span>
          {{ stepLabel(index) }}
        </button>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.rail ol {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.rail button {
  width: 100%;
  text-align: left;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.state {
  font-size: var(--font-size-12);
  color: var(--color-text-muted);
}

.state[data-state="已完成"] {
  color: var(--color-success);
}

.state[data-state="进行中"] {
  color: var(--color-info);
}
</style>
