<!-- 字段浏览器（SPEC-DM-012 §7.2 区域 2）：按"图纸固有字段 / 图纸集自定义属性 /
     图纸自定义属性"三组展示当前字段目录；点击按规范名称自动生成正确语法并插入
     当前表达式光标位置（点号或方括号 JSON 字符串形式，SPEC §4.2）。
     PLAN-DM-023 Task 2（V4）把条目恢复为冻结 Demo 的双行形态：第一行常显规范引用
     （不带外层花括号），第二行显示用户名称；并恢复本地搜索。搜索只过滤当前已取得
     的字段目录，是页面本地瞬时状态——不进 SheetCatalogController、不发请求、不持久化。 -->
<script setup lang="ts">
import {computed, ref} from "vue";
import {useI18n} from "vue-i18n";
import type {CatalogField, SheetCatalogController} from "../../composables/useSheetCatalog";

const props = defineProps<{catalog: SheetCatalogController}>();
const {t} = useI18n();

const query = ref("");

// 固有字段的第二行用户名称走宿主 i18n；属性名（DST 原文）保持原样不翻译
const BUILTIN_LABEL_KEYS: Record<string, string> = {
  number: "extensions.sheetCatalog.fieldBuiltinNumber",
  title: "extensions.sheetCatalog.fieldBuiltinTitle",
  file_name: "extensions.sheetCatalog.fieldBuiltinFileName",
};

interface FieldEntry {
  key: string;
  reference: string;   // 插入用规范引用，含外层花括号
  display: string;     // 常显正文，去掉外层花括号
  label: string;       // 第二行用户名称
}

function toEntry(field: CatalogField): FieldEntry {
  const reference = props.catalog.fieldReference(field.scope, field.canonicalName);
  const labelKey = field.builtin ? BUILTIN_LABEL_KEYS[field.canonicalName.toLowerCase()] : undefined;
  return {
    key: `${field.scope}:${field.canonicalName}`,
    reference,
    display: reference.slice(1, -1),
    label: labelKey === undefined ? field.canonicalName : t(labelKey),
  };
}

const builtinFields = computed(() => props.catalog.fieldCatalog.value.sheet.filter(field => field.builtin));
const sheetFields = computed(() => props.catalog.fieldCatalog.value.sheet.filter(field => !field.builtin));

// 分组标签参与匹配，因此"图纸固有字段"这类作用域关键字也能过滤（PLAN-DM-023 Task 2）
const groups = computed(() => [
  {id: "builtin", label: t("extensions.sheetCatalog.fieldGroupBuiltin"), entries: builtinFields.value.map(toEntry)},
  {id: "sheetset", label: t("extensions.sheetCatalog.fieldGroupSheetset"), entries: props.catalog.fieldCatalog.value.sheetset.map(toEntry)},
  {id: "sheet", label: t("extensions.sheetCatalog.fieldGroupSheet"), entries: sheetFields.value.map(toEntry)},
]);

const visibleGroups = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase();
  if (needle === "") return groups.value;
  return groups.value
    .map(group => ({
      ...group,
      entries: group.entries.filter(entry => `${group.label} ${entry.label} ${entry.display}`.toLocaleLowerCase().includes(needle)),
    }))
    .filter(group => group.entries.length > 0);
});

const searching = computed(() => query.value.trim() !== "");
const noMatches = computed(() => searching.value && visibleGroups.value.length === 0);
</script>
<template>
  <section class="field-browser panel" :aria-label="$t('extensions.sheetCatalog.fieldBrowserLabel')">
    <div class="field-head">
      <h3>{{ $t("extensions.sheetCatalog.fieldBrowserLabel") }}</h3>
      <span class="field-hint">{{ $t("extensions.sheetCatalog.fieldHint") }}</span>
    </div>
    <div class="field-search">
      <input
        v-model="query"
        type="text"
        :aria-label="$t('extensions.sheetCatalog.fieldSearchLabel')"
        :placeholder="$t('extensions.sheetCatalog.fieldSearchPlaceholder')"
      >
    </div>
    <div class="field-list">
      <section v-for="group in visibleGroups" :key="group.id" class="field-group">
        <h4>{{ group.label }}</h4>
        <ul v-if="group.entries.length > 0">
          <li v-for="entry in group.entries" :key="entry.key">
            <button
              type="button"
              class="field-chip"
              :title="entry.reference"
              @click="catalog.insertReference(entry.reference)"
            >
              <code>{{ entry.display }}</code>
              <small>{{ entry.label }}</small>
            </button>
          </li>
        </ul>
        <p v-else-if="!searching" class="empty-hint">{{ $t("extensions.sheetCatalog.fieldGroupEmpty") }}</p>
      </section>
      <p v-if="noMatches" class="field-empty">{{ $t("extensions.sheetCatalog.fieldSearchEmpty") }}</p>
      <p class="field-syntax">{{ $t("extensions.sheetCatalog.fieldSyntaxHint") }}</p>
    </div>
  </section>
</template>
<style scoped>
.field-browser{display:flex;flex-direction:column;gap:var(--space-2);min-width:0;min-height:0;overflow:hidden}
.field-head{display:flex;align-items:baseline;gap:var(--space-2);min-width:0}
.field-head h3{margin:0;font-size:14px}
.field-hint{margin-left:auto;color:var(--color-text-muted);font-size:12px;text-align:right}
.field-search input{width:100%;padding:7px 9px;border:1px solid var(--color-border-strong);border-radius:var(--radius-md);font-size:13px}
.field-list{display:flex;flex-direction:column;overflow:auto;min-height:0;flex:1;margin:0 calc(-1 * var(--space-1));padding:0 var(--space-1)}
.field-group h4{margin:var(--space-2) 0 var(--space-1);padding:0 2px;font-size:12px;font-weight:600;color:var(--color-text-secondary)}
.field-group ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.field-chip{display:block;width:100%;text-align:left;padding:6px 8px;border:1px solid transparent;border-radius:var(--radius-md);background:transparent;color:inherit;min-height:0}
.field-chip:hover{border-color:var(--color-border-subtle);background:var(--color-info-bg)}
.field-chip code{display:block;font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--color-text-primary);white-space:normal;overflow-wrap:anywhere}
.field-chip small{display:block;margin-top:2px;color:var(--color-text-secondary);font-size:12px;overflow-wrap:anywhere}
.field-empty{margin:var(--space-2) 2px;color:var(--color-text-muted);font-size:12px}
.empty-hint{margin:var(--space-1) 2px;color:var(--color-text-muted);font-size:12px}
.field-syntax{margin:var(--space-2) 2px 0;color:var(--color-text-muted);font-size:12px;line-height:1.7}
</style>
