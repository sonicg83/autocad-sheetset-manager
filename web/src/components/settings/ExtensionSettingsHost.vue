<script setup lang="ts">
// 扩展配置子视图宿主（PLAN-DM-025 Task 7 / SPEC-DM-011 SC-17）。
// 它是同一设置 <dialog> 内的平级子视图：不叠加第二个设置模态，分区导航由对话框禁用，
// 唯一出路是可见「返回扩展列表」（脏状态先确认）。本组件独占一个扩展的设置状态
// （useExtensionSettings），并负责三件事：分派呈现、进入焦点、返回脏状态闸门。
//
// 分派规则（R17）：generated 由宿主按 items 生成表单；custom 只经编译期白名单组件解析，
// 未知/未登记的 route_key 一律 fail-closed 成稳定诊断——绝不按服务端字符串动态 import
// 或按名字查组件，也不把复杂设置退化为 JSON 文本框（SPEC-DM-011 §3.3、ARCH-DM-006 §7）。
import {computed, nextTick, onMounted, ref, watch} from "vue";
import type {Component} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";
import {useConfirm} from "../../composables/useConfirm";
import {useExtensionSettings, isRevisionConflict} from "../../composables/useExtensionSettings";
import GeneratedExtensionSettingsForm from "./GeneratedExtensionSettingsForm.vue";
import SheetCatalogSettingsPanel from "./SheetCatalogSettingsPanel.vue";

// custom 专属组件的契约：与 generated 表单消费同一份 per-extension 状态
//（快照/编辑缓冲/脏标记/保存都在宿主，面板只做复杂交互）。
export interface CustomExtensionSettingsPanelProps {
  extensionId: string;
  state: ReturnType<typeof useExtensionSettings>;
}

// 编译期白名单：route_key → 专属组件。静态 import、静态键——组件解析是编译期事实，
// 绝不按服务端字符串动态 import 或按名字查组件。登记 sheet-catalog-settings 后，生产
// 图纸目录卡片（唯一声明 custom 的扩展）进入真实面板；白名单外/空 route_key 仍 fail-closed。
const CUSTOM_SETTINGS_PANELS: Record<string, Component<CustomExtensionSettingsPanelProps>> = {
  "sheet-catalog-settings": SheetCatalogSettingsPanel,
};

const props = defineProps<{extension: ExtensionSummary}>();
const emit = defineEmits<{back: []}>();
const {t} = useI18n();
const {state: confirmState, confirmAction, resolve: resolveConfirm} = useConfirm();

const settings = useExtensionSettings(props.extension.extension_id);
const {
  snapshot, items, loading, loadFailed, saving, saved, edits, fieldErrors,
  conflict, saveFailed, readOnly, readOnlyCode, dirty, load, setField, save, discardLocalEdits,
} = settings;

const hostEl = ref<HTMLElement | null>(null);
// 409 不是一种冲突：只有 expected_revision 漂移才配得上「按新修订重试 / 放弃本地修改」
// 两条出路（协议层按码判别，见 REVISION_CONFLICT_CODES）。Provider 级 409（名称重复等）
// 在这里没有出路可给，重试只会重发同一个已是最新的 expected_revision，故按普通保存失败呈现。
const revisionConflict = computed(() => isRevisionConflict(conflict.value));
// 冲突诊断行回显的三个稳定值：横幅只在判别为修订冲突时渲染，此处按同一事实取值
//（不用 v-if="conflict" 收窄：判别与 ref 是两个对象，模板窄化不再成立）
const revisionConflictInfo = computed(() => ({
  code: conflict.value?.code ?? "",
  expectedRevision: conflict.value?.expectedRevision ?? 0,
  currentRevision: conflict.value?.currentRevision ?? 0,
}));
// 普通保存失败的唯一文案来源：网络/5xx/未知（saveFailed）与 Provider 级 409（服务端正文）。
// 优先取 saveFailed：conflict 只在保存成功/放弃本地修改/只读收口时清除，因此
// 「Provider 级 409 之后再发一次非 409 失败」的新正文不能被陈旧的冲突正文压掉。
const failureNotice = computed(() => {
  if (revisionConflict.value) return "";
  if (saveFailed.value !== "") return saveFailed.value;
  return conflict.value?.message ?? "";
});
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
// fail-closed 诊断的两种原因分开措辞：白名单外有键值可回显，未登记 route_key 没有——
// 把空值塞进「route_key {route_key}」模板会印出一句带空白值的假原因
const unavailableText = computed(() => customRouteKey.value === ""
  ? t("settings.extensionSettings.customUnavailableMissingRouteKey")
  : t("settings.extensionSettings.customUnavailable", {route_key: customRouteKey.value}));
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

// 加载失败后的重试：与进入时同一落点语义（§3.3）。重试按钮随失败态被移除，
// 不重新定焦会让焦点退回 <body>——首次加载与重试成功必须落在同一个位置。
async function retryLoad(): Promise<void> {
  await load();
  await nextTick();
  focusEntry();
}

// 返回扩展列表：脏状态先确认（留在此处不丢弃输入）。
// 闸门用原生 <dialog showModal>（SPEC-DM-011 §3.3 的 SC-17 条：Esc 只作用于最上层模态）。
// 内联遮罩做不到这一点：它的 Esc 与外层设置对话框的关闭请求来自同一次按键，结果是
// 「关确认框」被当成「再次请求返回」重新打开确认框，或直接让设置对话框被原生关闭
// （子视图未提交的输入随之消失）。原生模态自带 top layer 与 Esc 归属：Esc 只关闸门，
// 关闭后焦点由平台归还给打开闸门的控件（不丢回 <body>）。
const confirmEl = ref<HTMLDialogElement | null>(null);
watch(() => confirmState.open, async open => {
  if (!open) {
    // 先 close() 再随 v-if 移除：原生模态在 close() 时把焦点归还给触发它的控件，
    // 直接移除节点只会把焦点丢回 <body>（返回闸门的「留在此处」靠这一点）
    confirmEl.value?.close();
    return;
  }
  await nextTick();
  confirmEl.value?.showModal();
  confirmEl.value?.querySelector<HTMLElement>("button")?.focus();
});
// Esc 已由原生模态接管（@cancel.prevent 映射为「留在此处」），此处只保留 Tab 焦点困绕
function onConfirmKeydown(event: KeyboardEvent): void {
  if (event.key !== "Tab" || confirmEl.value === null) return;
  const items = Array.from(confirmEl.value.querySelectorAll<HTMLElement>("button")).filter(el => !el.hasAttribute("disabled"));
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

async function back(): Promise<void> {
  if (confirmState.open) return; // 闸门自身打开时，Esc 与触发都归最上层闸门处理
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
    <div v-else-if="loadFailed && snapshot === null" class="cfg-notice error" data-testid="extension-settings-load-failed">
      <p class="cfg-notice-text" role="alert">{{ t("settings.extensionSettings.loadFailed") }}</p>
      <button type="button" @click="retryLoad">{{ t("settings.retry") }}</button>
    </div>
    <template v-else-if="snapshot">
      <!-- 快照已存在时的刷新失败：在 .cfg 级别就地提示，只读、冲突与普通编辑态共用同一条。
           冲突横幅会叫用户「按新修订重试」，而刷新失败时头部修订/Schema 徽标是陈旧的，
           这一条是用户唯一能知道「下方数据可能已过期」的地方 -->
      <p v-if="loadFailed" class="cfg-notice error" role="alert" data-testid="extension-settings-refresh-failed">
        {{ t("settings.extensionSettings.refreshFailed") }}
      </p>
      <!-- 只读保护（EXTENSION_SETTINGS_SCHEMA_NEWER）：子视图内所有控件都禁用，
           焦点必须落在这条诊断上（tabindex=-1），不得退回 body -->
      <div v-if="readOnly" class="cfg-notice readonly" role="note" tabindex="-1" data-entry-focus data-testid="extension-settings-readonly">
        <p class="cfg-notice-text">{{ t("errors.extension.schemaNewer") }}</p>
        <p class="cfg-hint">{{ t("settings.extensions.diagnosticCode", {code: readOnlyCode}) }}</p>
      </div>
      <!-- 修订冲突（服务端 409 且码属修订冲突集合）：本地编辑保留，提供「按新修订重试 / 放弃本地修改」两条出路 -->
      <div v-if="revisionConflict" class="cfg-conflict" role="alert">
        <p class="cfg-conflict-title">{{ t("settings.extensionSettings.conflict.title") }}</p>
        <p class="cfg-conflict-text">{{ t("settings.extensionSettings.conflict.message", {name}) }}</p>
        <p class="cfg-hint">{{ t("settings.extensionSettings.conflict.diagnostic", {extension_id: extension.extension_id, code: revisionConflictInfo.code, expected_revision: revisionConflictInfo.expectedRevision, current_revision: revisionConflictInfo.currentRevision}) }}</p>
        <div class="cfg-actions">
          <button type="button" :disabled="saving" @click="saveAndFocus">{{ t("settings.extensionSettings.conflict.retry") }}</button>
          <button type="button" :disabled="saving" @click="discardLocalEdits">{{ t("settings.extensionSettings.conflict.discard") }}</button>
        </div>
      </div>
      <!-- 非字段级保存失败（网络/5xx/未知，以及 Provider 级 409）：就地横幅，输入不替换。
           Provider 级 409 的正文取服务端响应（conflict.message），不重新措辞、不谎报「已被
           其他保存更新」——那个说法只在修订冲突横幅里成立 -->
      <p v-if="failureNotice" class="cfg-notice error" role="alert" data-testid="extension-settings-save-failed">{{ failureNotice }}</p>
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
      <!-- 未命中编译期白名单：稳定诊断 + 确定焦点落点（本分支必须保持可达且被覆盖） -->
      <div v-else class="cfg-notice" role="note" tabindex="-1" data-entry-focus data-testid="extension-settings-unavailable">
        <p class="cfg-notice-text">{{ unavailableText }}</p>
      </div>
    </template>
    <!-- 返回闸门：原生模态（见 onConfirmKeydown 上方的注释）。v-if 保证关闭时不在 DOM：
         常驻会让 [role="dialog"] 的计数断言同时命中隐藏闸门 -->
    <dialog
      v-if="confirmState.open" ref="confirmEl" class="gate-dialog"
      :aria-label="confirmState.title" @cancel.prevent="resolveConfirm(false)" @keydown="onConfirmKeydown"
    >
      <div class="modal-card" tabindex="-1">
        <h2>{{ confirmState.title }}</h2>
        <p class="modal-message">{{ confirmState.message }}</p>
        <div class="modal-actions">
          <button type="button" @click="resolveConfirm(false)">{{ confirmState.cancelText }}</button>
          <button type="button" @click="resolveConfirm(true)">{{ confirmState.confirmText }}</button>
        </div>
      </div>
    </dialog>
  </section>
</template>
<style scoped>
.cfg{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.cfg-head{border-bottom:1px solid var(--color-border-subtle);padding-bottom:var(--space-2)}
.cfg-title{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;margin-bottom:var(--space-1)}
.cfg-title h3{margin:0;font-size:var(--font-label)}
.badge{font-size:var(--font-caption);padding:2px 10px;border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary)}
.badge.warn{background:var(--color-warning-bg);color:var(--color-warning)}
.cfg-hint{margin:0;font-size:var(--font-caption);color:var(--color-text-secondary);line-height:1.8}
.cfg-notice{border:1px solid var(--color-border-subtle);background:var(--color-bg-muted);color:var(--color-text-secondary);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3)}
.cfg-notice.error{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.cfg-notice.readonly{border-color:var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger)}
.cfg-notice-text{margin:0 0 var(--space-2);font-size:var(--font-caption);line-height:1.8}
.cfg-conflict{border:1px solid var(--color-warning);background:var(--color-warning-bg);color:var(--color-warning);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3)}
.cfg-conflict-title{margin:0;font-size:var(--font-label);font-weight:600}
.cfg-conflict-text{margin:0;font-size:var(--font-caption);line-height:1.8}
.cfg-actions{display:flex;gap:var(--space-2);margin-top:var(--space-2);flex-wrap:wrap}
.cfg-actions button{padding:6px var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:var(--font-label)}
.cfg-actions button:disabled{cursor:not-allowed;opacity:.5}
.cfg-summary{border:1px solid var(--color-danger);background:var(--color-danger-bg);color:var(--color-danger);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3);font-size:var(--font-caption);line-height:1.8}
.cfg-summary-title{margin:0;font-weight:600}
.cfg-summary ul{margin:0;padding:0;list-style:none}
.cfg-link{border:0;background:transparent;color:var(--color-danger);cursor:pointer;padding:0;font-size:var(--font-caption);line-height:1.8;text-align:left;text-decoration:underline}
.cfg-notice button{margin-top:var(--space-1);padding:6px var(--space-3);border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-surface);color:var(--color-text-primary);cursor:pointer;font-size:var(--font-label)}
</style>
