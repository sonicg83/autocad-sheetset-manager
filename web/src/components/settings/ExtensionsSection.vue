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
// 开关与状态文字），卡片不可点击、不导航，唯一交互是开关；本分区只做"取数 + 列表"，
// 卡片本身在 ExtensionCard.vue，开关原语在 BooleanSwitch.vue。
//
// 纯呈现组件：列表、加载/失败/错误文案全部由 SettingsDialog 传入。启停编排
//（未保存输入三选一闸门、标签与焦点收敛）由 SettingsDialog + App 负责，本组件
// 绝不自行调用扩展端点——绕过闸门会静默丢草稿。
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";
import ExtensionCard from "./ExtensionCard.vue";

const props = defineProps<{
  list: ExtensionSummary[];
  loading: boolean;
  failed: boolean;
  errorText: string;
  busy: boolean;
}>();
defineEmits<{retry: []; toggle: [extensionId: string, enabled: boolean]}>();
const {t}=useI18n();

// 增长机制的唯一预设答案（SPEC-DM-011 §3.3）：单列 + 面板滚动；条目 ≥6 条按
// enabled 分「已启用 / 已停用」两段——分组键必须与开关同一权威，否则同一卡片
// 会在两段之间跳变。搜索/筛选/排序/分页/多列网格是明确的非目标。
const GROUP_THRESHOLD = 6;
const groups = computed(() => {
  if (props.list.length < GROUP_THRESHOLD) return [{key: "", title: "", items: props.list}];
  return [
    {key: "on", title: t("settings.extensions.stateOn"), items: props.list.filter(item => item.enabled)},
    {key: "off", title: t("settings.extensions.stateOff"), items: props.list.filter(item => !item.enabled)},
  ].filter(group => group.items.length > 0);
});
</script>
<template>
  <section class="ext-section" :aria-label="t('settings.sections.extensions')">
    <!-- 立即生效语义：分区内的开关点击即落库，与底部"取消/保存"缓冲无关，必须写明，
         否则用户会以为取消能回滚开关 -->
    <p class="ext-notice" role="note">{{ t("settings.extensions.immediateNotice") }}</p>
    <p v-if="loading" class="f-hint" role="status">{{ t("settings.extensions.loading") }}</p>
    <div v-else-if="failed" class="ext-failed">
      <p class="f-hint" role="alert">{{ t("settings.extensions.loadFailed") }}</p>
      <button type="button" @click="$emit('retry')">{{ t("settings.retry") }}</button>
    </div>
    <p v-else-if="list.length===0" class="f-hint">{{ t("settings.extensions.empty") }}</p>
    <template v-else>
      <div v-for="group in groups" :key="group.key" class="ext-group">
        <div v-if="group.title" class="group-title">{{ group.title }}</div>
        <ul class="ext-list">
          <ExtensionCard
            v-for="extension in group.items" :key="extension.extension_id"
            :extension="extension" :busy="busy" @toggle="(id, value) => $emit('toggle', id, value)"
          />
        </ul>
      </div>
    </template>
    <p v-if="errorText" class="ext-error" role="alert">{{ errorText }}</p>
  </section>
</template>
<style scoped>
.ext-section{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.ext-notice{margin:0;padding:8px 12px;border-radius:var(--radius-md);background:var(--color-info-bg);color:var(--color-text-secondary);font-size:12px}
.ext-failed{display:flex;flex-direction:column;align-items:flex-start;gap:var(--space-2)}
.ext-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--space-2)}
.ext-group{display:flex;flex-direction:column;gap:var(--space-2)}
.group-title{font-weight:600;font-size:13px;border-left:3px solid var(--color-accent);padding-left:var(--space-2)}
.ext-error{margin:0;color:var(--color-danger);font-size:13px}
</style>
