<script setup lang="ts">
import {ref} from "vue";
import UiButton from "../components/ui/UiButton.vue";
defineProps<{hasShell:boolean}>();
const emit=defineEmits<{select:[];submitPath:[path:string]}>();
const path=ref("");
// PLAN-DM-029 Task 9：路径输入必须有可见 label 关联（仅 placeholder/aria-label 不解除
// `visible-input-label` 例外）。该 label 文本复用现有键，不新增 i18n key；
// 同时从输入框上移除 placeholder，避免可见文本重复两遍。
const pathInputId="welcome-path-input";
</script>
<template>
  <section class="welcome-card" role="region" :aria-label="$t('shell.welcome.region')">
    <h2 class="welcome-title">{{ $t("shell.welcome.title") }}</h2>
    <p class="welcome-desc">{{ $t("shell.welcome.desc") }}</p>
    <template v-if="!hasShell">
      <div class="no-shell">
        <label class="no-shell-label" :for="pathInputId">{{ $t("shell.welcome.pathPlaceholder") }}</label>
        <input :id="pathInputId" v-model="path" @keyup.enter="$emit('submitPath',path)">
        <UiButton variant="secondary" @click="$emit('submitPath',path)">{{ $t("shell.welcome.openProject") }}</UiButton>
      </div>
    </template>
    <template v-else>
      <button type="button" class="primary" @click="$emit('select')">{{ $t("shell.welcome.selectDst") }}</button>
      <p class="drop-hint">{{ $t("shell.welcome.dropHint") }}</p>
    </template>
  </section>
</template>
<style scoped>
.welcome-card{max-width:var(--card-max-width);margin:12vh auto;padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);text-align:center}
.welcome-title{font-size:20px;margin:0 0 var(--space-2);color:var(--color-text-primary)}
.welcome-desc{color:var(--color-text-secondary);font-size:var(--font-label);margin:0 0 var(--space-5);line-height:1.6}
.no-shell{display:grid;gap:var(--space-2);margin:0 auto;max-width:var(--welcome-path-max-width);text-align:left}
.no-shell-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.no-shell input{min-width:0;height:var(--control-height-default);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:0 var(--space-3);font-family:inherit;font-size:var(--font-label)}
.drop-hint{color:var(--color-text-muted);font-size:var(--font-label);margin:var(--space-4) 0 0}
/* 欢迎页主操作按表单档 38px（ARCH-DM-007 §4.1）；`UiButton` 只有 36/34 两档，
   故此处保留原生按钮并逐字借用表单档令牌，不把 38 降为 36（T9-1(C) 允许该借用）。 */
.welcome-card .primary{background:var(--color-accent);color:var(--color-on-accent);border:1px solid transparent;border-radius:var(--radius-md);height:var(--control-height-form);padding:0 var(--space-5);font-weight:500;cursor:pointer;font-size:var(--button-font-size)}
.welcome-card .primary:hover{background:var(--color-accent-hover)}
</style>
