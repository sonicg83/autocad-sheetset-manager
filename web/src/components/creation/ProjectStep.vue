<script setup lang="ts">
// 第二阶段：项目信息（SPEC-DM-018 §3；PLAN-DM-036 Task 8）。
// 图纸集属性按标准动态生成：普通文本用输入框、枚举与级联属性用候选控件，必填属性在名称旁
// 渲染醒目星号（FormField 的 required，控件上另绑 aria-required）；默认值仍由草稿初建
// 时应用，不在字段下重复展示说明小字。派生属性只读：图纸集作用域的派生属性把界面当前
// 输入交给后端实时求值（store.refreshDerived，输入防抖触发）；图纸作用域依赖逐张编号
// 与标题，只能在权威预览中求值。项目目录 = 已存在的上一级目录 + 可编辑目录名，界面展示
// 拼接后的完整最终路径；目录名不从任何属性推断，也不自动追加「(2)」等后缀。
// 桌面壳可用时走既有 `shell.select_folder` 桥；桥不可用时直接输入完整路径，后端同样校验。
import {computed, onBeforeUnmount, onMounted, ref, watch} from "vue";
import FormField from "../ui/FormField.vue";
import UiButton from "../ui/UiButton.vue";
import UiHint from "../ui/UiHint.vue";
import UiInput from "../ui/UiInput.vue";
import UiSelect from "../ui/UiSelect.vue";
import {nextInstanceId} from "../ui/instanceId";
import {selectSettingsPath, shellReady} from "../../api/shell";
import {creationCascadeOptions, creationTargetPath} from "../../features/creation/inputModel";
import {groupCascadeHelp} from "../../features/creation/cascadeHelp";
import type {CascadeHelpGroup} from "../../features/creation/cascadeHelp";
import type {CreationCascadeProperty, CreationDerivedProperty, CreationInputProperty} from "../../features/creation/types";
import type {CreationStore} from "../../features/creation/store";

const props = defineProps<{store: CreationStore}>();

const componentInstanceId = nextInstanceId("creation-project");
const properties = computed(() => props.store.standard?.sheetset_properties ?? []);
const cascadeHelpGroups = computed(() => {
  const disabled = properties.value.filter(
    (property): property is CreationCascadeProperty => property.kind === "cascade" && cascadeDisabled(property),
  );
  return groupCascadeHelp(componentInstanceId, "sheetset", disabled.map(property => ({
    propertyId: property.property_id,
    sourcePropertyId: property.source_property_id,
    sourceName: properties.value.find(source => source.property_id === property.source_property_id)?.name
      ?? property.source_property_id,
  })));
});
// 完整最终路径由纯函数合成（与草稿保存的 target_path 同一份实现）
const finalPath = computed(() => creationTargetPath(props.store.parentPath, props.store.folderName));
const derived = computed(() => props.store.standard?.derived_properties ?? []);
// 桥或 `select_folder` 方法缺失时按钮禁用并给出可见原因（三态语义见 api/shell.ts）
const folderPickerDisabled = ref(false);
const pickerUnavailable = computed(() => folderPickerDisabled.value || !shellReady.value);

function valueOf(property: CreationInputProperty): string {
  return props.store.sheetsetValues[property.property_id] ?? "";
}

function optionsOf(property: CreationInputProperty): Array<{id: string; value: string}> {
  if (property.kind === "cascade") {
    return creationCascadeOptions(props.store.standard!, property, props.store.sheetsetValues)
      .map(value => ({id: value, value}));
  }
  return property.options.map(option => ({id: option.item_id, value: option.value}));
}

function cascadeDisabled(property: CreationInputProperty): boolean {
  return property.kind === "cascade"
    && valueOf(property) === ""
    && optionsOf(property).length === 0;
}

function cascadeHelpFor(propertyId: string): CascadeHelpGroup | undefined {
  return cascadeHelpGroups.value.find(group => group.propertyIds.includes(propertyId));
}

function isFirstCascadeHelp(propertyId: string): boolean {
  return cascadeHelpFor(propertyId)?.propertyIds[0] === propertyId;
}

function showSavedCascadeValue(property: CreationInputProperty): boolean {
  return property.kind === "cascade"
    && valueOf(property) !== ""
    && !optionsOf(property).some(option => option.value === valueOf(property));
}

/** 图纸集作用域派生属性的实时值；无值（未算出/被阻断）返回 undefined 回退「待计算」。 */
function derivedValueOf(property: CreationDerivedProperty): string | undefined {
  if (property.scope !== "sheetset") return undefined;
  return props.store.derivedValues[property.property_id];
}

// 输入变化防抖后请求后端实时求值（只读，不改草稿与预览状态）；进入页面先算一次
let deriveTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleDerivedRefresh(): void {
  clearTimeout(deriveTimer);
  deriveTimer = setTimeout(() => { void props.store.refreshDerived(); }, 300);
}
watch(() => props.store.sheetsetValues, scheduleDerivedRefresh);
onMounted(() => { void props.store.refreshDerived(); });
onBeforeUnmount(() => clearTimeout(deriveTimer));

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
        <UiHint kind="lead">{{ $t("creation.project.propertiesLead") }}</UiHint>
      </header>
      <p v-if="properties.length === 0" class="note">{{ $t("creation.project.emptyProperties") }}</p>
      <div v-else class="field-grid">
        <FormField
          v-for="property in properties"
          :key="property.property_id"
          :label="property.name"
          :required="property.required"
          :shared-described-by="cascadeHelpFor(property.property_id)?.id"
        >
          <template #default="{id, describedBy, invalid}">
            <UiSelect
              v-if="property.kind !== 'text'"
              :id="id"
              :described-by="describedBy"
              :invalid="invalid"
              :disabled="cascadeDisabled(property)"
              :aria-required="property.required ? 'true' : undefined"
              :model-value="valueOf(property)"
              @update:model-value="(value: string) => store.setSheetsetValue(property.property_id, value)"
            >
              <option value="">{{ $t("creation.project.emptyValue") }}</option>
              <option v-if="showSavedCascadeValue(property)" :value="valueOf(property)">
                {{ valueOf(property) }} · {{ $t("creation.cascade.invalidSavedValue") }}
              </option>
              <option v-for="option in optionsOf(property)" :key="option.id" :value="option.value">
                {{ option.value }}
              </option>
            </UiSelect>
            <UiInput
              v-else
              :id="id"
              :described-by="describedBy"
              :invalid="invalid"
              :aria-required="property.required ? 'true' : undefined"
              :model-value="valueOf(property)"
              @update:model-value="(value: string) => store.setSheetsetValue(property.property_id, value)"
            />
            <UiHint v-if="isFirstCascadeHelp(property.property_id)" :id="cascadeHelpFor(property.property_id)?.id" kind="help">
              {{ $t("creation.cascade.chooseParent", {parent: cascadeHelpFor(property.property_id)?.sourceName}) }}
            </UiHint>
          </template>
        </FormField>
      </div>
      <section v-if="derived.length > 0" class="derived">
        <h3>{{ $t("creation.project.derivedTitle") }}</h3>
        <UiHint kind="help">{{ $t("creation.project.derivedLead") }}</UiHint>
        <ul>
          <li v-for="property in derived" :key="property.property_id">
            <span>{{ property.name }}</span>
            <span
              v-if="derivedValueOf(property) !== undefined"
              class="derived-value"
              data-testid="creation-derived-value"
            >{{ derivedValueOf(property) === "" ? $t("creation.project.emptyValue") : derivedValueOf(property) }}</span>
            <span
              v-else-if="property.scope === 'sheet'"
              class="pending"
            >{{ $t("creation.project.derivedSheetPending") }}</span>
            <span v-else class="pending">{{ $t("creation.project.derivedPending") }}</span>
          </li>
        </ul>
      </section>
    </section>
    <section class="card">
      <header class="card-head">
        <h2>{{ $t("creation.project.pathTitle") }}</h2>
        <UiHint kind="lead">{{ $t("creation.project.pathLead") }}</UiHint>
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
      <UiHint kind="help">{{ $t("creation.project.pathNote") }}</UiHint>
      <UiHint kind="help">{{ $t("creation.project.nameBoundary") }}</UiHint>
    </section>
  </section>
</template>
<style scoped>
.project-step{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-4);align-items:start}
.card{padding:var(--space-4);background:var(--color-bg-surface);border:1px solid var(--color-border-subtle);border-radius:var(--radius-lg);display:grid;gap:var(--space-3)}
.card-head h2{margin:0;font-size:var(--font-title);color:var(--color-text-primary)}
.note{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);line-height:1.6}
.field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,var(--sheet-property-search-width)),1fr));gap:var(--space-3)}
.derived{border-top:1px solid var(--color-border-subtle);padding-top:var(--space-3);display:grid;gap:var(--space-2)}
.derived h3{margin:0;font-size:var(--font-card-title);color:var(--color-text-primary)}
.derived ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-1)}
.derived li{display:flex;justify-content:space-between;gap:var(--space-3);font-size:var(--font-label);color:var(--color-text-primary)}
.derived-value{font-family:var(--font-mono);color:var(--color-text-primary);word-break:break-all;text-align:right}
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
