// 图纸目录页（PLAN-DM-020 Task 11 / SPEC-DM-012 §7）。
// 页面只做装配：业务状态全部由 useSheetCatalog 持有，模板栏/字段浏览器/输出列
// 编辑器/兼容性摘要/预览表/操作区六组件经控制器交互。既有页面状态容器（Task 10）
// 保留：名称/描述经清单 name_key/description_key 由宿主 i18n 渲染，生命周期状态
// 按九值登记键呈现；「停用扩展」经 App 的全局未提交输入闸门（含本页草稿三选一）。
<script setup lang="ts">
import {computed} from "vue";
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
defineEmits<{toggleEnabled: [extensionId: string, enabled: boolean]}>();
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
</script>
<template>
  <section class="sheet-catalog" :aria-label="$t(extension.name_key)">
    <header class="catalog-head">
      <h2>{{ $t(extension.name_key) }}</h2>
      <p class="catalog-desc">{{ $t(extension.description_key) }}</p>
      <p class="catalog-meta">v{{ extension.version }} · {{ $t(statusKey) }}</p>
    </header>
    <div class="catalog-status" role="status">
      <p>{{ $t("extensions.page.ready") }}</p>
      <button type="button" @click="$emit('toggleEnabled', extension.extension_id, false)">{{ $t("extensions.page.disable") }}</button>
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
         未命名草稿不提供"保存为模板"（需先命名另存为），只能放弃或留在此处 -->
    <div v-if="catalog.guardState.value.open" class="modal-mask" @keydown.escape.prevent="catalog.resolveGuard('stay')">
      <div class="modal-card" role="dialog" aria-modal="true" :aria-label="$t('extensions.sheetCatalog.guardTitle')" tabindex="-1">
        <h2>{{ $t("extensions.sheetCatalog.guardTitle") }}</h2>
        <p class="modal-message">{{ $t("extensions.sheetCatalog.guardMessage", {summary: catalog.guardState.value.summary}) }}</p>
        <div class="modal-actions">
          <button type="button" @click="catalog.resolveGuard('stay')">{{ $t("extensions.sheetCatalog.guardStay") }}</button>
          <button type="button" @click="catalog.resolveGuard('discard')">{{ $t("extensions.sheetCatalog.guardDiscard") }}</button>
          <button type="button" class="primary" :disabled="!catalog.guardState.value.canSave" @click="catalog.resolveGuard('save')">{{ $t("extensions.sheetCatalog.guardSave") }}</button>
        </div>
      </div>
    </div>
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
.catalog-status{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.catalog-status p{margin:0;color:var(--color-text-secondary);font-size:14px}
.catalog-grid{display:flex;flex-direction:column;gap:var(--space-4);min-width:0}
.catalog-row{display:grid;grid-template-columns:280px minmax(0,1fr);gap:var(--space-4);align-items:start}
.loading{margin:0;color:var(--color-text-muted)}
@media (max-width: 960px){.catalog-row{grid-template-columns:1fr}}
</style>
