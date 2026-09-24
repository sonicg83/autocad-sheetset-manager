<script setup lang="ts">
// 第二阶段：项目信息（SPEC-DM-018 §3；PLAN-DM-036 Task 8）。
// 图纸集属性按标准动态生成：普通文本用输入框、枚举用选项控件，标明必填与标准默认值；
// 派生属性只读展示（待计算）。项目目录 = 已存在的上一级目录 + 可编辑目录名，界面展示
// 拼接后的完整最终路径；目录名不从任何属性推断，也不自动追加「(2)」等后缀。
// 桌面壳可用时走既有 `shell.select_folder` 桥；桥不可用时直接输入完整路径，后端同样校验。
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import FormField from "../ui/FormField.vue";
import UiButton from "../ui/UiButton.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import {selectSettingsPath, shellReady} from "../../api/shell";
import {creationTargetPath} from "../../features/creation/inputModel";
import type {CreationOrdinaryProperty} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{store: CreationStore}>();
const {t} = useI18n();

const properties = computed(() => props.store.standard?.sheetset_properties ?? []);
// 完整最终路径由纯函数合成（与草稿保存的 target_path 同一份实现）
const finalPath = computed(() => creationTargetPath(props.store.parentPath, props.store.folderName));
const derived = computed(() => props.store.standard?.derived_properties ?? []);
// 桥或 `select_folder` 方法缺失时按钮禁用并给出可见原因（三态语义见 api/shell.ts）
const folderPickerDisabled = ref(false);
const pickerUnavailable = computed(() => folderPickerDisabled.value || !shellReady.value);

function hintOf(property: CreationOrdinaryProperty): string {
  const parts = [
    t(property.kind === "enum" ? "creation.project.kindEnum" : "creation.project.kindText"),
    t(property.required ? "creation.project.required" : "creation.project.optional"),
    property.default_value === ""
      ? t("creation.project.defaultValueEmpty")
      : t("creation.project.defaultHint", {value: property.default_value}),
  ];
  return parts.join(" · ");
}

function valueOf(property: CreationOrdinaryProperty): string {
  return props.store.sheetsetValues[property.property_id] ?? "";
}

async function chooseParentFolder(): Promise<void> {
  const picked = await selectSettingsPath("folder", "");
  if (picked === undefined) {
    // 桥不可用：保留手动输入路径，不静默失败
    folderPickerDisabled.value = true;
    return;
  }
  if (picked === null) return; // 用户取消：路径保持不变
  props.store.setParentPath(picked);
}
</script>
<template>
  <section class="project-step" role="region" :aria-label="$t('creation.project.region')">
    <section class="card">
      <header class="card-head">
        <h2>{{ $t("creation.project.propertiesTitle") }}</h2>
        <p>{{ $t("creation.project.propertiesLead") }}</p>
      </header>
      <p v-if="properties.length === 0" class="note">{{ $t("creation.project.emptyProperties") }}</p>
      <div v-else class="field-grid">
        <FormField
          v-for="property in properties"
          :key="property.property_id"
          :label="property.name"
          :hint="hintOf(property)"
        >
          <template #default="{id, describedBy, invalid}">
            <UiSelect
              v-if="property.kind === 'enum'"
              :id="id"
              :described-by="describedBy"
              :invalid="invalid"
              :model-value="valueOf(property)"
              @update:model-value="(value: string) => store.setSheetsetValue(property.property_id, value)"
            >
              <option value="">{{ $t("creation.project.emptyValue") }}</option>
              <option v-for="option in property.options" :key="option.item_id" :value="option.value">
                {{ option.value }}
              </option>
            </UiSelect>
            <UiInput
              v-else
              :id="id"
              :described-by="describedBy"
              :invalid="invalid"
              :model-value="valueOf(property)"
              @update:model-value="(value: string) => store.setSheetsetValue(property.property_id, value)"
            />
          </template>
        </FormField>
      </div>
      <section v-if="derived.length > 0" class="derived">
        <h3>{{ $t("creation.project.derivedTitle") }}</h3>
        <p class="note">{{ $t("creation.project.derivedLead") }}</p>
        <ul>
          <li v-for="property in derived" :key="property.property_id">
            <span>{{ property.name }}</span>
            <span class="pending">{{ $t("creation.project.derivedPending") }}</span>
          </li>
        </ul>
      </section>
    </section>
    <section class="card">
      <header class="card-head">
        <h2>{{ $t("creation.project.pathTitle") }}</h2>
        <p>{{ $t("creation.project.pathLead") }}</p>
      </header>
      <div class="path-field">
        <FormField :label="$t('creation.project.parentLabel')" :hint="pickerUnavailable ? $t('creation.project.bridgeUnavailable') : undefined">
          <template #default="{id, describedBy, invalid}">
            <div class="parent-row">
              <UiInput
                :id="id"
                :described-by="describedBy"
                :invalid="invalid"
                :model-value="store.parentPath"
                :placeholder="$t('creation.project.parentPlaceholder')"
                @update:model-value="(value: string) => store.setParentPath(value)"
              />
              <UiButton variant="secondary" :disabled="pickerUnavailable" @click="chooseParentFolder">
                {{ $t("creation.project.chooseFolder") }}
              </UiButton>
            </div>
          </template>
        </FormField>
        <FormField :label="$t('creation.project.folderLabel')" :hint="$t('creation.project.folderHint')">
          <template #default="{id, describedBy, invalid}">
            <UiInput
              :id="id"
              :described-by="describedBy"
              :invalid="invalid"
              :model-value="store.folderName"
              @update:model-value="(value: string) => store.setFolderName(value)"
            />
          </template>
        </FormField>
      </div>
      <div class="final-path">
        <span class="final-path-label">{{ $t("creation.project.finalPath") }}</span>
        <span v-if="finalPath === ''" class="note">{{ $t("creation.project.finalPathEmpty") }}</span>
        <span v-else class="final-path-value" data-testid="creation-final-path">{{ finalPath }}</span>
      </div>
      <p class="note">{{ $t("creation.project.pathNote") }}</p>
      <p class="note">{{ $t("creation.project.nameBoundary") }}</p>
    </section>
  </section>
</template>
<style scoped>
.project-step{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-4);align-items:start}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);display:grid;gap:var(--space-3)}
.card-head h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.card-head p{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.note{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,var(--sheet-property-search-width)),1fr));gap:var(--space-3)}
.derived{border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3);display:grid;gap:var(--space-2)}
.derived h3{margin:0;font-size:var(--font-card-title);color:var(--color-text-primary)}
.derived ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.derived li{display:flex;justify-content:space-between;gap:var(--space-3);font-size:var(--font-label);color:var(--color-text-primary)}
.pending{color:var(--color-text-muted)}
.path-field{display:grid;gap:var(--space-3)}
.parent-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--space-2);align-items:end}
.final-path{display:grid;gap:var(--space-1);padding:var(--space-3);background:var(--color-bg-canvas);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md)}
.final-path-label{color:var(--color-text-secondary);font-size:var(--font-caption)}
.final-path-value{font-family:var(--font-mono);font-size:var(--font-label);color:var(--color-text-primary);word-break:break-all}
@media (max-width: 900px){
  .project-step{grid-template-columns:minmax(0,1fr)}
}
</style>
