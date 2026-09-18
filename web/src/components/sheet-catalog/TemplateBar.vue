<!-- 模板栏（SPEC-DM-012 §7.2 区域 1）：模板选择、保存/另存为/删除入口、保存错误
     与冲突恢复面板（SPEC §11：冲突保留本地编辑，明确提供"另存为 / 按新修订重试"，
     不只显示泛化保存失败）。删除确认模态由页面装配层提供。 -->
<script setup lang="ts">
import {nextTick, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {SheetCatalogTemplateController} from "../../composables/useSheetCatalogSettings";
import UiButton from "../ui/UiButton.vue";

// PLAN-DM-025 Task 8：本组件只依赖模板编辑接口（模板选择/草稿/保存/另存/删除），
// 不依赖预览或导出——同一份接口既服务业务页，也服务设置中心的 custom 面板。
// hideConflict：设置中心子视图的修订冲突横幅由宿主（ExtensionSettingsHost）渲染，
// 与冻结设计一致；面板内不再叠一份，避免同一冲突出现两条一模一样的出路按钮。
// 三步保存入口（保存/另存为/删除）在高版本只读（catalog.readOnly）下一律停用：
// 控制器在只读时直接返回 false，按钮若仍可点就是"点了没反应"的静默出口（I5）。
const props = defineProps<{catalog: SheetCatalogTemplateController; hideConflict?: boolean}>();
const emit = defineEmits<{saved: []; removed: []; confirmRemove: []}>();
const {t, locale} = useI18n();

// PLAN-DM-024 Task 3 / MEMO-DM-031 F4：历史数据或直接 API 注入的用户模板可能与
// 内置模板在当前语言下显示同名。只对碰撞的用户 option 追加“用户模板”后缀消歧，
// option 的 value 与所有模板操作仍按 UUID，不改持久化名称。
function templateOptionLabel(name: string): string {
  const builtin = t("extensions.sheetCatalog.builtinName").trim().toLocaleLowerCase(locale.value);
  const collides = name.trim().toLocaleLowerCase(locale.value) === builtin;
  return collides ? `${name}${t("extensions.sheetCatalog.userTemplateSuffix")}` : name;
}

const saveAsOpen = ref(false);
const saveAsName = ref("");
const card = ref<HTMLElement | null>(null);
// 模态焦点（SPEC §13：Esc、焦点圈闭与归还）：打开移入卡片、关闭归还触发按钮
let opener: HTMLElement | null = null;

async function onSave() {
  // PLAN-DM-034 Task 6（SPEC-DM-015 §5.1/§5.2）：clean 草稿没有可执行差异，任何激活途径
  // （强点击/Enter/Space/程序化 click）都在这里与 ariaDisabled 双层守卫下被挡住；
  // read-only、saving 等强阻断仍由原生 disabled 与控制器内部守卫承担。
  if (!props.catalog.dirty.value) return;
  if (await props.catalog.saveInPlace()) emit("saved");
}
function openSaveAs() {
  // 冲突面板保持可见：saveAs 依据 conflict 状态决定先刷新服务端修订再保存
  saveAsName.value = props.catalog.canSaveInPlace.value ? props.catalog.draft.value.name : "";
  saveAsOpen.value = true;
}
watch(saveAsOpen, async open => {
  if (open) {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    await nextTick();
    card.value?.focus();
  } else {
    opener?.focus?.();
    opener = null;
  }
});
function onModalKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    saveAsOpen.value = false;
    return;
  }
  if (event.key !== "Tab" || !card.value) return;
  const items = Array.from(card.value.querySelectorAll<HTMLElement>("button,input")).filter(element => !element.hasAttribute("disabled"));
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
async function confirmSaveAs() {
  if (await props.catalog.saveAs(saveAsName.value)) {
    saveAsOpen.value = false;
    emit("saved");
  }
}
</script>
<template>
  <section class="template-bar panel" :aria-label="$t('extensions.sheetCatalog.templateBarLabel')">
    <div class="template-row">
      <label class="template-select">
        <span>{{ $t("extensions.sheetCatalog.templateLabel") }}</span>
        <select :aria-label="$t('extensions.sheetCatalog.templateLabel')" :value="catalog.selectedId.value ?? ''" @change="catalog.selectTemplate(($event.target as HTMLSelectElement).value || null)">
          <option value="">{{ $t("extensions.sheetCatalog.builtinName") }}</option>
          <option v-for="template in catalog.templates.value" :key="template.templateId ?? template.name" :value="template.templateId">{{ templateOptionLabel(template.name) }}</option>
        </select>
      </label>
      <!-- PLAN-DM-023 V6：恢复“内置模板/已保存模板”身份徽标与“已保存/有未保存修改”状态文字；
           两者都是可见正文，不只靠颜色区分 -->
      <span class="template-badge" :class="catalog.canSaveInPlace.value ? 'saved' : 'builtin'">{{ catalog.canSaveInPlace.value ? $t("extensions.sheetCatalog.templateBadgeUser") : $t("extensions.sheetCatalog.templateBadgeBuiltin") }}</span>
      <!-- PLAN-DM-034 Task 6（SPEC-DM-015 §4.2/§4.3）：模板状态升级为中性/警示两种徽标。
           dirty 琥珀只落在这一枚模板级徽标（不铺到列输入框），role="status" 温和播报，
           不用频繁输入会反复打断的 alert。 -->
      <span class="template-state" :class="{dirty: catalog.dirty.value}" role="status">{{ catalog.dirty.value ? $t("extensions.sheetCatalog.dirtyBadge") : $t("extensions.sheetCatalog.templateStateSaved") }}</span>
      <span v-if="catalog.dirty.value && !catalog.canSaveInPlace.value" class="draft-name">{{ $t("extensions.sheetCatalog.unnamedDraft") }}</span>
      <span class="spacer"></span>
      <!-- clean 态是“没有可执行差异”而非不可操作：可聚焦语义禁用（aria-disabled），
           强点击/键盘激活经 onSave 首行守卫挡下；read-only 与 saving 继续原生 disabled -->
      <UiButton v-if="catalog.canSaveInPlace.value" :disabled="catalog.readOnly.value || catalog.saving.value" :aria-disabled="!catalog.dirty.value" @click="onSave">{{ catalog.saving.value ? $t("extensions.sheetCatalog.saving") : $t("extensions.sheetCatalog.save") }}</UiButton>
      <UiButton :disabled="catalog.readOnly.value" @click="openSaveAs">{{ $t("extensions.sheetCatalog.saveAs") }}</UiButton>
      <!-- 危险删除保持低强调（透明底 + 危险文字，不使用 UiButton 的实心 danger 变体），确认流程不变 -->
      <button v-if="catalog.canSaveInPlace.value" type="button" class="danger-text" :disabled="catalog.readOnly.value" @click="emit('confirmRemove')">{{ $t("extensions.sheetCatalog.remove") }}</button>
    </div>
    <!-- 同一句失败正文不渲染两次：设置中心子视图（hideConflict）由宿主横幅统一呈现，
         否则两个 role="alert" 会重复播报同一句话 -->
    <p v-if="catalog.saveError.value && !hideConflict" class="error notice" role="alert">{{ catalog.saveError.value }}</p>
    <div v-if="catalog.conflict.value && !hideConflict" class="conflict" role="alert" :aria-label="$t('extensions.sheetCatalog.conflictTitle')">
      <h3>{{ $t("extensions.sheetCatalog.conflictTitle") }}</h3>
      <p>{{ $t("extensions.sheetCatalog.conflictMessage") }}</p>
      <div class="template-row">
        <UiButton @click="openSaveAs">{{ $t("extensions.sheetCatalog.conflictSaveAs") }}</UiButton>
        <UiButton :disabled="catalog.saving.value" @click="catalog.retryAfterConflict()">{{ $t("extensions.sheetCatalog.conflictRetry") }}</UiButton>
      </div>
    </div>
    <div v-if="saveAsOpen" class="modal-mask" @keydown="onModalKeydown">
      <div class="modal-card" role="dialog" aria-modal="true" :aria-label="$t('extensions.sheetCatalog.saveAsTitle')" tabindex="-1" ref="card">
        <h2>{{ $t("extensions.sheetCatalog.saveAsTitle") }}</h2>
        <label class="save-as-name">
          <span>{{ $t("extensions.sheetCatalog.saveAsNameLabel") }}</span>
          <input v-model="saveAsName" type="text" :aria-label="$t('extensions.sheetCatalog.saveAsNameLabel')" @keydown.enter="confirmSaveAs">
        </label>
        <div class="modal-actions">
          <button type="button" @click="saveAsOpen=false">{{ $t("extensions.sheetCatalog.cancel") }}</button>
          <button type="button" class="primary" :disabled="catalog.saving.value || saveAsName.trim() === '' || catalog.readOnly.value" @click="confirmSaveAs">{{ $t("extensions.sheetCatalog.saveAsConfirm") }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.template-bar{display:flex;flex-direction:column;gap:var(--space-2)}
.template-bar.panel{padding:var(--space-2) var(--space-3)}
.template-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap;min-width:0}
/* 标签与选择框同排，窄屏时整行换行（PLAN-DM-023 Task 2：模板选择与三项管理操作单行优先）。
   选择框保留原生 <select>：UiSelect 的可见 label 在控件上方，会把这行从单行压成两行（冻结布局）。 */
.template-select{display:flex;align-items:center;gap:var(--space-2);font-size:var(--font-label);color:var(--color-text-secondary);min-width:0}
.template-select select{min-width:var(--catalog-template-select-min-width);padding:6px 8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md)}
.template-badge{font-size:var(--font-caption);padding:3px 9px;border-radius:var(--radius-full);white-space:nowrap}
.template-badge.builtin{color:var(--color-accent);background:var(--color-info-bg)}
.template-badge.saved{color:var(--color-success);background:var(--color-success-bg)}
/* PLAN-DM-034 Task 6（SPEC-DM-015 §4.2）：模板状态从 muted 正文升级为中性/警示两种徽标；
   dirty 前景/底色固定琥珀语义令牌，警示不只靠颜色（可见文字随状态切换） */
.template-state{font-size:var(--font-caption);padding:3px 9px;border-radius:var(--radius-full);background:var(--color-bg-muted);color:var(--color-text-secondary);white-space:nowrap}
.template-state.dirty{background:var(--color-warning-bg);color:var(--color-warning)}
.draft-name{color:var(--color-text-muted);font-size:var(--font-caption)}
.spacer{flex:1}
/* 危险删除保持低强调：透明底 + 危险文字（属性页 .danger-text 同一写法）；
   盒模型只用组件层令牌，不用 UiButton 的实心 danger 变体 */
.template-row .danger-text{min-height:var(--button-height);padding:0 var(--space-3);border:1px solid transparent;border-radius:var(--radius-md);background:transparent;color:var(--color-danger)}
.template-row .danger-text:hover:not(:disabled){background:var(--color-danger-bg)}
.conflict{border:1px solid var(--color-warning);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);background:var(--color-warning-bg)}
/* 14px 卡/区块标题：消费语义档位 --font-card-title（责任 K 已闭合，见 tokens.css 头注释） */
.conflict h3{margin:0 0 var(--space-2);font-size:var(--font-card-title)}
.conflict p{margin:0 0 var(--space-3);color:var(--color-text-primary);font-size:var(--button-font-size)}
.save-as-name{display:grid;gap:5px;color:var(--color-text-secondary);font-size:var(--font-label)}
.save-as-name input{padding:8px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm)}
</style>
