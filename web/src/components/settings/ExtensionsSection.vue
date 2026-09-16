<script setup lang="ts">
// 设置中心扩展分区（本次修复：让扩展停用可逆 / ARCH-DM-006 §7、SPEC-DM-011）。
// 背景：启停控件原先只长在扩展自己的页面上，而停用会移除该页面入口，开关因此
// 变成单向——用户点一次停用就再也找不到启用入口，且状态持久化在 extension_states。
//
// SPEC-DM-011 修订「启停交互改进」：启停控件由文字按钮改为滑动开关（role="switch" + aria-checked），
// 并在开关左侧给出可见的「已启用/已停用」文字状态——开关方向不能只靠颜色与滑块
// 位置表达，否则色觉障碍用户与屏幕阅读之外的场景都读不出当前状态。
//
// 扩展卡片基线（SC-16）：卡片承载四层信息（名称版本 / 描述 / 状态徽标与诊断码 /
// 动作行），卡片不可点击、不导航，交互只有动作行；卡片本身在 ExtensionCard.vue，
// 开关原语在 BooleanSwitch.vue。
//
// PLAN-DM-025 任务 7 起本组件承载扩展编排：清单取数（进入分区即拉取，不依赖工作区）、
// 启停落库（仍经 App 装配的闸门面板，本组件绝不自行调端点）、启停失败的原地呈现与
// 开关焦点收敛（均由 SettingsDialog 下移，见 SPEC-DM-011 §6 的 SC-17 行数预算）。
// 卡片「配置」入口只上抛 open-config：扩展设置状态归 ExtensionSettingsHost，本组件不持有。
import {computed,nextTick,onMounted,ref} from "vue";
import {useI18n} from "vue-i18n";
import {ApiError} from "../../api/client";
import type {ExtensionSummary} from "../../api/contracts";
import type {ExtensionsPanel} from "../../composables/useExtensions";
import ExtensionCard from "./ExtensionCard.vue";

const props = defineProps<{panel: ExtensionsPanel}>();
const emit = defineEmits<{openConfig: [extension: ExtensionSummary]}>();
const {t,te} = useI18n();
const sectionEl = ref<HTMLElement | null>(null);
const errorText = ref(""); // 启停失败就地行内呈现（对话框外的错误行会被遮罩压住）
const busy = ref(false);

// 扩展清单是应用级状态，不依赖工作区是否已加载：打开分区即拉取，
// 因此“手头没打开 DST”的用户也能在这里恢复被停用的扩展
onMounted(() => { void props.panel.reload(); });

// 非字段级 ApiError 文案：已知错误码已由 api/client 按 message_key 渲染（error.message），
// 未知码保留后端原文作诊断——与对话框内其他错误的呈现口径一致
function apiErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return String(error);
  return error.messageKey !== undefined && te(error.messageKey) ? error.message : error.rawMessage ?? error.message;
}

async function onToggle(extensionId: string, enabled: boolean): Promise<void> {
  if (busy.value) return;
  errorText.value = "";
  // 停用移除扩展页面入口、可能丢弃页内未保存草稿，因此仍经 App 的 guardAllInputs
  // 三选一（闸门为原生模态，会叠在本对话框之上）；选“留在此处”则闸门不继续，
  // 本次 toggle 静默结束——开关保持原位，不报错。
  busy.value = true;
  try{await props.panel.toggle(extensionId,enabled)}
  catch(error){errorText.value=apiErrorText(error)}
  finally{
    busy.value=false;
    // 忙碌期开关被 disabled，焦点会落回 body；恢复可用后归还同一开关，否则键盘用户
    // 每拨一次开关就丢一次位置。停用后标签栏处于 inert，不能把焦点送回页面。
    await nextTick();
    findCard(extensionId)?.querySelector<HTMLElement>(".switch")?.focus();
  }
}

// 按行数据属性定位卡片：不把服务端返回的 extension_id 拼进选择器字符串
function findCard(extensionId:string):HTMLElement|undefined{
  return Array.from(sectionEl.value?.querySelectorAll<HTMLElement>("[data-extension-id]")??[])
    .find(card=>card.dataset.extensionId===extensionId);
}
// 返回子视图后焦点归还触发它的「配置」按钮（SC-17：返回走子视图出口，关闭走齿轮入口）
function focusConfigOpener(extensionId:string):void{
  findCard(extensionId)?.querySelector<HTMLElement>("[data-config-opener]")?.focus();
}
defineExpose({focusConfigOpener});

// 增长机制的唯一预设答案（SPEC-DM-011 §3.3）：单列 + 面板滚动；条目 ≥6 条按
// enabled 分「已启用 / 已停用」两段——分组键必须与开关同一权威，否则同一卡片
// 会在两段之间跳变。搜索/筛选/排序/分页/多列网格是明确的非目标。
const GROUP_THRESHOLD = 6;
const groups = computed(() => {
  if (props.panel.list.length < GROUP_THRESHOLD) return [{key: "", title: "", items: props.panel.list}];
  return [
    {key: "on", title: t("settings.extensions.stateOn"), items: props.panel.list.filter(item => item.enabled)},
    {key: "off", title: t("settings.extensions.stateOff"), items: props.panel.list.filter(item => !item.enabled)},
  ].filter(group => group.items.length > 0);
});
</script>
<template>
  <section ref="sectionEl" class="ext-section" :aria-label="t('settings.sections.extensions')">
    <!-- 立即生效语义：分区内的开关点击即落库，与底部"取消/保存"缓冲无关，必须写明，
         否则用户会以为取消能回滚开关 -->
    <p class="ext-notice" role="note">{{ t("settings.extensions.immediateNotice") }}</p>
    <p v-if="panel.loading" class="f-hint" role="status">{{ t("settings.extensions.loading") }}</p>
    <div v-else-if="panel.failed" class="ext-failed">
      <p class="f-hint" role="alert">{{ t("settings.extensions.loadFailed") }}</p>
      <button type="button" @click="panel.reload()">{{ t("settings.retry") }}</button>
    </div>
    <p v-else-if="panel.list.length===0" class="f-hint">{{ t("settings.extensions.empty") }}</p>
    <template v-else>
      <div v-for="group in groups" :key="group.key" class="ext-group">
        <div v-if="group.title" class="group-title">{{ group.title }}</div>
        <ul class="ext-list">
          <ExtensionCard
            v-for="extension in group.items" :key="extension.extension_id"
            :extension="extension" :busy="busy"
            @toggle="(id, value) => onToggle(id, value)" @open-config="extension => emit('openConfig', extension)"
          />
        </ul>
      </div>
    </template>
    <p v-if="errorText" class="ext-error" role="alert">{{ errorText }}</p>
  </section>
</template>
<style scoped>
.ext-section{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.ext-notice{margin:0;padding:8px 12px;border-radius:var(--radius-md);background:var(--color-info-bg);color:var(--color-text-secondary);font-size:var(--font-caption)}
.ext-failed{display:flex;flex-direction:column;align-items:flex-start;gap:var(--space-2)}
.ext-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--space-2)}
.ext-group{display:flex;flex-direction:column;gap:var(--space-2)}
.group-title{font-weight:600;font-size:var(--font-label);border-left:3px solid var(--color-accent);padding-left:var(--space-2)}
.ext-error{margin:0;color:var(--color-danger);font-size:var(--font-label)}
</style>
