<script setup lang="ts">
// 逐张属性值模态（SPEC-DM-018 §6.1；PLAN-DM-036 Task 9）。
// 组内某个 sheet 属性的取值不一致时，主表只显示第一张实际值加「…」；本模态按组内顺序列出
// **全部图纸**的「图号｜图纸标题｜该属性实际值」，只展示所点属性，不改变主表一组一行的结构。
// 值来自后端预览的逐张明细（`property_cells[property_id].sheets`），图纸标题取同一组的
// `sheets`，前端不推算任何值。键盘：打开时焦点进入模态、Tab 圈定、Esc 或关闭按钮退出并把
// 焦点归还触发按钮（`useDialogFocus`）。
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import type {CreationPreviewPropertyColumn} from "../../features/creation/previewModel";
import type {CreationPreviewGroup} from "../../features/creation/types";

const props = defineProps<{
  open: boolean;
  group: CreationPreviewGroup | null;
  column: CreationPreviewPropertyColumn | null;
}>();
const emit = defineEmits<{close: []}>();
const {t} = useI18n();

const card = ref<HTMLElement | null>(null);

const title = computed(() =>
  props.group === null || props.column === null
    ? ""
    : t("creation.review.valuesTitle", {group: props.group.title, property: props.column.label}),
);
/** 逐张明细：顺序取属性明细自身的组内顺序，标题按图号从同组图纸取（同一份后端计划）。 */
const rows = computed(() => {
  if (props.group === null || props.column === null) return [];
  const titles = new Map(props.group.sheets.map(sheet => [sheet.number, sheet.title]));
  return (props.group.property_cells[props.column.property_id]?.sheets ?? []).map(row => ({
    number: row.number,
    title: titles.get(row.number) ?? "",
    value: row.value,
  }));
});

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("close");
  },
});
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card" class="modal-card values-card" role="dialog" aria-modal="true"
      :aria-label="title" tabindex="-1"
    >
      <h2>{{ title }}</h2>
      <p class="values-lead">
        {{ $t("creation.review.valuesLead", {count: rows.length}) }}
      </p>
      <div class="table-scroll">
        <table class="values-table">
          <thead>
            <tr>
              <th>{{ $t("creation.review.valuesSheetNumber") }}</th>
              <th>{{ $t("creation.review.valuesSheetTitle") }}</th>
              <th>{{ column?.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.number">
              <td class="mono">{{ row.number }}</td>
              <td>{{ row.title }}</td>
              <td>{{ row.value === "" ? $t("creation.review.emptyValue") : row.value }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="modal-actions">
        <UiButton variant="secondary" @click="emit('close')">
          {{ $t("creation.review.valuesClose") }}
        </UiButton>
      </div>
    </div>
  </div>
</template>
<style scoped>
.values-card{display:grid;gap:var(--space-3)}
.values-lead{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
/* 主表与模态各自横向滚动：900×768 下页面整体不横溢 */
.table-scroll{overflow-x:auto;min-width:0}
.values-table{width:100%;border-collapse:collapse}
.values-table th,.values-table td{padding:var(--space-1);border-bottom:1px solid var(--color-border-subtle);text-align:left}
.values-table th{font-size:var(--font-label);color:var(--color-text-secondary);font-weight:500;white-space:nowrap}
.values-table td{font-size:var(--font-label);color:var(--color-text-primary)}
</style>
