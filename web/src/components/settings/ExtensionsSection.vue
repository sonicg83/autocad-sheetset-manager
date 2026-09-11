<script setup lang="ts">
// 设置中心扩展分区（本次修复：让扩展停用可逆 / ARCH-DM-006 §7、SPEC-DM-011）。
// 背景：启停控件原先只长在扩展自己的页面上，而停用会移除该页面入口，开关因此
// 变成单向——用户点一次停用就再也找不到启用入口，且状态持久化在 extension_states。
//
// SPEC-DM-011 修订「启停交互改进」：启停控件由文字按钮改为滑动开关（role="switch" + aria-checked），
// 并在开关左侧给出可见的「已启用/已停用」文字状态——开关方向不能只靠颜色与滑块
// 位置表达，否则色觉障碍用户与屏幕阅读之外的场景都读不出当前状态。开关的方位与
// 文字都取自服务端 enabled，绝不由 status 反推。
//
// 纯呈现组件：列表、加载/失败/错误文案全部由 SettingsDialog 传入。启停编排
//（未保存输入三选一闸门、标签与焦点收敛）由 SettingsDialog + App 负责，本组件
// 绝不自行调用扩展端点——绕过闸门会静默丢草稿。
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";

defineProps<{
  list: ExtensionSummary[];
  loading: boolean;
  failed: boolean;
  errorText: string;
  busy: boolean;
}>();
defineEmits<{retry: []; toggle: [extensionId: string, enabled: boolean]}>();
const {t}=useI18n();
// 已启用判定以服务端 enabled 为准：status 可能是 FAILED/INCOMPATIBLE 这类"天然不可用"
// 值，与用户启停意图在该表上是可区分的（ARCH-DM-006 §5），不能拿 status 反推开关方向。
// 因此「已启用 + 启动失败」是合法呈现（runtime.py 刻意把 enabled 与 status 分开持久化），
// 本组件不做任何把开关拨回关闭的修正。
const isEnabled=(extension:ExtensionSummary):boolean=>extension.enabled;
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
    <ul v-else class="ext-list">
      <li v-for="extension in list" :key="extension.extension_id" class="ext-row" :data-extension-id="extension.extension_id">
        <div class="ext-info">
          <span class="ext-name">{{ t(extension.name_key) }}</span>
          <span class="ext-meta">v{{ extension.version }} · {{ t(`extensions.status.${extension.status}`) }}</span>
        </div>
        <div class="ext-control">
          <!-- 可见状态文字：语义仍由开关自身的 aria-checked 承担，故对辅助技术隐藏，
               避免"已启用 启用 图纸目录"这类重复播报 -->
          <span class="ext-state" :class="{on:isEnabled(extension)}" aria-hidden="true">{{ isEnabled(extension) ? t("settings.extensions.stateOn") : t("settings.extensions.stateOff") }}</span>
          <button
            type="button"
            class="switch"
            role="switch"
            :aria-checked="isEnabled(extension)"
            :aria-label="isEnabled(extension) ? t('settings.extensions.disableNamed',{name:t(extension.name_key)}) : t('settings.extensions.enableNamed',{name:t(extension.name_key)})"
            :disabled="busy"
            @click="$emit('toggle',extension.extension_id,!isEnabled(extension))"
          ><span class="switch-thumb" aria-hidden="true"></span></button>
        </div>
      </li>
    </ul>
    <p v-if="errorText" class="ext-error" role="alert">{{ errorText }}</p>
  </section>
</template>
<style scoped>
.ext-section{display:flex;flex-direction:column;gap:var(--space-3);min-width:0}
.ext-notice{margin:0;padding:8px 12px;border-radius:var(--radius-md);background:var(--color-info-bg);color:var(--color-text-secondary);font-size:12px}
.ext-failed{display:flex;flex-direction:column;align-items:flex-start;gap:var(--space-2)}
.ext-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--space-2)}
.ext-row{display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.ext-info{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
.ext-name{color:var(--color-text-primary);font-size:14px;font-weight:500;overflow-wrap:anywhere}
.ext-meta{color:var(--color-text-muted);font-size:12px}
.ext-control{display:flex;align-items:center;gap:var(--space-2);flex:none}
.ext-state{font-size:12px;color:var(--color-text-muted)}
.ext-state.on{color:var(--color-success)}
/* 滑动开关：轨道尺寸与滑块用 --radius-full/--color-accent 等既有令牌，
   开态颜色=强调色、关态=弱化底色；禁用态沿用全局 button:disabled 的透明度语义 */
.switch{position:relative;flex:none;width:44px;height:24px;padding:0;border:1px solid var(--color-border-strong);border-radius:var(--radius-full);background:var(--color-bg-muted);cursor:pointer;transition:background-color .15s ease,border-color .15s ease}
.switch[aria-checked="true"]{background:var(--color-accent);border-color:var(--color-accent)}
.switch:disabled{cursor:not-allowed}
.switch-thumb{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:var(--radius-full);background:var(--color-bg-surface);box-shadow:var(--shadow-1);transition:transform .15s ease}
.switch[aria-checked="true"] .switch-thumb{transform:translateX(20px)}
@media (prefers-reduced-motion:reduce){.switch,.switch-thumb{transition:none}}
.ext-error{margin:0;color:var(--color-danger);font-size:13px}
</style>
