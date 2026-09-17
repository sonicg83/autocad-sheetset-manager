<!-- 固定操作栏：返回/下一步 + 自动保存状态（aria-live）。高度计入
     tokens.css 的 --dock-height，全局 scroll-padding-bottom 据此留白，
     保证聚焦控件滚动定位后不被本栏遮挡。 -->
<script setup lang="ts">
import {computed} from "vue";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

const nextEnabled = computed(() => store.completion.value[store.step.value - 1]);
const nextVisible = computed(() => store.step.value < 7);
const currentComplete = computed(() => store.completion.value[store.step.value - 1]);

const statusText = computed(() => {
  switch (store.autosaveStatus.value) {
    case "dirty":
      return "有未保存更改";
    case "saving":
      return "正在保存…";
    case "saved":
      return "已自动保存";
    case "conflict":
      return "保存冲突";
    case "error":
      return "保存失败";
    default:
      return "";
  }
});
</script>

<template>
  <div data-testid="action-dock" class="dock">
    <button type="button" data-testid="dock-back" :disabled="store.step.value <= 1" @click="store.goBack()">
      上一步
    </button>
    <p data-testid="autosave-status" aria-live="polite" class="status">{{ statusText }}</p>
    <p v-if="!currentComplete" class="blocked" aria-live="polite">请先完成本步骤的必填内容</p>
    <button
      v-if="nextVisible"
      type="button"
      class="primary"
      data-testid="dock-next"
      :disabled="!nextEnabled"
      @click="store.advance()"
    >
      下一步
    </button>
  </div>
</template>

<style scoped>
.dock {
  position: fixed;
  inset-inline: 0;
  bottom: 0;
  height: var(--dock-height);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 0 var(--space-5);
  background: var(--color-bg-surface);
  border-top: var(--border-width-1) solid var(--color-border-subtle);
  box-shadow: var(--shadow-2);
}

.status {
  margin: 0;
  font-size: var(--font-size-13);
  color: var(--color-text-muted);
}

.blocked {
  margin: 0;
  font-size: var(--font-size-13);
  color: var(--color-warning);
}
</style>
