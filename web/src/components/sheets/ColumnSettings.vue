<script setup lang="ts">
// 显示列配置面板（PLAN-DM-015 任务 4，SPEC-DM-009 §5）。
// 固定列显示锁定状态；可选内置列与图纸自定义属性复选框；自定义属性多时支持名称搜索；
// 提供开关与「恢复默认」（仅影响当前图纸集）。第一版不提供拖拽排序。
// 面板打开状态自持：关闭后焦点回到「显示列」触发按钮；Esc/Tab 与确认模态同型键盘模型。
import {computed, nextTick, ref} from "vue";
import type {BuiltinPrefField, SheetColumnOption} from "../../composables/useSheetColumns";

const props = defineProps<{
  options: SheetColumnOption[];
  saveError: string;
  newPropertyCount: number;
}>();
const emit = defineEmits<{
  toggleBuiltin: [field: BuiltinPrefField, value: boolean];
  toggleProperty: [name: string, value: boolean];
  reset: [];
}>();

const open = ref(false);
const search = ref("");
const panel = ref<HTMLElement | null>(null);
const opener = ref<HTMLElement | null>(null);

const lockedOptions = computed(() => props.options.filter((item) => item.kind === "builtin" && item.fixed));
const builtinOptions = computed(() => props.options.filter((item) => item.kind === "builtin" && !item.fixed));
const hasProperties = computed(() => props.options.some((item) => item.kind === "sheet"));
// 名称搜索只过滤自定义属性；固定/可选内置列常显
const propertyOptions = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return props.options.filter((item) => item.kind === "sheet" && (!query || item.label.toLocaleLowerCase().includes(query)));
});

function openPanel() {
  opener.value = document.activeElement as HTMLElement | null;
  open.value = true;
  search.value = "";
  void nextTick(() => panel.value?.focus());
}
function closePanel() {
  open.value = false;
  opener.value?.focus();
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") { e.stopPropagation(); closePanel(); return; }
  if (e.key !== "Tab" || !panel.value) return;
  const items = Array.from(panel.value.querySelectorAll<HTMLElement>("button,input")).filter((el) => !el.hasAttribute("disabled"));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function onBuiltinChange(col: SheetColumnOption, event: Event) {
  if (col.prefField) emit("toggleBuiltin", col.prefField, (event.target as HTMLInputElement).checked);
}
function onPropertyChange(col: SheetColumnOption, event: Event) {
  if (col.name) emit("toggleProperty", col.name, (event.target as HTMLInputElement).checked);
}
</script>
<template>
  <span class="column-settings">
    <button type="button" class="cols-toggle" aria-haspopup="dialog" @click="openPanel">
      显示列<span v-if="newPropertyCount" class="cols-count">{{ newPropertyCount }} 个新字段</span>
    </button>
    <div v-if="open" class="cols-mask" @keydown="onKeydown" @click.self="closePanel">
      <div class="cols-panel" role="dialog" aria-modal="true" aria-label="显示列" tabindex="-1" ref="panel">
        <div class="cols-head">
          <h3 class="cols-title">显示列</h3>
          <button type="button" class="cols-close" @click="closePanel">关闭显示列</button>
        </div>
        <p class="cols-hint">固定列不可隐藏；配置按图纸集记忆，不影响搜索、筛选与完整属性编辑。</p>
        <p v-if="saveError" class="cols-error" role="alert">{{ saveError }}</p>
        <label class="cols-search">搜索自定义属性<input v-model="search" placeholder="按属性名称搜索"></label>
        <div class="cols-list">
          <div v-for="col in lockedOptions" :key="col.key" class="cols-option locked">
            <label class="cols-check"><input type="checkbox" checked disabled><span>{{ col.label }}</span><small>固定</small></label>
          </div>
          <div v-for="col in builtinOptions" :key="col.key" class="cols-option">
            <label class="cols-check">
              <input type="checkbox" :checked="col.visible" @change="onBuiltinChange(col, $event)">
              <span>{{ col.label }}</span>
            </label>
          </div>
          <h4 v-if="hasProperties" class="cols-section">图纸自定义属性</h4>
          <div v-for="col in propertyOptions" :key="col.key" class="cols-option">
            <label class="cols-check">
              <input type="checkbox" :checked="col.visible" @change="onPropertyChange(col, $event)">
              <span>{{ col.label }}</span>
            </label>
            <small v-if="col.newField" class="cols-new">新字段</small>
          </div>
        </div>
        <div class="cols-actions">
          <button type="button" class="cols-reset" @click="emit('reset')">恢复默认</button>
        </div>
      </div>
    </div>
  </span>
</template>
<style scoped>
.column-settings{display:inline-flex}
.cols-toggle{border:1px solid var(--color-border,var(--color-bg-surface-2));background:var(--color-bg-surface);color:var(--color-text-primary);border-radius:var(--radius-sm,6px);padding:4px 10px;font-size:13px;cursor:pointer;font-family:inherit}
.cols-toggle:hover{background:var(--color-bg-muted,var(--color-bg-surface-2))}
.cols-count{margin-left:6px;color:var(--color-accent);font-weight:600}
.cols-mask{position:fixed;inset:0;z-index:1000;background:rgba(16,24,40,.4);display:flex;align-items:center;justify-content:center}
.cols-panel{width:380px;max-width:calc(100vw - 32px);max-height:min(80vh,560px);display:flex;flex-direction:column;background:var(--color-bg-surface);border:1px solid var(--color-border,var(--color-bg-surface-2));border-radius:var(--radius-md,8px);box-shadow:var(--shadow-2,0 8px 24px #17203333);padding:var(--space-4);outline:none}
.cols-head{display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-2)}
.cols-title{margin:0;font-size:15px;color:var(--color-text-primary)}
.cols-close{margin-left:auto;border:none;background:none;color:var(--color-text-secondary);cursor:pointer;font-size:13px;padding:4px 8px;border-radius:var(--radius-sm,6px);font-family:inherit}
.cols-close:hover{background:var(--color-bg-muted,var(--color-bg-surface-2));color:var(--color-text-primary)}
.cols-hint{font-size:12px;color:var(--color-text-secondary);margin:0 0 var(--space-2);line-height:1.6}
.cols-error{font-size:12px;color:var(--color-danger,#c53030);margin:0 0 var(--space-2);background:var(--color-danger-soft,transparent);padding:6px 10px;border-radius:var(--radius-sm,6px)}
.cols-search{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--color-text-secondary);margin-bottom:var(--space-2)}
.cols-search input{flex:1;min-width:0}
.cols-list{overflow:auto;margin:0 0 var(--space-2);max-height:40vh}
.cols-option{display:flex;align-items:center;gap:8px;padding:6px 2px;font-size:13px}
.cols-check{display:inline-flex;align-items:center;gap:8px;color:var(--color-text-primary);cursor:pointer}
.cols-check input:disabled{cursor:not-allowed}
.cols-option.locked small{color:var(--color-text-muted);font-size:12px;margin-left:2px}
.cols-option small.cols-new{color:var(--color-accent);font-size:12px}
.cols-section{margin:var(--space-2) 0 0;font-size:12px;color:var(--color-text-secondary);font-weight:600}
.cols-actions{display:flex;justify-content:flex-end;padding-top:var(--space-2);border-top:1px solid var(--color-border,var(--color-bg-surface-2))}
.cols-reset{border:1px solid var(--color-border,var(--color-bg-surface-2));background:var(--color-bg-surface);color:var(--color-text-primary);border-radius:var(--radius-sm,6px);padding:4px 12px;font-size:13px;cursor:pointer;font-family:inherit}
.cols-reset:hover{background:var(--color-bg-muted,var(--color-bg-surface-2))}
</style>
