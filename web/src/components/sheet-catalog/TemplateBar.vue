<!-- 模板栏（SPEC-DM-012 §7.2 区域 1）：模板选择、保存/另存为/删除入口、保存错误
     与冲突恢复面板（SPEC §11：冲突保留本地编辑，明确提供"另存为 / 按新修订重试"，
     不只显示泛化保存失败）。删除确认模态由页面装配层提供。 -->
<script setup lang="ts">
import {nextTick, ref, watch} from "vue";
import type {SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const emit = defineEmits<{saved: []; removed: []; confirmRemove: []}>();

const saveAsOpen = ref(false);
const saveAsName = ref("");
const card = ref<HTMLElement | null>(null);

async function onSave() {
  if (await props.catalog.saveInPlace()) emit("saved");
}
function openSaveAs() {
  props.catalog.dismissConflict();
  saveAsName.value = props.catalog.canSaveInPlace.value ? props.catalog.draft.value.name : "";
  saveAsOpen.value = true;
  void nextTick(() => card.value?.focus());
}
watch(saveAsOpen, open => {
  if (open) void nextTick(() => card.value?.focus());
  else props.catalog.dismissConflict();
});
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
          <option v-for="template in catalog.templates.value" :key="template.templateId ?? template.name" :value="template.templateId">{{ template.name }}</option>
        </select>
      </label>
      <span v-if="catalog.dirty.value" class="dirty-badge">{{ $t("extensions.sheetCatalog.dirtyBadge") }}</span>
      <span v-if="catalog.dirty.value && !catalog.canSaveInPlace.value" class="draft-name">{{ $t("extensions.sheetCatalog.unnamedDraft") }}</span>
      <span class="spacer"></span>
      <button v-if="catalog.canSaveInPlace.value" type="button" :disabled="!catalog.dirty.value || catalog.saving.value" @click="onSave">{{ catalog.saving.value ? $t("extensions.sheetCatalog.saving") : $t("extensions.sheetCatalog.save") }}</button>
      <button type="button" @click="openSaveAs">{{ $t("extensions.sheetCatalog.saveAs") }}</button>
      <button v-if="catalog.canSaveInPlace.value" type="button" @click="emit('confirmRemove')">{{ $t("extensions.sheetCatalog.remove") }}</button>
    </div>
    <p v-if="catalog.saveError.value" class="error notice" role="alert">{{ catalog.saveError.value }}</p>
    <div v-if="catalog.conflict.value" class="conflict" role="alert" :aria-label="$t('extensions.sheetCatalog.conflictTitle')">
      <h3>{{ $t("extensions.sheetCatalog.conflictTitle") }}</h3>
      <p>{{ $t("extensions.sheetCatalog.conflictMessage") }}</p>
      <div class="template-row">
        <button type="button" @click="openSaveAs">{{ $t("extensions.sheetCatalog.conflictSaveAs") }}</button>
        <button type="button" :disabled="catalog.saving.value" @click="catalog.retryAfterConflict()">{{ $t("extensions.sheetCatalog.conflictRetry") }}</button>
      </div>
    </div>
    <div v-if="saveAsOpen" class="modal-mask" @keydown.escape.prevent="saveAsOpen=false">
      <div class="modal-card" role="dialog" aria-modal="true" :aria-label="$t('extensions.sheetCatalog.saveAsTitle')" tabindex="-1" ref="card">
        <h2>{{ $t("extensions.sheetCatalog.saveAsTitle") }}</h2>
        <label class="save-as-name">
          <span>{{ $t("extensions.sheetCatalog.saveAsNameLabel") }}</span>
          <input v-model="saveAsName" type="text" :aria-label="$t('extensions.sheetCatalog.saveAsNameLabel')" @keydown.enter="confirmSaveAs">
        </label>
        <div class="modal-actions">
          <button type="button" @click="saveAsOpen=false">{{ $t("extensions.sheetCatalog.cancel") }}</button>
          <button type="button" class="primary" :disabled="catalog.saving.value || saveAsName.trim() === ''" @click="confirmSaveAs">{{ $t("extensions.sheetCatalog.saveAsConfirm") }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.template-bar{display:flex;flex-direction:column;gap:var(--space-3)}
.template-row{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
.template-select{display:grid;gap:4px;font-size:13px;color:var(--color-text-secondary)}
.template-select select{min-width:220px;padding:8px;border:1px solid var(--color-border-strong);border-radius:5px}
.dirty-badge{color:var(--color-warning);font-size:13px}
.draft-name{color:var(--color-text-muted);font-size:13px}
.spacer{flex:1}
.conflict{border:1px solid var(--color-warning);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);background:var(--color-warning-bg)}
.conflict h3{margin:0 0 var(--space-2);font-size:14px}
.conflict p{margin:0 0 var(--space-3);color:var(--color-text-primary);font-size:14px}
.save-as-name{display:grid;gap:5px;color:var(--color-text-secondary);font-size:13px}
.save-as-name input{padding:8px;border:1px solid var(--color-border-strong);border-radius:5px}
</style>
