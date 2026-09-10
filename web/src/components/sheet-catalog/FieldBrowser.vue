<!-- 字段浏览器（SPEC-DM-012 §7.2 区域 2）：按"图纸固有字段 / 图纸集自定义属性 /
     图纸自定义属性"三组展示当前字段目录；点击按规范名称自动生成正确语法并插入
     当前表达式光标位置（点号或方括号 JSON 字符串形式，SPEC §4.2）。 -->
<script setup lang="ts">
import type {SheetCatalogController} from "../../composables/useSheetCatalog";

defineProps<{catalog: SheetCatalogController}>();
</script>
<template>
  <section class="field-browser panel" :aria-label="$t('extensions.sheetCatalog.fieldBrowserLabel')">
    <h3>{{ $t("extensions.sheetCatalog.fieldBrowserLabel") }}</h3>
    <p class="hint">{{ $t("extensions.sheetCatalog.fieldHint") }}</p>
    <div class="field-group">
      <h4>{{ $t("extensions.sheetCatalog.fieldGroupBuiltin") }}</h4>
      <ul>
        <li v-for="field in catalog.fieldCatalog.value.sheet.filter(item => item.builtin)" :key="`builtin:${field.canonicalName}`">
          <button
            type="button"
            :title="catalog.fieldReference('sheet', field.canonicalName)"
            @click="catalog.insertReference(catalog.fieldReference('sheet', field.canonicalName))"
          >{{ field.canonicalName }}</button>
        </li>
      </ul>
    </div>
    <div class="field-group">
      <h4>{{ $t("extensions.sheetCatalog.fieldGroupSheetset") }}</h4>
      <ul>
        <li v-for="field in catalog.fieldCatalog.value.sheetset" :key="`sheetset:${field.canonicalName}`">
          <button
            type="button"
            :title="catalog.fieldReference('sheetset', field.canonicalName)"
            @click="catalog.insertReference(catalog.fieldReference('sheetset', field.canonicalName))"
          >{{ field.canonicalName }}</button>
        </li>
      </ul>
      <p v-if="catalog.fieldCatalog.value.sheetset.length === 0" class="empty">{{ $t("extensions.sheetCatalog.fieldGroupEmpty") }}</p>
    </div>
    <div class="field-group">
      <h4>{{ $t("extensions.sheetCatalog.fieldGroupSheet") }}</h4>
      <ul>
        <li v-for="field in catalog.fieldCatalog.value.sheet.filter(item => !item.builtin)" :key="`sheet:${field.canonicalName}`">
          <button
            type="button"
            :title="catalog.fieldReference('sheet', field.canonicalName)"
            @click="catalog.insertReference(catalog.fieldReference('sheet', field.canonicalName))"
          >{{ field.canonicalName }}</button>
        </li>
      </ul>
      <p v-if="catalog.fieldCatalog.value.sheet.filter(item => !item.builtin).length === 0" class="empty">{{ $t("extensions.sheetCatalog.fieldGroupEmpty") }}</p>
    </div>
  </section>
</template>
<style scoped>
.field-browser{display:flex;flex-direction:column;gap:var(--space-2);min-width:0}
.field-browser h3{margin:0;font-size:14px}
.hint{margin:0;color:var(--color-text-muted);font-size:12px}
.field-group h4{margin:var(--space-2) 0 var(--space-1);font-size:13px;color:var(--color-text-secondary)}
.field-group ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.field-group button{padding:4px 10px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);background:var(--color-bg-muted);font-size:13px}
.field-group button:hover{border-color:var(--color-accent);color:var(--color-accent)}
.empty{margin:0;color:var(--color-text-muted);font-size:12px}
</style>
