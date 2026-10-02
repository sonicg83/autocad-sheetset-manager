<script setup lang="ts">
import {computed} from "vue";
import UiIcon from "./UiIcon.vue";
import type {HintLive} from "./UiHint.vue";

export type UiBannerTone = "notice" | "success" | "warning" | "error";
const props = defineProps<{tone: UiBannerTone; id?: string; live?: HintLive}>();
const live = computed(() => props.live ?? "off");
const role = computed(() => live.value === "polite" ? "status" : live.value === "assertive" ? "alert" : undefined);
</script>
<template>
  <section
    :id="id"
    class="ui-banner"
    :class="`ui-banner--${tone}`"
    data-hint-kind="banner"
    :data-tone="tone"
    :role="role"
    :aria-live="live === 'off' ? undefined : live"
  >
    <UiIcon class="ui-banner__icon" name="status-dot" size="sm" />
    <div class="ui-banner__content"><slot /></div>
    <div v-if="$slots.actions" class="ui-banner__actions"><slot name="actions" /></div>
  </section>
</template>
<style scoped>
.ui-banner{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:var(--space-2);min-width:0;padding:var(--space-3);border:1px solid currentColor;border-inline-start-width:4px;border-radius:var(--radius-md);line-height:1.5;overflow-wrap:anywhere}
.ui-banner__icon{margin-top:2px}
.ui-banner__content{min-width:0}
.ui-banner__actions{display:flex;align-items:flex-start;gap:var(--space-2);flex-wrap:wrap}
.ui-banner--notice{color:var(--color-info);background:var(--color-info-bg)}
.ui-banner--success{color:var(--color-success);background:var(--color-success-bg)}
.ui-banner--warning{color:var(--color-warning);background:var(--color-warning-bg)}
.ui-banner--error{color:var(--color-danger);background:var(--color-danger-bg)}
</style>
