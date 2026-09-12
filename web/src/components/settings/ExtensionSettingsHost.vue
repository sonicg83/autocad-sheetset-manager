<script setup lang="ts">
// 扩展配置子视图宿主（PLAN-DM-025 Task 7 / SPEC-DM-011 SC-17）。
// 它是同一设置 <dialog> 内的平级子视图：不叠加第二个设置模态，分区导航由对话框禁用，
// 唯一出路是可见「返回扩展列表」（脏状态先确认）。本组件独占一个扩展的设置状态
// （useExtensionSettings），并负责三件事：分派呈现、进入焦点、返回脏状态闸门。
//
// 分派规则（R17）：generated 由宿主按 items 生成表单；custom 只经编译期白名单组件解析，
// 未知/未登记的 route_key 一律 fail-closed 成稳定诊断——绝不按服务端字符串动态 import
// 或按名字查组件，也不把复杂设置退化为 JSON 文本框（SPEC-DM-011 §3.3、ARCH-DM-006 §7）。
import {computed, nextTick, onMounted, ref} from "vue";
import type {Component} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";
import {useConfirm} from "../../composables/useConfirm";
import {useExtensionSettings} from "../../composables/useExtensionSettings";
import GeneratedExtensionSettingsForm from "./GeneratedExtensionSettingsForm.vue";
import ConfirmModal from "../ui/ConfirmModal.vue";

// custom 专属组件的契约：与 generated 表单消费同一份 per-extension 状态
//（快照/编辑缓冲/脏标记/保存都在宿主，面板只做复杂交互）。
export interface CustomExtensionSettingsPanelProps {
  extensionId: string;
  state: ReturnType<typeof useExtensionSettings>;
}

// 编译期白名单：route_key → 专属组件。当前为空——图纸目录的 custom 面板属
// PLAN-DM-025 任务 8 的交付物，任务 7 不注册任何条目，因此生产卡片（唯一的
// dst-manager.sheet-catalog 声明 custom）此刻走 fail-closed 诊断态。
const CUSTOM_SETTINGS_PANELS: Record<string, Component<CustomExtensionSettingsPanelProps>> = {};

const props = defineProps<{extension: ExtensionSummary}>();
const emit = defineEmits<{back: []}>();
const {t} = useI18n();
const {state: confirmState, confirmAction, resolve: resolveConfirm} = useConfirm();

const settings = useExtensionSettings(props.extension.extension_id);
const {
  snapshot, items, loading, loadFailed, saving, saved, edits, fieldErrors,
  conflict, saveFailed, readOnly, dirty, load, setField, save, discardLocalEdits,
} = settings;

const hostEl = ref<HTMLElement | null>(null);
const name = computed(() => t(props.extension.name_key));
const customRouteKey = computed(() => props.extension.settings_contribution?.route_key ?? "");
// 白名单只认自有键（Object.hasOwn）：不命中 Object.prototype 上的同名属性
const customPanel = computed(() => {
  const routeKey = props.extension.settings_contribution?.route_key;
  return routeKey !== undefined && routeKey !== null && Object.hasOwn(CUSTOM_SETTINGS_PANELS, routeKey)
    ? CUSTOM_SETTINGS_PANELS[routeKey]
    : null;
});
const subView = computed<"generated" | "custom" | "unavailable">(() => {
  if (props.extension.settings_contribution?.presentation === "generated") return "generated";
  return customPanel.value === null ? "unavailable" : "custom";
});
const hasFieldErrors = computed(() => Object.keys(fieldErrors.value).length > 0);
// 保存可用性：加载中/只读/无改动/无快照都不可提交（空保存是 no-op，不由按钮之外表达）
const saveDisabled = computed(() => saving.value || readOnly.value || !dirty.value || snapshot.value === null);

// 进入焦点（§3.3）：优先子视图首个可用控件；只读或 fail-closed 状态下没有可用控件，
// 落到带 tabindex="-1" 的诊断条，任何状态下都不退回 <body>
function focusEntry(): void {
  const target = hostEl.value?.querySelector<HTMLElement>(
    "input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),[data-entry-focus]",
  );
  target?.focus();
}
onMounted(async () => {
  await load();
  await nextTick(); // 快照渲染完成后再定进入焦点（首字段控件 / 只读与不可用诊断条）
  focusEntry();
});

// 返回扩展列表：脏状态先确认（留在此处不丢弃输入）
async function back(): Promise<void> {
  if (confirmState.open) return; // 确认框自身打开时，Esc 与触发都归最上层确认框处理
  if (dirty.value) {
    const discard = await confirmAction({
      title: t("settings.extensionSettings.confirmBack.title"),
      message: t("settings.extensionSettings.confirmBack.message", {name: name.value}),
      confirmText: t("settings.extensionSettings.confirmBack.discard"),
      cancelText: t("settings.confirm.stay"),
    });
    if (!discard) return;
  }
  discardLocalEdits();
  emit("back");
}

function fieldLabel(key: string): string {
  const item = items.value.find(entry => entry.key === key);
  return item === undefined ? key : t(item.label_key);
}
// 按行数据属性定位字段：不把服务端返回的字段键拼进选择器字符串
function jumpToError(key: string): void {
  for (const row of Array.from(hostEl.value?.querySelectorAll<HTMLElement>("[data-field]") ?? [])) {
    if (row.dataset.field !== key) continue;
    row.scrollIntoView({block: "center"});
    row.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
    return;
  }
}
// 保存后焦点归还错误摘要（422）或保持原位：摘要由 save() 的失败路径决定是否出现
async function saveAndFocus(): Promise<void> {
  await save();
  if (hasFieldErrors.value) {
    await nextTick();
    hostEl.value?.querySelector<HTMLElement>('[data-testid="extension-settings-error-summary"]')?.focus();
  }
}

// 对话框的底部按钮与关闭闸门只读这三项；其余呈现状态留在本组件内部
defineExpose({dirty, saving, saved, saveDisabled, save: saveAndFocus, back});
</script>
<template>
  <section ref="hostEl" class="cfg" data-view="extension-config" aria-labelledby="extension-settings-title">
    <div class="cfg-head">
      <div class="cfg-title">
        <h3 id="extension-settings-title">{{ t("settings.extensionSettings.title", {name}) }}</h3>
        <span v-if="snapshot" class="badge">{{ t("settings.extensionSettings.revision", {revision: snapshot.revision}) }}</span>
        <span v-if="snapshot" class="badge">{{ t("settings.extensionSettings.schemaVersion", {schema_version: snapshot.schema_version}) }}</span>
        <span v-if="readOnly" class="badge warn">{{ t("settings.extensionSettings.readOnlyBadge") }}</span>
      </div>
      <p class="cfg-hint">{{ t("settings.extensionSettings.sharedNotice") }}</p>
    </div>

    <p v-if="loading && snapshot === null" class="f-hint" role="status">{{ t("settings.extensionSettings.loading") }}</p>
    <div v-else-if="loadFailed && snapshot === null" class="cfg-notice error">
      <p class="cfg-notice-text" role="alert">{{ t("settings.extensionSettings.loadFailed") }}</p>
      <button type="button" @click="load">{{ t("settings.retry") }}</button>
    </div>
    <template v-else-if="snapshot">
      <!-- 只读保护（EXTENSION_SETTINGS_SCHEMA_NEWER）：子视图内所有控件都禁用，
           焦点必须落在这条诊断上（tabindex=-1），不得退回 body -->
      <div v-if="readOnly" class="cfg-notice readonly" role="note" tabindex="-1" data-entry-focus data-testid="extension-settings-readonly">
        <p class="cfg-notice-text">{{ t("errors.extension.schemaNewer") }}</p>
        <p class="cfg-hint">{{ t("settings.extensions.diagnosticCode", {code: snapshot.diagnostic_code ?? ""}) }}</p>
      </div>
      <!-- 修订冲突（服务端 409）：本地编辑保留，提供「按新修订重试 / 放弃本地修改」两条出路 -->
      <div v-if="conflict" class="cfg-conflict" role="alert">
        <p class="cfg-conflict-title">{{ t("settings.extensionSettings.conflict.title") }}</p>
        <p class="cfg-conflict-text">{{ t("settings.extensionSettings.conflict.message", {name}) }}</p>
        <p class="cfg-hint">{{ t("settings.extensionSettings.conflict.diagnostic", {code: "EXTENSION_SETTINGS_INVALID", expected_revision: conflict.expectedRevision, current_revision: conflict.currentRevision}) }}</p>
        <div class="cfg-actions">
          <button type="button" :disabled="saving" @click="saveAndFocus">{{ t("settings.extensionSettings.conflict.retry") }}</button>
          <button type="button" :disabled="saving" @click="discardLocalEdits">{{ t("settings.extensionSettings.conflict.discard") }}</button>
        </div>
      </div>
      <!-- 非字段级保存失败（网络/5xx/未知）：就地横幅，输入不替换 -->
      <p v-if="saveFailed" class="cfg-notice error" role="alert">{{ saveFailed }}</p>
      <!-- 422 摘要：取得焦点，条目链接字段（与核心配置保存失败同一交互） -->
      <div v-if="hasFieldErrors" class="cfg-summary" role="alert" tabindex="-1" data-testid="extension-settings-error-summary">
        <p class="cfg-summary-title">{{ t("settings.extensionSettings.errors.summaryTitle") }}</p>
        <ul>
          <li v-for="(error, key) in fieldErrors" :key="key">
            <button type="button" class="cfg-link" @click="jumpToError(key)">{{ fieldLabel(key) }}: {{ error.message }}</button>
          </li>
        </ul>
      </div>

      <GeneratedExtensionSettingsForm
        v-if="subView === 'generated'"
        :items="items" :value="snapshot.value" :edits="edits" :errors="fieldErrors"
        :read-only="readOnly" @update="setField"
      />
      <component
        :is="customPanel" v-else-if="subView === 'custom'"
        :extension-id="extension.extension_id" :state="settings"
      />
      <!-- 未命中编译期白名单：稳定诊断 + 确定焦点落点（本任务生产卡片即此态） -->
      <div v-else class="cfg-notice" role="note" tabindex="-1" data-entry-focus data-testid="extension-settings-unavailable">
        <p class="cfg-notice-text">{{ t("settings.extensionSettings.customUnavailable", {route_key: customRouteKey}) }}</p>
      </div>
    </template>
    <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  </section>
</template>
<style scoped>
.cfg{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.cfg-head{border-bottom:1px solid var(--color-border-subtle);padding-bottom:var(--space-2)}
.cfg-title{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;margin-bottom:var(--space-1)}
.cfg-title h3{margin:0;font-size:13px}
.badge{font-size:12px;padding:2px 10px;border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary)}
.badge.warn{background:var(--color-warning-bg);color:var(--color-warning)}
.cfg-hint{margin:0;font-size:12px;color:var(--color-text-secondary);line-height:1.8}
.cfg-notice{border:1px solid var(--color-border-subtle);background:var(--color-bg-muted);color:var(--color-text-secondary);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3)}
.cfg-notice.error{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.cfg-notice.readonly{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.cfg-notice-text{margin:0 0 var(--space-2);font-size:12px;line-height:1.8}
.cfg-conflict{border:1px solid var(--color-warning);background:var(--color-warning-bg);color:var(--color-warning);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3)}
.cfg-conflict-title{margin:0;font-size:13px;font-weight:600}
.cfg-conflict-text{margin:0;font-size:12px;line-height:1.8}
.cfg-actions{display:flex;gap:var(--space-2);margin-top:var(--space-2);flex-wrap:wrap}
.cfg-actions button{padding:6px var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:13px}
.cfg-actions button:disabled{cursor:not-allowed;opacity:.5}
.cfg-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);font-size:12px;line-height:1.8}
.cfg-summary-title{margin:0;font-weight:600}
.cfg-summary ul{margin:0;padding:0;list-style:none}
.cfg-link{border:0;background:transparent;color:var(--color-danger);cursor:pointer;padding:0;font-size:12px;line-height:1.8;text-align:left;text-decoration:underline}
.cfg-notice button{margin-top:var(--space-1);padding:6px var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:13px}
</style>
