<!-- 值对照对话框（PLAN-DM-016 任务 3，SPEC-DM-010 §5.3）：原文件值/草稿值/当前输入三阶段对照。
     只做呈现与焦点管理：阶段合并与取值由 PropertyValuePanel 计算；
     复用公共模态原语（modal-mask/modal-card），Esc=关闭、Tab 焦点圈闭、关闭后焦点回触发按钮。 -->
<script setup lang="ts">
import {ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import {useDialogFocus} from "../ui/dialogFocus";

export type CompareStage = {label: string; value: string | undefined};

const props = defineProps<{
  open: boolean;
  heading: string;   // 如「值对照 · 工程名称」
  stages: CompareStage[];
}>();
const emit = defineEmits<{close: []}>();
const {t} = useI18n();
const card = ref<HTMLElement | null>(null);

// 焦点管理统一交给 dialogFocus.ts（PLAN-DM-029 Task 10 Step 4）：打开了送焦点、Tab 圈闭、
// Escape 与关闭归还不再手写。与迁移前逐条等价：
// · `initialFocus: card` —— 保持既有落点（打开时聚焦对话框本身，而不是首个按钮）；
// · `opener` 由工具在打开时捕获（早于送焦点），无需本组件再存一个；
// · `onEscape` —— 原实现是 `stopPropagation()` + `emit("close")`；工具自己不阻止也不停止传播，
//   把原始事件交给回调，所以这段语义原样表达；
// · 圈闭 —— 本对话框只有「关闭对照」一个可聚焦元素，工具在 `first === last` 时同样会
//   `preventDefault()` 并把焦点留在原位：Tab 跑不出对话框（与手写实现一致）。
const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: (event) => { event.stopPropagation(); emit("close"); },
});

function display(value: string | undefined): string {
  if (value === undefined) return t("properties.compare.fieldMissing");
  if (value === "") return t("properties.compare.emptyText");
  return value;
}

</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onDialogKeydown">
    <div ref="card" class="modal-card compare-card" role="dialog" aria-modal="true" :aria-label="heading" tabindex="-1">
      <h2>{{ heading }}</h2>
      <p class="compare-hint">{{ $t("properties.compare.dialogHint") }}</p>
      <div v-for="stage in stages" :key="stage.label" class="compare-item">
        <small>{{ stage.label }}</small>
        <pre>{{ display(stage.value) }}</pre>
      </div>
      <div class="modal-actions">
        <UiButton variant="secondary" @click="emit('close')">{{ $t("properties.compare.close") }}</UiButton>
      </div>
    </div>
  </div>
</template>
<style scoped>
.compare-card{max-width:var(--compare-card-max-width)}
.compare-hint{margin:0 0 var(--space-3);color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.7}
.compare-item{padding:var(--space-3);background:var(--color-bg-canvas);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);margin-top:var(--space-2)}
.compare-item small{display:block;color:var(--color-text-secondary);margin-bottom:var(--space-1)}
.compare-item pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;max-height:var(--compare-item-max-height);overflow:auto}
</style>
