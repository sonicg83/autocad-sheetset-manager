<!-- 步骤引导面板：说明本步任务与完成条件，帮助用户理解门禁要求。 -->
<script setup lang="ts">
const props = defineProps<{
  title: string;
  goal: string;
  hints: string[];
}>();
</script>

<template>
  <section data-testid="guidance" class="guidance" aria-labelledby="guidance-title">
    <h2 id="guidance-title">{{ props.title }}</h2>
    <p class="goal">{{ props.goal }}</p>
    <ul v-if="props.hints.length > 0">
      <li v-for="hint in props.hints" :key="hint">{{ hint }}</li>
    </ul>
  </section>
</template>

<style scoped>
.guidance {
  margin-bottom: var(--space-5);
}

.goal {
  margin: var(--space-2) 0 0;
  color: var(--color-text-secondary);
}

ul {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-5);
  color: var(--color-text-muted);
  font-size: var(--font-size-13);
}
</style>
