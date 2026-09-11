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
  ><span class="switch-thumb" aria-hidden="true"></span></button>
</template>
<style scoped>
.switch{position:relative;flex:none;width:44px;height:24px;padding:0;border:1px solid var(--color-border-strong);border-radius:var(--radius-full);background:var(--color-bg-muted);cursor:pointer;transition:background-color .15s ease,border-color .15s ease}
.switch[aria-checked="true"]{background:var(--color-accent);border-color:var(--color-accent)}
.switch:disabled{cursor:not-allowed}
.switch-thumb{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:var(--radius-full);background:var(--color-bg-surface);box-shadow:var(--shadow-1);transition:transform .15s ease}
.switch[aria-checked="true"] .switch-thumb{transform:translateX(20px)}
@media (prefers-reduced-motion:reduce){.switch,.switch-thumb{transition:none}}
</style>
