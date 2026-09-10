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
import CompatibilitySummary from "../components/sheet-catalog/CompatibilitySummary.vue";
import CatalogPreview from "../components/sheet-catalog/CatalogPreview.vue";
import CatalogActions from "../components/sheet-catalog/CatalogActions.vue";
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
// PLAN-DM-022 修订：模态由页面内联遮罩改为原生 <dialog showModal>（与宿主未提交
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
    </header>
    <div class="catalog-status">
      <p>{{ $t("extensions.page.ready") }}</p>
      <p class="catalog-manage-hint">{{ $t("extensions.page.manageHint") }}</p>
    </div>
    <p v-if="catalog.loading.value" class="loading" role="status">{{ $t("extensions.sheetCatalog.loading") }}</p>
    <p v-else-if="catalog.loadError.value" class="error notice" role="alert">{{ catalog.loadError.value }}</p>
    <div v-else class="catalog-grid">
      <TemplateBar :catalog="catalog" @saved="onSaved" @confirm-remove="confirmRemove" />
      <div class="catalog-row">
        <FieldBrowser :catalog="catalog" />
        <ColumnEditor :catalog="catalog" />
      </div>
      <CompatibilitySummary :catalog="catalog" />
      <CatalogPreview :catalog="catalog" />
      <CatalogActions :catalog="catalog" />
    </div>

    <!-- 三选一保护（SPEC §3.2）：切换模板/切换页签/停用扩展/关闭工作区统一闸门；
         未命名草稿不提供"保存为模板"（需先命名另存为），只能放弃或留在此处。
         原生模态：停用扩展时设置对话框正在 top layer，本闸门必须自行进入 top layer
         才能叠在其上并被点击（PLAN-DM-022 修订）。 -->
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
          <button type="button" class="primary" :disabled="!catalog.guardState.value.canSave" @click="catalog.resolveGuard('save')">{{ $t("extensions.sheetCatalog.guardSave") }}</button>
        </div>
      </div>
    </dialog>
    <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
    <ToastHost :toasts="toasts" @dismiss="dismiss" />
  </section>
</template>
<style scoped>
.sheet-catalog{display:flex;flex-direction:column;gap:var(--space-4);min-height:0}
.catalog-head{display:flex;flex-direction:column;gap:var(--space-2)}
.catalog-head h2{margin:0;font-size:18px;color:var(--color-text-primary)}
.catalog-desc{margin:0;color:var(--color-text-secondary);font-size:14px}
.catalog-meta{margin:0;color:var(--color-text-muted);font-size:12px}
.catalog-status{display:flex;flex-direction:column;gap:var(--space-1);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.catalog-status p{margin:0;color:var(--color-text-secondary);font-size:14px}
.catalog-status .catalog-manage-hint{color:var(--color-text-muted);font-size:12px}
.catalog-grid{display:flex;flex-direction:column;gap:var(--space-4);min-width:0}
.catalog-row{display:grid;grid-template-columns:280px minmax(0,1fr);gap:var(--space-4);align-items:start}
.loading{margin:0;color:var(--color-text-muted)}
@media (max-width: 960px){.catalog-row{grid-template-columns:1fr}}
</style>
