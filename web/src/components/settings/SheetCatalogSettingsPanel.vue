<!-- 图纸目录 custom 设置面板（PLAN-DM-025 Task 8 / SPEC-DM-011 SC-17、SPEC-DM-012 §6.2/§6.4）。
     它是编译期白名单 CUSTOM_SETTINGS_PANELS 里 "sheet-catalog-settings" 指向的专属组件，
     在设置中心同一 <dialog> 的子视图内呈现：模板集合、字段映射与表达式属复杂设置，
     不降级为 JSON 文本框。

     与业务页共享同一状态模型但不共享可变实例：这里用宿主注入的 per-extension 设置状态
     （快照/编辑缓冲/保存/冲突/只读）构造目录设置控制器，因此页脚「保存」提交的就是
     模板集合 + 输出图纸过滤的完整设置快照（SPEC-DM-012 §6.4）。

     没有工作区快照：不渲染字段浏览器、不伪造预览与兼容性诊断（ColumnEditor 不传校验
     反馈即隐藏徽标与摘要），但表达式文本仍可编辑，光标协议也保持可用（不降级为 no-op）。 -->
<script setup lang="ts">
import {computed, nextTick, onMounted, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSettingsState} from "../../composables/useExtensionSettings";
import {useSheetCatalogSettings} from "../../composables/useSheetCatalogSettings";
import {useConfirm} from "../../composables/useConfirm";
import TemplateBar from "../sheet-catalog/TemplateBar.vue";
import ColumnEditor from "../sheet-catalog/ColumnEditor.vue";

const props = defineProps<{extensionId: string; state: ExtensionSettingsState}>();
const {t} = useI18n();
const {state: confirmState, confirmAction, resolve: resolveConfirm} = useConfirm();

// 无三选一闸门：设置中心子视图的唯一出路是可见「返回扩展列表」，其脏状态闸门由宿主
// （ExtensionSettingsHost）承担，且宿主的 dirty 与本面板同源（我们与协议层编辑缓冲同步）。
const catalog = useSheetCatalogSettings(props.state);
const readOnly = ref(false);
watch(() => props.state.readOnly.value, value => { readOnly.value = value; }, {immediate: true});

// 输出过滤字段级 dirty 提示（PLAN-DM-034 Task 5）：直接复用控制器已导出的 filterDirty
//（控制器对「服务端规范化数组重建的文本」比较，不在这里重新比较快照），与 hint/error
// 一起经稳定 ID 关联到输入的 aria-describedby。
const filterDescribedBy = computed(() => {
  const ids = ["catalog-settings-filter-hint"];
  if (catalog.filterDirty.value) ids.push("catalog-settings-filter-dirty");
  if (catalog.filterError.value !== "") ids.push("catalog-settings-filter-error");
  return ids.join(" ");
});

onMounted(() => {
  // 宿主已完成 GET（子视图只在快照存在时渲染）：以服务端值初始化编辑缓冲。
  // 进入焦点由宿主统一负责（子视图首个可用控件），本面板不重复定焦。
  catalog.refresh();
});

// 宿主页脚「保存」直接走协议层（与 TEMPLATEBAR 的保存同一协议层）：保存成功后必须用
// 服务端规范化值重建缓冲，否则过滤词会一直显示用户输入的原始文本（SPEC §6.4：PUT 提交
// 原始文本、回显以服务端数组为准）。失败与冲突路径上编辑缓冲仍脏，绝不重建（保留草稿）。
watch(() => [props.state.snapshot.value?.revision, props.state.dirty.value] as const, () => {
  if (props.state.dirty.value || props.state.conflict.value !== null || props.state.snapshot.value === null) return;
  catalog.refresh();
});

// 删除用户模板：先确认（与页面同一文案），确认后由控制器提交删除（URL/UUID 语义不变）。
// 闸门用原生 <dialog showModal>（SPEC-DM-011 §3.3：Esc 只作用于最上层模态）。
const confirmEl = ref<HTMLDialogElement | null>(null);
watch(() => confirmState.open, async open => {
  if (!open) {
    confirmEl.value?.close();
    return;
  }
  await nextTick();
  confirmEl.value?.showModal();
  confirmEl.value?.querySelector<HTMLElement>("button")?.focus();
});
function onConfirmKeydown(event: KeyboardEvent): void {
  if (event.key !== "Tab" || confirmEl.value === null) return;
  const items = Array.from(confirmEl.value.querySelectorAll<HTMLElement>("button")).filter(element => !element.hasAttribute("disabled"));
  if (items.length === 0) return;
  const first = items[0]!;
  const last = items[items.length - 1]!;
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

async function confirmRemove(): Promise<void> {
  const name = catalog.templates.value.find(template => template.templateId === catalog.selectedId.value)?.name ?? "";
  const confirmed = await confirmAction({
    title: t("extensions.sheetCatalog.removeConfirmTitle"),
    message: t("extensions.sheetCatalog.removeConfirmMessage", {name}),
    // 取消文案取 ConfirmModal 的同一缺省键：本闸门是原生模态，没有组件的兜底渲染
    cancelText: t("shell.modal.cancel"),
    confirmText: t("extensions.sheetCatalog.removeConfirmConfirm"),
    danger: true,
  });
  if (!confirmed) return;
  await catalog.removeTemplate();
}
</script>
<template>
  <!-- readOnly 时 <fieldset disabled> 禁用全部后代控件（含按钮与表达式输入框）：
       只读态没有可用控件，宿主把焦点定在只读诊断条上 -->
  <fieldset
    class="catalog-settings" :disabled="readOnly"
    :aria-label="$t('extensions.sheetCatalog.settingsPanelLabel')" data-testid="sheet-catalog-settings-panel"
  >
    <section class="cs-group" aria-labelledby="catalog-settings-template-title">
      <h4 id="catalog-settings-template-title">{{ $t("extensions.sheetCatalog.settingsGroupTemplate") }}</h4>
      <TemplateBar :catalog="catalog" hide-conflict @confirm-remove="confirmRemove" />
      <ColumnEditor :catalog="catalog" />
    </section>

    <section class="cs-group" aria-labelledby="catalog-settings-output-title">
      <h4 id="catalog-settings-output-title">{{ $t("extensions.sheetCatalog.settingsGroupOutput") }}</h4>
      <div
        class="cs-field" data-testid="catalog-settings-filter-field"
        :class="{'is-dirty': catalog.filterDirty.value, 'is-error': catalog.filterError.value !== ''}"
      >
        <label for="catalog-settings-filter">{{ $t("extensions.sheetCatalog.settingsFilterLabel") }}</label>
        <!-- 单行文本框：GET 的服务端数组以 ", " 连接回显，PUT 提交原始文本由 Provider 规范化
             （服务端最终校验语法、结构与关键词数量/长度，前端不截断也不预判） -->
        <input
          id="catalog-settings-filter" data-testid="catalog-settings-filter"
          type="text" :value="catalog.filterText.value"
          :placeholder="$t('extensions.sheetCatalog.settingsFilterPlaceholder')"
          :aria-describedby="filterDescribedBy"
          :aria-invalid="catalog.filterError.value !== '' ? 'true' : 'false'"
          @input="catalog.setFilterText(($event.target as HTMLInputElement).value)"
        >
        <p id="catalog-settings-filter-hint" class="cs-hint">{{ $t("extensions.sheetCatalog.settingsFilterHint") }}</p>
        <!-- 字段级 dirty 可见文字（PLAN-DM-034 Task 5）：role="status" 温和播报，
             与字段级 422 错误（下方的 role="alert"）是两种层级——错误存在时红色优先 -->
        <p
          v-if="catalog.filterDirty.value" id="catalog-settings-filter-dirty" class="cs-dirty"
          role="status" data-testid="catalog-settings-filter-dirty"
        >{{ $t("extensions.sheetCatalog.dirtyBadge") }}</p>
        <p v-if="catalog.filterError.value" id="catalog-settings-filter-error" class="cs-error" role="alert" data-testid="catalog-settings-filter-error">{{ catalog.filterError.value }}</p>
      </div>
    </section>

    <!-- 删除确认闸门（原生模态，见 confirmRemove 上方注释） -->
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
  </fieldset>
</template>
<style scoped>
/* fieldset 默认边框/内边距复位：本面板在 .cfg 内是普通区块，不引入新的视觉语言 */
.catalog-settings{display:flex;flex-direction:column;gap:var(--space-3);border:0;margin:0;padding:0;min-width:0}
.cs-group{display:flex;flex-direction:column;gap:var(--space-2);min-width:0}
.cs-group h4{margin:0;font-size:var(--font-label);color:var(--color-text-secondary)}
.cs-field{display:grid;gap:5px;min-width:0}
.cs-field label{font-size:var(--font-label);color:var(--color-text-secondary)}
.cs-field input{padding:8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);font:inherit;font-size:var(--font-label);background:var(--color-bg-surface);color:var(--color-text-primary)}
/* dirty 琥珀在 error 红色之前声明：字段级 422 错误存在时红色覆盖琥珀（错误优先） */
.cs-field.is-dirty input{border-color:var(--color-warning)}
.cs-field.is-error input{border-color:var(--color-danger)}
.cs-hint{margin:0;font-size:var(--font-caption);color:var(--color-text-secondary);line-height:1.8}
.cs-dirty{margin:0;font-size:var(--font-caption);line-height:1.8;color:var(--color-warning)}
.cs-error{margin:0;font-size:var(--font-caption);line-height:1.8;color:var(--color-danger)}
</style>
