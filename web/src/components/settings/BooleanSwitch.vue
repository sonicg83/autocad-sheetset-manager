<script setup lang="ts">
// 布尔状态控件唯一视觉语言（SPEC-DM-006 §6.3 / SPEC-DM-011 §3.3）：
// 「点击即落库的启停开关」与「随表单保存的布尔字段」共用本组件，语义差异由
// 调用方文案与"保存"按钮是否点亮传达，不由控件形态区分。
// 根元素是 button[role=switch]：Space/Enter 原生可切换，方向由 aria-checked 承担。
// 不渲染可见状态文字：冻结件中扩展开关的文字在左、bool 字段的文字在右，
// 文字由调用方布局（避免为一个组件引入两种内部顺序）。
// dataKey/inputId 保持既有契约：错误跳转依赖 [data-key] 可聚焦、表单 label 依赖 :for。
defineProps<{
  checked: boolean;
  disabled?: boolean;
  label: string;        // 可访问名（调用方本地化后传入）
  dataKey?: string;     // 写入根按钮的 [data-key]
  inputId?: string;     // 写入根按钮的 id，供 <label for> 关联
}>();
const emit = defineEmits<{change: [boolean]}>();
</script>
<template>
  <button
    :id="inputId" type="button" class="switch" role="switch"
    :data-key="dataKey" :aria-checked="checked" :aria-label="label" :disabled="disabled === true"
    @click="emit('change', !checked)"
  ><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span></button>
</template>
<style scoped>
/* 外层 button 承担可点盒（≥44×32，ARCH-DM-007 §10 / Step 3），**视觉轨道 44×24 移到内部
   元素上**：直接把 44×24 当可点盒会低于 32px 下限，而把轨道本身改成 ≥32 高会改变开关观感。
   两层拆分后「可点盒达标」与「轨道保持 44×24」同时成立。 */
.switch{position:relative;flex:none;display:inline-flex;align-items:center;justify-content:center;width:var(--settings-switch-width);min-height:var(--tap-target-min);padding:0;border:0;background:none;cursor:pointer}
.switch:disabled{cursor:not-allowed}
.switch-track{position:relative;display:block;width:var(--settings-switch-width);height:var(--settings-switch-height);border:1px solid var(--color-border-strong);border-radius:var(--radius-full);background:var(--color-bg-muted);transition:background-color .15s ease,border-color .15s ease}
.switch[aria-checked="true"] .switch-track{background:var(--color-accent);border-color:var(--color-accent)}
.switch-thumb{position:absolute;top:2px;left:2px;width:var(--settings-switch-thumb-size);height:var(--settings-switch-thumb-size);border-radius:var(--radius-full);background:var(--color-bg-surface);box-shadow:var(--shadow-1);transition:transform .15s ease}
.switch[aria-checked="true"] .switch-thumb{transform:translateX(20px)}
@media (prefers-reduced-motion:reduce){.switch-track,.switch-thumb{transition:none}}
</style>
