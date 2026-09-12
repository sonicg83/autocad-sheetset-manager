<!-- 字段浏览器（SPEC-DM-012 §7.2 区域 2）：按"图纸固有字段 / 图纸集自定义属性 /
     图纸自定义属性"三组展示当前字段目录；点击按规范名称自动生成正确语法并插入
     当前表达式光标位置（点号或方括号 JSON 字符串形式，SPEC §4.2）。
     PLAN-DM-023 Task 2（V4）把条目恢复为冻结 Demo 的双行形态：第一行常显规范引用
     （不带外层花括号），第二行显示用户名称；并恢复本地搜索。搜索只过滤当前已取得
     的字段目录，是页面本地瞬时状态——不进 SheetCatalogController、不发请求、不持久化。
     PLAN-DM-026 Task 3 按 SPEC-DM-012 §7.2 区域 2 在条目内新增数字格式码入口：
     只把 §5.4 的格式码拼进引用文本（只读导出的输出格式化），不修改 DST/DWG、
     不写回属性值、不做重编号，插入仍走既有 insertReference 光标协议。 -->
<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import type {CatalogField, SheetCatalogController} from "../../composables/useSheetCatalog";
import {applyNumberFormat, NUMBER_FORMAT_WIDTHS, STRIP_ZEROS_WIDTH} from "./formatCode";

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

// ---- 数字格式码入口（PLAN-DM-026 Task 3 / SPEC-DM-012 §7.2 区域 2）----
// 轻量 disclosure（非 ARIA menu）：原生按钮 + aria-expanded/aria-controls，菜单仅在打开时渲染。
// 选项是普通 Tab 停靠点，没有 roving tabindex / 方向键 / type-ahead，也不在打开时移动焦点，
// 因此不声明 menu/menuitem，避免向辅助技术承诺一套未实现的键盘模型。
// 菜单在流内展开而非浮层，避免被 .field-browser/.field-list 的 overflow 裁切；
// 触发按钮与选项的可访问名都不含字段引用文本（如 sheet.number），否则区域内
// 既有的 getByRole("button", {name: /sheet\.number/}) 严格定位会多出一个匹配。
const openFormatKey = ref<string | null>(null);
// 每个条目行只渲染自己的菜单，因此单一“最后打开的触发按钮”足以支持 Escape 归还焦点
let activeTrigger: HTMLButtonElement | null = null;

// 触发按钮与当前菜单的公共祖先选择器：命中即视为“点在格式入口内部”
const FORMAT_ENTRY_SELECTOR = ".field-format-entry, .field-format-menu";

// 选项组的 DOM id：分组 id + 行内序号组合，保证 aria-controls 的 IDREF 唯一且不含空白
// （字段规范名可能含空格或冒号，直接拼进 id 会破坏 IDREF；group.id 只取 builtin/sheetset/sheet）。
function formatMenuId(groupId: string, index: number) {
  return `field-format-menu-${groupId}-${index}`;
}

function toggleFormatMenu(key: string, event: MouseEvent) {
  const trigger = event.currentTarget as HTMLButtonElement;
  if (openFormatKey.value === key) {
    openFormatKey.value = null;
    return;
  }
  activeTrigger = trigger;
  openFormatKey.value = key;
}

function closeFormatMenu() {
  openFormatKey.value = null;
}

function insertFormatCode(entry: FieldEntry, width: number) {
  props.catalog.insertReference(applyNumberFormat(entry.reference, width));
  closeFormatMenu();
}

function onDocumentPointerDown(event: PointerEvent) {
  if (openFormatKey.value === null) return;
  if (event.target instanceof Element && event.target.closest(FORMAT_ENTRY_SELECTOR) !== null) return;
  closeFormatMenu();
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape" || openFormatKey.value === null) return;
  closeFormatMenu();
  activeTrigger?.focus();
}

// 被搜索过滤掉的行不再渲染；若不同步关闭菜单状态，清空搜索会让该行菜单意外重新展开
watch(query, () => {
  if (openFormatKey.value !== null) closeFormatMenu();
});

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown);
  document.addEventListener("keydown", onDocumentKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  document.removeEventListener("keydown", onDocumentKeydown);
});
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
          <li v-for="(entry, index) in group.entries" :key="entry.key" class="field-entry">
            <div class="field-entry-main">
              <button
                type="button"
                class="field-chip"
                :title="entry.reference"
                @click="catalog.insertReference(entry.reference)"
              >
                <code>{{ entry.display }}</code>
                <small>{{ entry.label }}</small>
              </button>
              <div class="field-format-entry">
                <button
                  type="button"
                  class="format-trigger"
                  :aria-label="$t('extensions.sheetCatalog.fieldFormatButton')"
                  :aria-expanded="openFormatKey === entry.key"
                  :aria-controls="formatMenuId(group.id, index)"
                  @click="toggleFormatMenu(entry.key, $event)"
                >
                  {{ $t("extensions.sheetCatalog.fieldFormatButton") }}
                </button>
              </div>
            </div>
            <ul
              v-if="openFormatKey === entry.key"
              :id="formatMenuId(group.id, index)"
              class="field-format-menu"
              role="group"
              :aria-label="$t('extensions.sheetCatalog.fieldFormatMenuLabel')"
            >
              <li>
                <button type="button" class="format-option" @click="insertFormatCode(entry, STRIP_ZEROS_WIDTH)">
                  {{ $t("extensions.sheetCatalog.fieldFormatStripZeros") }}
                </button>
              </li>
              <li v-for="width in NUMBER_FORMAT_WIDTHS" :key="width">
                <button type="button" class="format-option" @click="insertFormatCode(entry, width)">
                  {{ $t("extensions.sheetCatalog.fieldFormatPad", {width}) }}
                </button>
              </li>
            </ul>
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
.field-entry{display:flex;flex-direction:column;min-width:0}
.field-entry-main{display:flex;align-items:flex-start;gap:2px;min-width:0}
.field-chip{display:block;flex:1 1 auto;min-width:0;text-align:left;padding:6px 8px;border:1px solid transparent;border-radius:var(--radius-md);background:transparent;color:inherit;min-height:0}
/* 格式入口触发按钮固定宽度、不参与伸缩，字段栏轨道宽度因此保持 258px 不变 */
.field-format-entry{flex:none}
.format-trigger{padding:6px;border:1px solid transparent;border-radius:var(--radius-md);background:transparent;color:var(--color-text-secondary);font-size:12px;white-space:nowrap}
.format-trigger:hover{border-color:var(--color-border-subtle);background:var(--color-info-bg)}
.format-trigger[aria-expanded="true"]{border-color:var(--color-border-strong);color:var(--color-text-primary)}
/* 菜单在流内展开：超长选项在菜单内换行，不把字段栏撑宽。
   选择器带上 .field-entry 以高于 .field-group ul 的优先级，否则菜单的内边距/外边距被后者覆盖 */
.field-entry .field-format-menu{list-style:none;margin:2px 0 var(--space-1);padding:2px;display:flex;flex-direction:column;gap:2px;border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-muted);min-width:0}
.format-option{display:block;width:100%;text-align:left;padding:4px 6px;border-radius:var(--radius-sm);background:transparent;color:inherit;font-size:12px;overflow-wrap:anywhere}
.format-option:hover{background:var(--color-info-bg)}
.field-chip:hover{border-color:var(--color-border-subtle);background:var(--color-info-bg)}
.field-chip code{display:block;font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--color-text-primary);white-space:normal;overflow-wrap:anywhere}
.field-chip small{display:block;margin-top:2px;color:var(--color-text-secondary);font-size:12px;overflow-wrap:anywhere}
.field-empty{margin:var(--space-2) 2px;color:var(--color-text-muted);font-size:12px}
.empty-hint{margin:var(--space-1) 2px;color:var(--color-text-muted);font-size:12px}
.field-syntax{margin:var(--space-2) 2px 0;color:var(--color-text-muted);font-size:12px;line-height:1.7}
/* PLAN-DM-023 Task 5：≤980px 单列布局下限高 235px，字段列表内部滚动，
   输出列与预览不因字段数量继续下移（与冻结 Demo 的 field-card max-height 一致） */
@media (max-width: 980px){.field-browser{max-height:235px}}
</style>
