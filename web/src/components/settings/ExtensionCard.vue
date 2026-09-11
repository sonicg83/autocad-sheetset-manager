<script setup lang="ts">
// 扩展卡片（SPEC-DM-011 §3.3 / SC-16）。纯呈现：状态容器 + 唯一开关，
// 不可点击、不导航——卡片上不得长出扩展自身设置的入口（后者归扩展页面，ARCH-DM-006 §8）。
// 四层信息固定顺序：①名称+版本 ②描述 ③状态徽标+诊断码 ④开关与可见状态文字。
// 开关方向只取服务端 enabled；status 只决定徽标色调与诊断码，"已启用 + 启动失败"
// 是合法组合，不得互相否认（ARCH-DM-006 §5）。
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";
import BooleanSwitch from "./BooleanSwitch.vue";

const props = defineProps<{extension: ExtensionSummary; busy: boolean}>();
const emit = defineEmits<{toggle: [extensionId: string, enabled: boolean]}>();
const {t} = useI18n();

const name = computed(() => t(props.extension.name_key));
const enabled = computed(() => props.extension.enabled);
// 徽标色调：可用=成功、启动失败=危险、不兼容/等待依赖=警告，其余（已停用/过渡态）=弱化
const tone = computed(() => {
  switch (props.extension.status) {
    case "AVAILABLE": return "success";
    case "FAILED": return "danger";
    case "INCOMPATIBLE":
    case "WAITING_DEPENDENCY": return "warning";
    default: return "muted";
  }
});
// 可见状态文字与分组标题共用措辞（同一状态不出现两套说法）；位置在开关左侧，
// 与冻结件 g4-07～g4-11 一致（控件本身不渲染文字，由本卡片布局）
const stateText = computed(() => enabled.value ? t("settings.extensions.stateOn") : t("settings.extensions.stateOff"));
const switchLabel = computed(() => enabled.value
  ? t("settings.extensions.disableNamed", {name: name.value})
  : t("settings.extensions.enableNamed", {name: name.value}));
</script>
<template>
  <li class="ext-card" :data-extension-id="extension.extension_id">
    <div class="ext-main">
      <span class="ext-name">{{ name }}</span>
      <span class="ext-desc">{{ t(extension.description_key) }}</span>
      <span class="ext-meta">
        <span class="badge muted">v{{ extension.version }}</span>
        <span class="badge" :class="tone">{{ t(`extensions.status.${extension.status}`) }}</span>
        <!-- 诊断码原样显示稳定枚举名，不翻译、不拼接后端文本（ARCH-DM-006 §4.3） -->
        <span v-if="extension.error_code" class="ext-diag">{{ t("settings.extensions.diagnosticCode", {code: extension.error_code}) }}</span>
      </span>
    </div>
    <div class="ext-side">
      <span class="ext-state" :class="{on:enabled}" aria-hidden="true">{{ stateText }}</span>
      <BooleanSwitch
        :checked="enabled" :disabled="busy" :label="switchLabel"
        :data-key="extension.extension_id"
        @change="value => emit('toggle', extension.extension_id, value)"
      />
    </div>
  </li>
</template>
<style scoped>
.ext-card{display:flex;align-items:flex-start;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.ext-main{display:flex;flex-direction:column;gap:var(--space-1);min-width:0;flex:1}
.ext-name{color:var(--color-text-primary);font-size:14px;font-weight:500;overflow-wrap:anywhere}
.ext-desc{color:var(--color-text-secondary);font-size:12px;line-height:1.7}
.ext-meta{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;font-size:12px}
.badge{font-size:12px;padding:2px 10px;border-radius:var(--radius-full)}
.badge.muted{background:var(--color-bg-muted);color:var(--color-text-secondary)}
.badge.success{background:var(--color-success-bg);color:var(--color-success)}
.badge.warning{background:var(--color-warning-bg);color:var(--color-warning)}
.badge.danger{background:var(--color-danger-bg);color:var(--color-danger)}
.ext-diag{color:var(--color-warning)}
.ext-side{display:flex;align-items:center;gap:var(--space-2);flex:none;padding-top:2px}
.ext-state{font-size:12px;color:var(--color-text-muted)}
.ext-state.on{color:var(--color-success)}
</style>
