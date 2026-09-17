<!-- 第 4 步 匹配模板（SPEC-DB-001 §2）：纳入基础 DWG 与布局模板（复制进项目并固定
     SHA-256），选择源布局。布局探测端口未接线时后端固定 501 CAD_VERSION_UNAVAILABLE，
     界面如实显示"需要 CAD 探测，尚未接线"，不伪造布局列表、不放 disabled 占位。 -->
<script setup lang="ts">
import FieldDiagnostics from "../components/FieldDiagnostics.vue";
import GuidancePanel from "../components/GuidancePanel.vue";
import {onMounted, reactive, ref} from "vue";
import {api, BuilderApiError, type AssetModel} from "../api/client";
import {injectWizardStore} from "../composables/useWizardStore";

const store = injectWizardStore();

const baseSourcePath = ref("");
const layoutSourcePath = ref("");
const inspecting = ref(false);
const inspectState = ref<"idle" | "unavailable" | "failed">("idle");
const inspectMessage = ref("");
const availableLayouts = ref<string[]>([]);

const assetInfo = reactive({base: null as AssetModel | null, layout: null as AssetModel | null});

onMounted(() => {
  void store.refreshCadabilities();
});

async function intake(role: "base" | "layout"): Promise<void> {
  const sourcePath = role === "base" ? baseSourcePath.value : layoutSourcePath.value;
  const asset = await store.intakeAsset(role, sourcePath);
  if (asset) {
    if (role === "base") {
      assetInfo.base = asset;
    } else {
      assetInfo.layout = asset;
    }
    // 资产变化后既有探测结果失效
    availableLayouts.value = [];
    inspectState.value = "idle";
  }
}

async function inspectLayouts(): Promise<void> {
  if (!store.draft.template.layout_asset_id) {
    return;
  }
  inspecting.value = true;
  try {
    const response = await api.inspectAsset(store.draft.template.layout_asset_id, {
      cad_version: store.draft.cad_version as "2016" | "2020",
    });
    availableLayouts.value = response.layouts.filter((layout) => layout !== "Model");
    inspectState.value = "idle";
    inspectMessage.value = "";
  } catch (error) {
    availableLayouts.value = [];
    if (error instanceof BuilderApiError && error.status === 501) {
      inspectState.value = "unavailable";
      inspectMessage.value = "需要 CAD 探测，尚未接线";
    } else {
      inspectState.value = "failed";
      inspectMessage.value = (error as BuilderApiError).message;
    }
  } finally {
    inspecting.value = false;
  }
}

function capabilityNotice(): string {
  const current = store.cadabilities.value.find(
    (capability) => capability.cad_version === store.draft.cad_version,
  );
  if (store.draft.cad_version && current && !current.available) {
    return `本机未检测到 AutoCAD ${store.draft.cad_version} 的 Core Console/插件，布局探测不可用。`;
  }
  return "";
}
</script>

<template>
  <section aria-labelledby="templates-title">
    <GuidancePanel
      title="第4步 匹配模板"
      goal="纳入基础 DWG 与布局模板，选择源布局；资产复制进项目并固定 SHA-256。"
      :hints="['源布局必须由匹配版本的 CAD 验证存在后才能选择。']"
    />
    <FieldDiagnostics />

    <fieldset class="asset-group">
      <legend>基础 DWG</legend>
      <p class="field">
        <label class="field-label" for="t-base-path">基础 DWG 路径</label>
        <input id="t-base-path" v-model="baseSourcePath" data-field="template.base_asset_source" type="text" />
      </p>
      <button type="button" data-testid="intake-base" :disabled="baseSourcePath.trim().length === 0" @click="intake('base')">
        纳入基础 DWG
      </button>
      <p v-if="assetInfo.base" data-testid="asset-base-info" class="asset-info">
        已纳入 {{ assetInfo.base.source_name }}，SHA-256 {{ assetInfo.base.sha256.slice(0, 12) }}…（{{ assetInfo.base.size }} 字节）
      </p>
    </fieldset>

    <fieldset class="asset-group">
      <legend>布局模板</legend>
      <p class="field">
        <label class="field-label" for="t-layout-path">布局模板路径</label>
        <input id="t-layout-path" v-model="layoutSourcePath" data-field="template.layout_asset_source" type="text" />
      </p>
      <button type="button" data-testid="intake-layout" :disabled="layoutSourcePath.trim().length === 0" @click="intake('layout')">
        纳入布局模板
      </button>
      <p v-if="assetInfo.layout" data-testid="asset-layout-info" class="asset-info">
        已纳入 {{ assetInfo.layout.source_name }}，SHA-256 {{ assetInfo.layout.sha256.slice(0, 12) }}…（{{ assetInfo.layout.size }} 字节）
      </p>
    </fieldset>

    <div class="inspect">
      <button
        type="button"
        data-testid="inspect-layout"
        :disabled="!store.draft.template.layout_asset_id || inspecting"
        @click="inspectLayouts"
      >
        探测布局
      </button>
      <p v-if="capabilityNotice()" class="notice" role="status">{{ capabilityNotice() }}</p>
      <p v-if="inspectState === 'unavailable'" data-testid="asset-note" class="notice" role="status">
        需要 CAD 探测，尚未接线：布局 inspection 端口未接入真实 CAD，无法读取布局列表。
      </p>
      <p v-else-if="inspectState === 'failed'" class="field-error" role="alert">{{ inspectMessage }}</p>
      <p v-else-if="availableLayouts.length > 0" class="field">
        <label class="field-label" for="t-source-layout">源布局</label>
        <select id="t-source-layout" v-model="store.draft.template.source_layout"  :disabled="store.buildRunning.value" data-field="template.source_layout">
          <option v-for="layout in availableLayouts" :key="layout" :value="layout">{{ layout }}</option>
        </select>
      </p>
    </div>
  </section>
</template>

<style scoped>
.asset-group {
  margin: 0 0 var(--space-4);
  padding: var(--space-4);
  border: var(--border-width-1) solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  max-width: 480px;
}

.asset-group legend {
  font-size: var(--font-size-14);
  font-weight: 600;
  padding: 0 var(--space-2);
}

.asset-info {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-13);
  color: var(--color-success);
}

.notice {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-13);
  color: var(--color-info);
  background: var(--color-info-bg);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  max-width: 480px;
}
</style>
