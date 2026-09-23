<script setup lang="ts">
import {ref} from "vue";
import UiButton from "../components/ui/UiButton.vue";
// 欢迎页（SPEC-DM-016 §4；PLAN-DM-039 Task 1）："打开图纸集优先"双栏——
// 主栏约占 2/3（打开 DST 是唯一 primary），辅栏约占 1/3（其他任务：创建新图纸集、
// 管理图纸标准、导入标准包三个次级入口）。900×768 及以下降为单列，主任务仍排最前。
// 布局与文案层级对照 `docs/dst-manager/mockups/SPEC-DM-016-welcome-demo.html`；
// 入口去向由 `App.vue` 装配，本组件只发事件、不承载导航或导入状态。
defineProps<{hasShell: boolean}>();
const emit = defineEmits<{
  select: [];
  submitPath: [path: string];
  createSheetset: [];
  manageStandards: [];
  importStandard: [];
}>();
const path = ref("");
// PLAN-DM-029 Task 9：路径输入必须有可见 label 关联（仅 placeholder/aria-label 不解除
// `visible-input-label` 例外）。该 label 文本复用现有键，不新增 i18n key；
// 同时从输入框上移除 placeholder，避免可见文本重复两遍。
const pathInputId = "welcome-path-input";
</script>
<template>
  <section class="welcome-page" role="region" :aria-label="$t('shell.welcome.region')">
    <header class="welcome-intro">
      <h1>{{ $t("shell.welcome.startTitle") }}</h1>
      <p>{{ $t("shell.welcome.startDesc") }}</p>
    </header>
    <div class="welcome-layout" data-testid="welcome-layout">
      <article class="welcome-open-card" data-testid="welcome-open-card">
        <h2>{{ $t("shell.welcome.title") }}</h2>
        <p>{{ $t("shell.welcome.desc") }}</p>
        <template v-if="!hasShell">
          <div class="no-shell">
            <label class="no-shell-label" :for="pathInputId">{{ $t("shell.welcome.pathPlaceholder") }}</label>
            <input :id="pathInputId" v-model="path" @keyup.enter="emit('submitPath', path)">
            <UiButton variant="secondary" @click="emit('submitPath', path)">{{ $t("shell.welcome.openProject") }}</UiButton>
          </div>
        </template>
        <template v-else>
          <button type="button" class="primary" @click="emit('select')">{{ $t("shell.welcome.selectDst") }}</button>
          <p class="drop-hint">{{ $t("shell.welcome.dropHint") }}</p>
        </template>
      </article>
      <aside class="welcome-task-card" data-testid="welcome-task-card">
        <h2>{{ $t("shell.welcome.otherTasksTitle") }}</h2>
        <p>{{ $t("shell.welcome.otherTasksDesc") }}</p>
        <div class="task-list">
          <UiButton class="task-item" variant="secondary" @click="emit('createSheetset')">
            <span class="task-copy">
              <strong>{{ $t("shell.welcome.createTask") }}</strong>
              <span>{{ $t("shell.welcome.createTaskDesc") }}</span>
            </span>
          </UiButton>
          <UiButton class="task-item" variant="secondary" @click="emit('manageStandards')">
            <span class="task-copy">
              <strong>{{ $t("standards.entry") }}</strong>
              <span>{{ $t("shell.welcome.manageTaskDesc") }}</span>
            </span>
          </UiButton>
          <UiButton class="task-item" variant="secondary" @click="emit('importStandard')">
            <span class="task-copy">
              <strong>{{ $t("standards.library.import") }}</strong>
              <span>{{ $t("shell.welcome.importTaskDesc") }}</span>
            </span>
          </UiButton>
        </div>
        <p class="boundary-note" role="note">{{ $t("shell.welcome.standardBoundary") }}</p>
      </aside>
    </div>
    <!-- 最近打开属于增强信息：没有可信记录时不伪造历史，只说明为空（SPEC-DM-016 §4.1） -->
    <p class="recent-note">{{ $t("shell.welcome.recentEmptyNote") }}</p>
  </section>
</template>
<style scoped>
.welcome-page{max-width:var(--shell-content-max-width,1200px);margin:0 auto;padding:var(--space-6) var(--space-5);display:grid;gap:var(--space-5)}
.welcome-intro{text-align:center}
.welcome-intro h1{margin:0;font-size:var(--font-page-title);color:var(--color-text-primary)}
.welcome-intro p{margin:var(--space-2) auto 0;max-width:var(--welcome-path-max-width);color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.7}
/* 打开优先双栏：主栏 2fr、辅栏 1fr（SPEC-DM-016 §4.1 的约 2:1） */
.welcome-layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:var(--space-4);align-items:stretch}
.welcome-open-card,.welcome-task-card{padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1)}
.welcome-open-card{display:flex;flex-direction:column;gap:var(--space-3)}
.welcome-open-card h2,.welcome-task-card h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.welcome-open-card p,.welcome-task-card p{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.65}
.no-shell{display:grid;gap:var(--space-2);max-width:var(--welcome-path-max-width)}
.no-shell-label{font-size:var(--font-label);color:var(--color-text-secondary)}
.no-shell input{min-width:0;height:var(--control-height-default);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:0 var(--space-3);font-family:inherit;font-size:var(--font-label)}
.drop-hint{color:var(--color-text-muted)}
/* 欢迎页主操作按表单档 38px（ARCH-DM-007 §4.1）；`UiButton` 只有 36/34 两档，
   故此处保留原生按钮并逐字借用表单档令牌，不把 38 降为 36（T9-1(C) 允许该借用）。 */
.welcome-open-card .primary{align-self:flex-start;background:var(--color-accent);color:var(--color-on-accent);border:1px solid transparent;border-radius:var(--radius-md);height:var(--control-height-form);padding:0 var(--space-5);font-weight:500;cursor:pointer;font-size:var(--button-font-size)}
.welcome-open-card .primary:hover{background:var(--color-accent-hover)}
.welcome-task-card{display:flex;flex-direction:column;gap:var(--space-2)}
.task-list{display:grid;gap:var(--space-2);margin-top:var(--space-2)}
.task-item{width:100%;height:auto;justify-content:flex-start;text-align:left;padding:var(--space-3)}
.task-copy{display:grid;gap:var(--space-1);min-width:0}
.task-copy strong{font-weight:500;color:var(--color-text-primary)}
.task-copy span{color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.5;white-space:normal}
.boundary-note{margin-top:var(--space-2)!important;padding:var(--space-3);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-muted)!important;font-size:var(--font-label);line-height:1.6}
.recent-note{margin:0;text-align:center;color:var(--color-text-muted);font-size:var(--font-label)}
/* 900×768 及以下单列：打开任务仍在最前，不产生页面横向滚动（SPEC-DM-016 §4.1） */
@media (max-width: 900px){
  .welcome-page{padding:var(--space-5) var(--space-4)}
  .welcome-layout{grid-template-columns:minmax(0,1fr)}
}
</style>
