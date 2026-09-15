// 图纸目录页（PLAN-DM-020 Task 11 / SPEC-DM-012 §7）。
// 页面只做装配：业务状态全部由 useSheetCatalog 持有，模板栏/字段浏览器/输出列
// 编辑器/兼容性摘要/预览表/操作区六组件经控制器交互。既有页面状态容器（Task 10）
// 保留：名称/描述经清单 name_key/description_key 由宿主 i18n 渲染，生命周期状态
// 按九值登记键呈现。启停入口唯一在设置中心（SPEC-DM-011 扩展分区）：本页原先自带
// 「停用扩展」按钮，而停用会移除本页入口，开关因此变成单向、用户被永久卡死
//（extension_states.enabled 持久化为 false，重启对账仍会重新停掉），故该按钮已移除。
// 本页仍保留未保存草稿三选一守卫（切换模板/切换页签/关闭工作区）。
<script setup lang="ts">
import {computed, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary, Workspace} from "../api/contracts";
import {useSheetCatalog} from "../composables/useSheetCatalog";
import {useConfirm} from "../composables/useConfirm";
import {useToast} from "../composables/useToast";
import TemplateBar from "../components/sheet-catalog/TemplateBar.vue";
import FieldBrowser from "../components/sheet-catalog/FieldBrowser.vue";
import ColumnEditor from "../components/sheet-catalog/ColumnEditor.vue";
import CatalogPreview from "../components/sheet-catalog/CatalogPreview.vue";
import ConfirmModal from "../components/ui/ConfirmModal.vue";
import ToastHost from "../components/ui/ToastHost.vue";

const props = defineProps<{extension: ExtensionSummary; workspace: Workspace | null}>();
const {t} = useI18n();
const workspaceRef = computed(() => props.workspace);
const catalog = useSheetCatalog(workspaceRef);
void catalog.initialize();
const {state: confirmState, confirmAction, resolve: resolveConfirm} = useConfirm();
const {toasts, pushToast, dismiss} = useToast();

const statusKey = computed(() => `extensions.status.${props.extension.status}`);
const removeTargetName = computed(() => catalog.templates.value.find(template => template.templateId === catalog.selectedId.value)?.name ?? "");

async function confirmRemove() {
  const ok = await confirmAction({
    title: t("extensions.sheetCatalog.removeConfirmTitle"),
    message: t("extensions.sheetCatalog.removeConfirmMessage", {name: removeTargetName.value}),
    confirmText: t("extensions.sheetCatalog.removeConfirmConfirm"),
    danger: true,
  });
  if (!ok) return;
  if (await catalog.removeTemplate()) pushToast({type: "ok", title: t("extensions.sheetCatalog.toastDeleted"), body: removeTargetName.value});
}
function onSaved() {
  pushToast({type: "ok", title: t("extensions.sheetCatalog.toastSaved"), body: catalog.draft.value.name});
}

// 三选一守卫模态焦点（SPEC §13：Esc、焦点圈闭与归还）。打开时焦点移入模态卡片、
// 关闭归还触发元素；Tab 在模态内可聚焦元素间圈闭（禁用的"保存为模板"不参与）。
// SPEC-DM-011 修订「启停交互改进」：模态由页面内联遮罩改为原生 <dialog showModal>（与宿主未提交
// 输入闸门同一原语）——设置中心在 top layer 打开时，内联遮罩会被其 inert 吞掉：
// 用户看得见弹框却点不动。原生模态自带 top layer 与 ::backdrop，Esc 也只作用于
// 最上层对话框（不会顺带触发下层设置窗口的关闭）。模态元素常驻 DOM（关闭即
// display:none），不写 role/aria-modal：原生模态已自带 dialog 角色与模态语义，
// 显式属性会让 e2e 通用的 [role="dialog"][aria-modal="true"] 选择器误命中隐藏闸门。
const guardCard = ref<HTMLElement | null>(null);
const guardDialogEl = ref<HTMLDialogElement | null>(null);
let guardOpener: HTMLElement | null = null;
watch(() => catalog.guardState.value.open, open => {
  const dialog = guardDialogEl.value;
  if (open) {
    if (dialog === null || dialog.open) return;
    guardOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    guardCard.value?.focus();
  } else {
    if (dialog?.open) dialog.close();
    if (!confirmState.open) {
      guardOpener?.focus?.();
      guardOpener = null;
    }
  }
});
function onGuardKeydown(event: KeyboardEvent) {
  // Esc 归原生模态的 cancel 处理（见模板 @cancel）
  if (event.key !== "Tab" || !guardCard.value) return;
  const items = Array.from(guardCard.value.querySelectorAll<HTMLElement>("button")).filter(element => !element.hasAttribute("disabled"));
  if (items.length === 0) return;
  const first = items[0]!;
  const last = items[items.length - 1]!;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
</script>
<template>
  <section class="sheet-catalog" :aria-label="$t(extension.name_key)">
    <header class="catalog-head">
      <h2>{{ $t(extension.name_key) }}</h2>
      <p class="catalog-desc">{{ $t(extension.description_key) }}</p>
      <p class="catalog-meta">v{{ extension.version }} · {{ $t(statusKey) }}</p>
      <span class="spacer"></span>
      <!-- 启停入口唯一在设置中心（见文件头注释）：指引保留为紧凑可见正文，不再占整行状态卡 -->
      <p class="catalog-manage-hint">{{ $t("extensions.page.manageHint") }}</p>
    </header>
    <!-- 只读保护（EXTENSION_SETTINGS_SCHEMA_NEWER）：服务端已存更高 Schema，本次
         设置写不进去。文案与诊断码沿用设置中心（ExtensionSettingsHost）同一键，
         不另造一套说法；没有这条通知时业务页的保存入口只会静默失败（I5）。 -->
    <p v-if="catalog.readOnly.value" class="readonly-notice" role="note" data-testid="sheet-catalog-readonly">
      <span>{{ t("errors.extension.schemaNewer") }}</span>
      <span class="readonly-code">{{ t("settings.extensions.diagnosticCode", {code: catalog.readOnlyCode.value}) }}</span>
    </p>
    <p v-if="catalog.loading.value" class="loading" role="status">{{ $t("extensions.sheetCatalog.loading") }}</p>
    <p v-else-if="catalog.loadError.value" class="error notice" role="alert">{{ catalog.loadError.value }}</p>
    <div v-else class="catalog-grid">
      <TemplateBar :catalog="catalog" @saved="onSaved" @confirm-remove="confirmRemove" />
      <div class="catalog-row">
        <FieldBrowser :catalog="catalog" />
        <!-- 业务页传入真实校验反馈：兼容性徽标与摘要显示（设置中心 custom 面板不传） -->
        <ColumnEditor :catalog="catalog" :feedback="catalog.feedback" />
      </div>
      <CatalogPreview :catalog="catalog" />
    </div>

    <!-- 三选一保护（SPEC §3.2）：切换模板/切换页签/停用扩展/关闭工作区统一闸门；
         未命名草稿不提供"保存为模板"（需先命名另存为），只能放弃或留在此处。
         原生模态：停用扩展时设置对话框正在 top layer，本闸门必须自行进入 top layer
         才能叠在其上并被点击（SPEC-DM-011 修订「启停交互改进」）。 -->
    <dialog
      ref="guardDialogEl" class="gate-dialog"
      :aria-label="$t('extensions.sheetCatalog.guardTitle')"
      @cancel.prevent="catalog.resolveGuard('stay')" @keydown="onGuardKeydown"
    >
      <div ref="guardCard" class="modal-card" tabindex="-1">
        <h2>{{ $t("extensions.sheetCatalog.guardTitle") }}</h2>
        <p class="modal-message">{{ $t("extensions.sheetCatalog.guardMessage", {summary: catalog.guardState.value.summary}) }}</p>
        <div class="modal-actions">
          <button type="button" @click="catalog.resolveGuard('stay')">{{ $t("extensions.sheetCatalog.guardStay") }}</button>
          <button type="button" @click="catalog.resolveGuard('discard')">{{ $t("extensions.sheetCatalog.guardDiscard") }}</button>
          <!-- 只读态下"保存为模板"必然失败（控制器直接返回 false，模态停在原地）：
               与 TemplateBar 同一口径停用，不留下没有反馈的按钮 -->
          <button type="button" class="primary" :disabled="!catalog.guardState.value.canSave || catalog.readOnly.value" @click="catalog.resolveGuard('save')">{{ $t("extensions.sheetCatalog.guardSave") }}</button>
        </div>
      </div>
    </dialog>
    <!-- confirmDisabled：只读态下删除必然不落盘（控制器保存门禁直接返回 false，确认后模态关闭但既无落盘也无提示，
         是一个静默出口）。当前删除入口已随只读停用，所以这里不会在正常路径上到达；
         但仍按同一口径写死门禁，避免以后新增删除入口时重新引入静默出口 -->
    <ConfirmModal v-bind="confirmState" :confirm-disabled="catalog.readOnly.value" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
    <ToastHost :toasts="toasts" @dismiss="dismiss" />
  </section>
</template>
<style scoped>
/* PLAN-DM-023 Task 4：页面占满桌面壳剩余高度，栅格与预览卡可压缩到各自 min-height，
   因此 1440×1000 首屏完整容纳“页头 + 模板栏 + 字段/输出列 + 预览与导出”；
   内容超过可用高度时由本容器自身滚动（小视口与单列布局）。 */
.sheet-catalog{display:flex;flex-direction:column;gap:var(--space-3);min-height:0;flex:1;overflow:auto}
/* PLAN-DM-023 Task 2：标题、说明、版本/生命周期与启停指引组合为单行紧凑头部 */
.catalog-head{display:flex;align-items:baseline;gap:var(--space-3);flex-wrap:wrap;min-width:0}
/* 18px 页标题借用组件层 --modal-title-font-size：语义层没有 18px 档位（收口责任 K）。
   层叠已核：全仓无全局 h2 规则，.modal-card h2 只作用于模态卡片内部，不覆盖本页标题。 */
.catalog-head h2{margin:0;font-size:var(--modal-title-font-size);color:var(--color-text-primary)}
.catalog-head .spacer{flex:1}
.catalog-desc{margin:0;color:var(--color-text-secondary);font-size:var(--font-label);min-width:0}
.catalog-meta{margin:0;color:var(--color-text-muted);font-size:var(--font-caption);white-space:nowrap}
.catalog-manage-hint{margin:0;color:var(--color-text-muted);font-size:var(--font-caption)}
.catalog-grid{display:flex;flex-direction:column;gap:var(--space-3);min-width:0;min-height:0;flex:1 1 auto}
/* 工作区栅格取冻结 Demo 的确定高度（--catalog-pane-height = 425px），不随字段条目或列数增长：
   字段列表与列区各自内部滚动，避免栅格被压缩后内容溢出叠到预览卡上。 */
.catalog-row{display:grid;grid-template-columns:258px minmax(470px,1fr);gap:var(--space-3);height:var(--catalog-pane-height);align-items:stretch;min-width:0;flex:0 0 auto}
.loading{margin:0;color:var(--color-text-muted)}
/* 高版本只读通知：中性底 + 边线，与"加载失败"的红色 notice 区分 */
.readonly-notice{display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:baseline;margin:0;padding:var(--space-2) var(--space-3);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);color:var(--color-text-secondary);font-size:var(--font-label)}
.readonly-code{color:var(--color-text-muted);font-size:var(--font-caption)}
/* PLAN-DM-023 Task 5：≤980px 降为单列（与冻结 Demo 同断点），高度由内容决定：
   字段区限高 --catalog-field-browser-max-height + 输出列卡 min-height --catalog-pane-height，
   超出时由 .sheet-catalog 滚动 */
@media (max-width: 980px){.catalog-row{grid-template-columns:1fr;height:auto}}
</style>
