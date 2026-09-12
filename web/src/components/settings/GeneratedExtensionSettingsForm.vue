<script setup lang="ts">
// generated 扩展设置表单（PLAN-DM-025 Task 7 / SPEC-DM-011 SC-17）。
// 宿主按服务端合并后的 items 生成表单：字段顺序、label_key/description_key 来自清单，
// 控件类型、默认值与约束来自 Provider，两者都不在本层重新解释。
//
// 控件词表与设置中心应用设置词表不同源（后端 SettingsFieldControl 注释：integer/boolean
// 对应设置中心的 int/bool，number/string 在设置中心没有对应项）。因此本文件是唯一的
// 映射点，且必须编译期穷尽：词表新增取值会让 CONTROL_KINDS 缺键而类型报错；运行时遇到
// 契约外取值（如 object/array）一律 fail-closed 成不支持诊断，绝不退化为 JSON 文本框。
import {useI18n} from "vue-i18n";
import type {ExtensionSettingsFieldControl, ExtensionSettingsItem} from "../../api/contracts";
import type {ExtensionFieldError} from "../../composables/useExtensionSettings";
import BooleanSwitch from "./BooleanSwitch.vue";

// 扩展设置控件 → 表单控件：boolean 复用设置中心既有滑动开关（与核心 bool 字段同形态）
type FormControlKind = "boolean" | "integer" | "number" | "string" | "enum";
const CONTROL_KINDS: Record<ExtensionSettingsFieldControl, FormControlKind> = {
  boolean: "boolean",
  integer: "integer",
  number: "number",
  string: "string",
  enum: "enum",
};
const UNSUPPORTED = "unsupported" as const;

function controlKind(control: string): FormControlKind | typeof UNSUPPORTED {
  return (CONTROL_KINDS as Record<string, FormControlKind | undefined>)[control] ?? UNSUPPORTED;
}

const props = defineProps<{
  items: ExtensionSettingsItem[];
  value: Record<string, unknown>; // 服务端持久值（字段缺失时回退 Provider 默认值）
  edits: Record<string, unknown>; // 本地编辑缓冲（父级唯一所有者）
  errors: Record<string, ExtensionFieldError>;
  readOnly: boolean;
}>();
const emit = defineEmits<{update: [key: string, value: unknown]}>();
const {t} = useI18n();

function inputId(key: string): string {
  return `extension-settings-input-${key}`;
}
// 生效显示值：编辑缓冲优先 → 服务端持久值 → Provider 默认值
function current(item: ExtensionSettingsItem): unknown {
  if (item.key in props.edits) return props.edits[item.key];
  if (item.key in props.value) return props.value[item.key];
  return item.default;
}
function scalarText(item: ExtensionSettingsItem): string {
  const value = current(item);
  return value === null || value === undefined ? "" : String(value);
}
// 数值控件：空输入按 null（nullable）或空串上送（非空约束由 Provider 判定），
// 非空按数值上送——前端不静默改写用户输入，越界值由 422 行内定位
function onNumberInput(item: ExtensionSettingsItem, event: Event): void {
  const raw = (event.target as HTMLInputElement).value;
  if (raw === "") {
    emit("update", item.key, item.nullable ? null : "");
    return;
  }
  const parsed = Number(raw);
  emit("update", item.key, Number.isFinite(parsed) ? parsed : raw);
}
function errorOf(item: ExtensionSettingsItem): ExtensionFieldError | undefined {
  return props.errors[item.key];
}
</script>
<template>
  <div class="ef-form">
    <div
      v-for="item in items" :key="item.key" class="ef-row"
      :class="{dirty: item.key in edits, error: errorOf(item) !== undefined}" :data-field="item.key"
    >
      <label class="ef-label" :for="inputId(item.key)">{{ t(item.label_key) }}</label>
      <div class="ef-main">
        <BooleanSwitch
          v-if="controlKind(item.control) === 'boolean'"
          :checked="Boolean(current(item))" :disabled="readOnly" :label="t(item.label_key)"
          :data-key="item.key" :input-id="inputId(item.key)"
          @change="value => emit('update', item.key, value)"
        />
        <input
          v-else-if="controlKind(item.control) === 'integer' || controlKind(item.control) === 'number'"
          :id="inputId(item.key)" type="number" :data-key="item.key" :value="scalarText(item)"
          :step="controlKind(item.control) === 'integer' ? '1' : 'any'"
          :min="item.min_value ?? undefined" :max="item.max_value ?? undefined"
          :disabled="readOnly" :aria-label="t(item.label_key)" :aria-invalid="errorOf(item) !== undefined"
          @input="event => onNumberInput(item, event)"
        >
        <input
          v-else-if="controlKind(item.control) === 'string'"
          :id="inputId(item.key)" type="text" :data-key="item.key" :value="scalarText(item)"
          :disabled="readOnly" :aria-label="t(item.label_key)" :aria-invalid="errorOf(item) !== undefined"
          @input="event => emit('update', item.key, (event.target as HTMLInputElement).value)"
        >
        <span
          v-else-if="controlKind(item.control) === 'enum'" class="ef-radio-line"
          role="radiogroup" :aria-label="t(item.label_key)"
        >
          <label v-for="option in item.options" :key="option">
            <input
              type="radio" :name="`extension-settings-radio-${item.key}`" :data-key="item.key"
              :value="option" :checked="scalarText(item) === option" :disabled="readOnly"
              @change="emit('update', item.key, option)"
            >{{ option }}
          </label>
        </span>
        <!-- 契约外控件：稳定诊断，不猜测语义、不提供任意 JSON 文本框（SC-17） -->
        <p v-else class="ef-hint" role="note">{{ t("settings.extensionSettings.unsupportedControl", {control: item.control}) }}</p>
        <div v-if="item.description_key || item.min_value !== null" class="ef-foot">
          <span v-if="item.description_key" class="ef-hint">{{ t(item.description_key) }}</span>
          <span v-if="item.min_value !== null" class="ef-hint">{{ item.min_value }}–{{ item.max_value }}</span>
        </div>
        <p v-if="errorOf(item)" class="ef-error" role="alert">{{ errorOf(item)?.message }}</p>
      </div>
    </div>
  </div>
</template>
<style scoped>
.ef-form{display:flex;flex-direction:column;gap:var(--space-1)}
.ef-row{display:grid;grid-template-columns:150px 1fr;gap:var(--space-2) var(--space-3);padding:var(--space-2) var(--space-3);border:1px solid transparent;border-radius:var(--radius-md);align-items:start}
.ef-row:focus-within{background:var(--color-bg-canvas)}
.ef-row.dirty{border-color:var(--color-warning);background:var(--color-warning-bg)}
.ef-row.error{border-color:var(--color-danger);background:var(--color-danger-bg)}
.ef-label{font-size:13px;font-weight:500;padding-top:var(--space-2);color:var(--color-text-primary)}
.ef-main{display:flex;flex-direction:column;gap:var(--space-1);min-width:0;align-items:flex-start}
.ef-main input[type="text"],.ef-main input[type="number"]{width:100%;height:34px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);padding:0 var(--space-2)}
.ef-main input:disabled{opacity:.5;cursor:not-allowed}
.ef-radio-line{display:flex;gap:var(--space-4);padding-top:var(--space-2);flex-wrap:wrap}
.ef-radio-line label{display:flex;gap:var(--space-1);align-items:center;font-size:13px;color:var(--color-text-primary)}
.ef-foot{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap;min-height:24px}
.ef-hint{margin:0;font-size:12px;color:var(--color-text-secondary);line-height:1.7}
.ef-error{margin:0;font-size:12px;color:var(--color-danger);line-height:1.6}
@media (max-width:900px){.ef-row{grid-template-columns:1fr}}
</style>
