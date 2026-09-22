<script setup lang="ts">
// 枚举值编辑模态框（PLAN-DM-038 Task 6 / SPEC-DM-017 §4.1）。
//
// 契约：
// - 列表自上而下就是枚举顺序；顺序列只显示序号与可键盘操作的上移/下移控件；
// - 内部稳定 ID（`enum_item_id`）只存在于模型，不在任何界面位置显示；
// - 模态持有独立缓冲：取消丢弃本轮新增/删除/改名/排序，保存才一次性提交；
// - 宽度与最大高度施加在外层对话框，正文独立滚动，底部操作栏不参与滚动且不被裁切；
// - 焦点圈闭与关闭归还交给 `dialogFocus.ts`（与既有模态一致）。
import {computed, nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import UiButton from "../ui/UiButton.vue";
import UiIconButton from "../ui/UiIconButton.vue";
import UiInput from "../ui/UiInput.vue";
import {useDialogFocus} from "../ui/dialogFocus";
import {nextEnumItemId, type DraftEnumItem, type DraftEnumProperty} from "../../features/standards/draftModel";

const props = defineProps<{
  open: boolean;
  property: DraftEnumProperty | null;
  /** 引用该枚举的映射属性名（保存后进入待确认状态）。 */
  impactedNames?: string[];
}>();
const emit = defineEmits<{save: [items: DraftEnumItem[]]; cancel: []}>();
const {t} = useI18n();

const card = ref<HTMLElement | null>(null);
const items = ref<DraftEnumItem[]>([]);

// 每次打开都从属性当前枚举重建缓冲：取消不留痕，重复打开也不会累积上一轮编辑。
watch(
  () => props.open,
  open => {
    if (!open) return;
    items.value = (props.property?.enum_items ?? []).map(item => ({...item}));
  },
  {immediate: true},
);

const {onDialogKeydown} = useDialogFocus({
  open: () => props.open,
  container: card,
  initialFocus: card,
  onEscape: event => {
    event.stopPropagation();
    emit("cancel");
  },
});

const impactText = computed(() => {
  const names = props.impactedNames ?? [];
  if (names.length === 0) return t("standards.enumDialog.noImpact");
  return t("standards.enumDialog.impacted", {
    count: names.length,
    names: names.join(t("standards.enumDialog.nameSeparator")),
  });
});

function move(index: number, delta: number): void {
  const target = index + delta;
  if (target < 0 || target >= items.value.length) return;
  const [moved] = items.value.splice(index, 1);
  if (moved === undefined) return;
  items.value.splice(target, 0, moved);
}

/** 新增项在模型里生成稳定 ID，但在当前缓冲内必须唯一（多次新增不重号）。 */
function freshItemId(): string {
  const base = props.property === null ? "enum-new" : nextEnumItemId(props.property, "enum-new");
  const used = new Set(items.value.map(item => item.item_id));
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

async function add(): Promise<void> {
  const item: DraftEnumItem = {item_id: freshItemId(), value: ""};
  items.value.push(item);
  await nextTick();
  card.value
    ?.querySelector<HTMLInputElement>(`[data-testid="enum-value-${item.item_id}"]`)
    ?.focus();
}

function remove(index: number): void {
  items.value.splice(index, 1);
}

function save(): void {
  emit("save", items.value.map(item => ({...item})));
}
</script>
<template>
  <div v-if="open && property" class="modal-mask" @keydown="onDialogKeydown">
    <div
      ref="card"
      class="enum-dialog"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-label="$t('standards.enumDialog.title', {name: property.name})"
      data-testid="enum-dialog"
    >
      <header class="dialog-head">
        <div class="head-text">
          <h2 class="dialog-title">{{ $t("standards.enumDialog.title", {name: property.name}) }}</h2>
          <p class="dialog-hint">{{ $t("standards.enumDialog.hint") }}</p>
        </div>
        <span class="scope-badge">{{ property.scope }}</span>
      </header>
      <div class="dialog-body">
        <p class="impact-note" role="note" data-testid="enum-impact">{{ impactText }}</p>
        <div class="enum-head" aria-hidden="true">
          <span>{{ $t("standards.enumDialog.order") }}</span>
          <span>{{ $t("standards.enumDialog.value") }}</span>
          <span></span>
        </div>
        <div v-for="(item, index) in items" :key="item.item_id" class="enum-row">
          <span class="enum-order">
            <span class="enum-sequence">{{ String(index + 1).padStart(2, "0") }}</span>
            <UiIconButton
              icon="chevron-up"
              :label="$t('standards.enumDialog.moveUp', {name: item.value || String(index + 1)})"
              :disabled="index === 0"
              :data-testid="`enum-up-${item.item_id}`"
              @click="move(index, -1)"
            />
            <UiIconButton
              icon="chevron-down"
              :label="$t('standards.enumDialog.moveDown', {name: item.value || String(index + 1)})"
              :disabled="index === items.length - 1"
              :data-testid="`enum-down-${item.item_id}`"
              @click="move(index, 1)"
            />
          </span>
          <UiInput
            v-model="item.value"
            :label="$t('standards.enumDialog.value')"
            :data-testid="`enum-value-${item.item_id}`"
          />
          <UiIconButton
            icon="close"
            :label="$t('standards.enumDialog.remove')"
            :data-testid="`enum-delete-${item.item_id}`"
            @click="remove(index)"
          />
        </div>
        <div class="body-actions">
          <UiButton variant="secondary" size="compact" data-testid="add-enum" @click="add">
            {{ $t("standards.enumDialog.add") }}
          </UiButton>
        </div>
      </div>
      <footer class="dialog-foot">
        <UiButton variant="secondary" data-testid="cancel-enum" @click="emit('cancel')">
          {{ $t("standards.enumDialog.cancel") }}
        </UiButton>
        <UiButton variant="primary" data-testid="save-enum" @click="save">
          {{ $t("standards.enumDialog.save") }}
        </UiButton>
      </footer>
    </div>
  </div>
</template>
<style scoped>
/* 宽度与最大高度只在外层对话框：正文滚动，底部操作栏固定可见（不被裁切）。 */
.enum-dialog{
  display:flex;flex-direction:column;
  width:min(880px,calc(100vw - 32px));max-height:calc(100vh - 42px);
  overflow:hidden;outline:none;
  background:var(--color-bg-surface);color:var(--color-text-primary);
  border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);box-shadow:var(--shadow-3);
}
.dialog-head{display:flex;flex:0 0 auto;align-items:flex-start;gap:var(--space-3);padding:var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.head-text{display:grid;gap:var(--space-1);min-width:0}
.dialog-title{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.dialog-hint{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.scope-badge{flex:0 0 auto;padding:0 var(--space-2);border:1px solid var(--color-border-subtle);border-radius:var(--radius-full);font-size:var(--font-label);color:var(--color-text-secondary)}
.dialog-body{flex:1 1 auto;min-height:0;overflow:auto;display:grid;gap:var(--space-2);padding:var(--space-4)}
.impact-note{margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);font-size:var(--font-label);color:var(--color-text-secondary)}
.enum-head,.enum-row{display:grid;grid-template-columns:minmax(120px,140px) minmax(0,1fr) 44px;gap:var(--space-2);align-items:center}
.enum-head{font-size:var(--font-label);color:var(--color-text-secondary)}
.enum-order{display:flex;align-items:center;gap:var(--space-1)}
.enum-sequence{text-align:center;color:var(--color-text-muted);font-variant-numeric:tabular-nums;font-size:var(--font-label)}
.body-actions{display:flex}
.dialog-foot{display:flex;flex:0 0 auto;justify-content:flex-end;gap:var(--space-2);padding:var(--space-3) var(--space-4);border-top:1px solid var(--color-border-subtle);background:var(--color-bg-muted)}
</style>
