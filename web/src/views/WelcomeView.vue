<script setup lang="ts">
import {ref} from "vue";
defineProps<{hasShell:boolean}>();
const emit=defineEmits<{select:[];submitPath:[path:string]}>();
const path=ref("");
</script>
<template>
  <section class="welcome-card" role="region" :aria-label="$t('shell.welcome.region')">
    <h2 class="welcome-title">{{ $t("shell.welcome.title") }}</h2>
    <p class="welcome-desc">{{ $t("shell.welcome.desc") }}</p>
    <template v-if="!hasShell">
      <div class="no-shell">
        <input v-model="path" :placeholder="$t('shell.welcome.pathPlaceholder')" @keyup.enter="$emit('submitPath',path)">
        <button type="button" @click="$emit('submitPath',path)">{{ $t("shell.welcome.openProject") }}</button>
      </div>
    </template>
    <template v-else>
      <button type="button" class="primary" @click="$emit('select')">{{ $t("shell.welcome.selectDst") }}</button>
      <p class="drop-hint">{{ $t("shell.welcome.dropHint") }}</p>
    </template>
  </section>
</template>
<style scoped>
.welcome-card{max-width:520px;margin:12vh auto;padding:var(--space-5);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-1);text-align:center}
.welcome-title{font-size:20px;margin:0 0 var(--space-2);color:var(--color-text-primary)}
.welcome-desc{color:var(--color-text-secondary);font-size:13px;margin:0 0 var(--space-5);line-height:1.6}
.no-shell{display:flex;gap:var(--space-2);margin:0 auto;max-width:420px}
.no-shell input{flex:1;min-width:0;height:36px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);padding:0 var(--space-3);font-family:inherit;font-size:13px}
.no-shell button{height:36px;padding:0 var(--space-4);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:13px}
.drop-hint{color:var(--color-text-muted);font-size:13px;margin:var(--space-4) 0 0}
.welcome-card .primary{background:var(--color-accent);color:var(--color-on-accent);border:1px solid transparent;border-radius:var(--radius-md);height:38px;padding:0 var(--space-5);font-weight:500;cursor:pointer;font-size:14px}
.welcome-card .primary:hover{background:var(--color-accent-hover)}
</style>
