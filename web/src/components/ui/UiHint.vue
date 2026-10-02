<script setup lang="ts">
import {computed} from "vue";

export type HintKind = "lead" | "help" | "status" | "error";
export type HintTone = "neutral" | "info" | "success" | "warning" | "error";
export type HintLive = "off" | "polite" | "assertive";
type HintCommonProps = {id?: string; live?: HintLive};
export type UiHintProps = HintCommonProps & (
  | {kind: "lead" | "help"; tone?: never}
  | {kind: "status"; tone?: HintTone}
  | {kind: "error"; tone?: "error"}
);

const props = defineProps<UiHintProps>();
const live = computed(() => props.live ?? "off");
const role = computed(() => live.value === "polite" ? "status" : live.value === "assertive" ? "alert" : undefined);
const toneClass = computed(() => {
  if (props.kind === "error") return "ui-hint--tone-error";
  if (props.kind === "status") return `ui-hint--tone-${props.tone ?? "neutral"}`;
  return undefined;
});
</script>
<template>
  <div
    :id="id"
    class="ui-hint"
    :class="[`ui-hint--${kind}`, toneClass]"
    :data-hint-kind="kind"
    :data-tone="kind === 'status' ? (tone ?? 'neutral') : (kind === 'error' ? 'error' : undefined)"
    :role="role"
    :aria-live="live === 'off' ? undefined : live"
  >
    <slot />
  </div>
</template>
<style scoped>
.ui-hint{display:block;min-width:0;line-height:1.5;overflow-wrap:anywhere}
.ui-hint--lead{font-family:var(--font-ui);font-size:var(--font-label);color:var(--color-text-secondary)}
.ui-hint--help{font-family:var(--font-ui);font-size:var(--font-caption);color:var(--color-text-muted)}
.ui-hint--status,.ui-hint--error{font-family:var(--font-ui);font-size:var(--font-caption)}
.ui-hint--tone-neutral{color:var(--color-text-secondary)}
.ui-hint--tone-info{color:var(--color-info)}
.ui-hint--tone-success{color:var(--color-success)}
.ui-hint--tone-warning{color:var(--color-warning)}
.ui-hint--tone-error{color:var(--color-danger)}
</style>
