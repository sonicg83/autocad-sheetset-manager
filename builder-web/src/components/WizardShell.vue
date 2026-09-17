<!-- 向导壳层：标题 + 步骤导航 + 当前步骤内容 + 固定操作栏 + Toast 宿主。
     每个时刻只渲染当前步骤的字段（App.vue 以 v-if 切换）。 -->
<script setup lang="ts">
import {inject} from "vue";
import {WIZARD_STORE_KEY} from "../composables/useWizardStore";
import ActionDock from "./ActionDock.vue";
import StepRail from "./StepRail.vue";

const store = inject(WIZARD_STORE_KEY);
if (!store) {
  throw new Error("WizardShell 必须在注入向导状态的组件树内使用");
}
</script>

<template>
  <div data-testid="wizard-shell" class="shell">
    <header class="shell-header">
      <h1>DST Builder</h1>
    </header>
    <div class="shell-body">
      <aside class="shell-rail">
        <StepRail />
      </aside>
      <main class="shell-main">
        <slot />
      </main>
    </div>
    <ActionDock />
    <div
      v-if="store.toast.value"
      data-testid="toast"
      class="toast"
      :class="store.toast.value.kind"
      role="status"
    >
      <p>{{ store.toast.value.message }}</p>
      <button type="button" data-testid="toast-dismiss" @click="store.dismissToast()">知道了</button>
    </div>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}

.shell-header {
  padding: var(--space-3) var(--space-5);
  border-bottom: var(--border-width-1) solid var(--color-border-subtle);
  background: var(--color-bg-surface);
}

.shell-header h1 {
  font-size: var(--font-size-16);
}

.shell-body {
  display: flex;
  gap: var(--space-5);
  padding: var(--space-5);
  /* 底部为固定操作栏留出空间，避免内容被遮挡。 */
  padding-bottom: calc(var(--dock-height) + var(--space-5));
  align-items: flex-start;
}

.shell-rail {
  flex: 0 0 220px;
}

.shell-main {
  flex: 1 1 auto;
  min-width: 0;
}

@media (max-width: 720px) {
  .shell-body {
    flex-direction: column;
  }

  .shell-rail {
    flex: none;
    width: 100%;
  }
}

.toast {
  position: fixed;
  right: var(--space-5);
  bottom: calc(var(--dock-height) + var(--space-4));
  display: flex;
  align-items: center;
  gap: var(--space-3);
  max-width: min(360px, calc(100vw - var(--space-8, 32px)));
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: var(--border-width-1) solid var(--color-border-strong);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-2);
}

.toast p {
  margin: 0;
  font-size: var(--font-size-13);
}

.toast.error {
  border-color: var(--color-danger);
  background: var(--color-danger-bg);
}

.toast.success {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}
</style>
