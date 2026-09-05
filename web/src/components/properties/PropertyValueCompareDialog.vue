<!-- 值对照对话框（PLAN-DM-016 任务 3，SPEC-DM-010 §5.3）：原文件值/草稿值/当前输入三阶段对照。
     只做呈现与焦点管理：阶段合并与取值由 PropertyValuePanel 计算；
     复用公共模态原语（modal-mask/modal-card），Esc=关闭、Tab 焦点圈闭、关闭后焦点回触发按钮。 -->
<script setup lang="ts">
import {nextTick, ref, watch} from "vue";

export type CompareStage = {label: string; value: string | undefined};

const props = defineProps<{
  open: boolean;
  heading: string;   // 如「值对照 · 工程名称」
  stages: CompareStage[];
}>();
const emit = defineEmits<{close: []}>();
const card = ref<HTMLElement | null>(null);
const opener = ref<Element | null>(null);

function display(value: string | undefined): string {
  if (value === undefined) return "（字段不存在）";
  if (value === "") return "（空文本）";
  return value;
}

watch(() => props.open, async (open) => {
  if (open) {
    opener.value = document.activeElement;
    await nextTick();
    card.value?.focus();
  } else {
    (opener.value as HTMLElement | null)?.focus?.();
  }
});

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") { event.stopPropagation(); emit("close"); return; }
  if (event.key !== "Tab" || !card.value) return;
  // 焦点圈闭：Tab 循环限制在模态内（对话框内只有「关闭对照」一个可聚焦控件）
  const items = Array.from(card.value.querySelectorAll<HTMLElement>("button")).filter((el) => !el.hasAttribute("disabled"));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onKeydown">
    <div ref="card" class="modal-card compare-card" role="dialog" aria-modal="true" :aria-label="heading" tabindex="-1">
      <h2>{{ heading }}</h2>
      <p class="compare-hint">三阶段按当前草稿链路对照；相同阶段合并展示。长文本完整显示，不截断。</p>
      <div v-for="stage in stages" :key="stage.label" class="compare-item">
        <small>{{ stage.label }}</small>
        <pre>{{ display(stage.value) }}</pre>
      </div>
      <div class="modal-actions">
        <button type="button" @click="emit('close')">关闭对照</button>
      </div>
    </div>
  </div>
</template>
<style scoped>
.compare-card{max-width:560px}
.compare-hint{margin:0 0 var(--space-3);color:var(--color-text-secondary);font-size:13px;line-height:1.7}
.compare-item{padding:var(--space-3);background:var(--color-bg-canvas);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);margin-top:var(--space-2)}
.compare-item small{display:block;color:var(--color-text-secondary);margin-bottom:var(--space-1)}
.compare-item pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;max-height:180px;overflow:auto}
</style>
