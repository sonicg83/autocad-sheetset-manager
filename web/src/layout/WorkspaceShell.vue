<script setup lang="ts">
import TopBar from "./TopBar.vue";
import TabBar from "./TabBar.vue";
import TaskOverlay from "./TaskOverlay.vue";
import ActionDock from "./ActionDock.vue";

// 纯展示壳层（PLAN-DM-029 Task 11 Step 6）。只装配 TopBar/TabBar/TaskOverlay/ActionDock 与
// 壳层级提示，把页面内容经默认 slot 透出；业务状态一律由根组件经 props 传入、经 emits 回传。
//
// **本文件不得导入 API client、draft helpers 或任何业务 composable**（T11-1(E)）：一旦导入，
// 壳层就不再是纯展示的，Step 6 的验收条件即失效——`check:ui` 不检查这一点，故须以 grep 自证。
//
// 子组件的 props 以「整组对象」传入（`InstanceType<typeof X>["$props"]`）：比逐个声明约 30 个 prop
// 更**类型安全**——对象键写错是编译错误，而逐个写 prop 名若拼错会静默落进 `$attrs`（不报错）。
type TopBarProps = InstanceType<typeof TopBar>["$props"];
type TabBarProps = InstanceType<typeof TabBar>["$props"];
type TaskOverlayProps = InstanceType<typeof TaskOverlay>["$props"];
type ActionDockProps = InstanceType<typeof ActionDock>["$props"];

defineProps<{
  // 壳层级提示与布局开关
  hasWorkspace: boolean;
  sheetsActive: boolean;
  error: string | null;
  lastErrorDiagnostic: string | null;
  isWorkspaceLoading: boolean;
  isRestoreExecuting: boolean;
  topBar: TopBarProps;
  tabBar: TabBarProps;
  taskOverlay: TaskOverlayProps;
  dock: ActionDockProps;
}>();

const emit = defineEmits<{
  close: [];
  "open-folder": [];
  "open-settings": [];
  select: [id: string];
  keydown: [event: KeyboardEvent];
  "update:tab": [tab: TaskOverlayProps["tab"]];
  fold: [];
  retry: [];
  "preview-repair": [];
  "execute-repair": [];
  "cancel-repair": [];
  preview: [];
  write: [];
  undo: [];
  redo: [];
  clear: [];
  remove: [index: number];
  discard: [];
  "reload-conflict": [];
  "retry-save": [];
}>();
</script>

<template>
  <TopBar
    v-bind="topBar"
    @close="emit('close')"
    @open-folder="emit('open-folder')"
    @open-settings="emit('open-settings')"
  />
  <div class="shell-body">
    <main class="shell-main" :class="{'sheets-active': sheetsActive}">
      <p v-if="error" class="error notice">{{ error }}</p>
      <!-- PLAN-DM-021 Task 9（I18N-11）：未知错误的原始文本只在可展开诊断详情呈现 -->
      <details v-if="error && lastErrorDiagnostic" class="error notice"><summary>{{ $t("errors.ui.diagnosticsDetails") }}</summary><pre class="error-raw">{{ lastErrorDiagnostic }}</pre></details>
      <p v-if="isWorkspaceLoading" class="panel loading" role="status">{{ $t("shell.workspace.loading") }}</p>
      <p v-if="isRestoreExecuting" class="panel loading" role="status">{{ $t("shell.workspace.restoring") }}</p>
      <!-- TabBar 的键盘处理是**原生 DOM 监听**（TabBar 只 emit select，单根 <nav> 承接透传的 @keydown）→
           此处按原样监听并转成壳层 emit，保证根组件仍按「按键冒泡到 TabBar 根」的既有路径驱动。 -->
      <TabBar v-if="hasWorkspace" v-bind="tabBar" @select="emit('select', $event)" @keydown="emit('keydown', $event)" />
      <slot />
    </main>
    <TaskOverlay
      v-if="hasWorkspace"
      v-bind="taskOverlay"
      @update:tab="emit('update:tab', $event)"
      @fold="emit('fold')"
      @retry="emit('retry')"
      @preview-repair="emit('preview-repair')"
      @execute-repair="emit('execute-repair')"
      @cancel-repair="emit('cancel-repair')"
    />
  </div>
  <ActionDock
    v-if="hasWorkspace"
    v-bind="dock"
    @preview="emit('preview')"
    @write="emit('write')"
    @undo="emit('undo')"
    @redo="emit('redo')"
    @clear="emit('clear')"
    @remove="emit('remove', $event)"
    @discard="emit('discard')"
    @reload-conflict="emit('reload-conflict')"
    @retry-save="emit('retry-save')"
  />
</template>

<style scoped>
/* 壳层布局：自 App.vue 原样搬入（Task 11 Step 6），未改任何取值。 */
.shell-body{display:flex;align-items:stretch;height:calc(100vh - 104px);min-height:0}
.shell-main{display:flex;flex-direction:column;gap:var(--space-3);flex:1;min-width:0;min-height:0;max-width:none;margin:0;padding:var(--space-5);overflow:auto}
.shell-main.sheets-active{overflow:hidden}
</style>
