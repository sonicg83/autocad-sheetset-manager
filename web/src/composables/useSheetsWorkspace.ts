// 图纸页单表工作区状态组合式函数（PLAN-DM-015 任务 3，SPEC-DM-009 §4）。
// 统一 scope/搜索/低频筛选/勾选集合/首屏加载，实例化于主标签之外，跨标签切换保留状态。
// 行 ID 取服务端 ID；查询覆盖完整路径与隐藏属性，不依赖显示列。
// 结构显示消费任务 1 的权威投影（workspace 为投影后的显示副本）。
import {computed, ref, watch} from "vue";
import type {Ref} from "vue";
import type {ChangeCommand, Subset, Sheet, Workspace} from "../api/contracts";
import type {SheetScope} from "../features/sheets/types";

export type SheetRow = {subset: Subset; sheet: Sheet};
export type SheetPathFilter = "all" | "resolved" | "unresolved";
export type SheetDiagFilter = "all" | "blocking" | "clean";
export type SheetPendingFilter = "all" | "pending" | "unchanged";

const RENDER_LIMIT = 80;

export function useSheetsWorkspace(deps: {
  workspace: Ref<Workspace | null>;
  commands: Ref<ChangeCommand[]>;
}) {
  // —— 范围（初始为全部图纸；树与范围筛选共用同一状态）——
  const scope = ref<SheetScope>({kind: "all"});
  const focusedSheetId = ref<string | null>(null);
  // —— 搜索与低频筛选（搜索常驻；低频筛选经「筛选」切换展开）——
  const searchText = ref("");
  const searchAll = ref(false);
  const filtersVisible = ref(false);
  const pathFilter = ref<SheetPathFilter>("all");
  const diagnosticFilter = ref<SheetDiagFilter>("all");
  const pendingFilter = ref<SheetPendingFilter>("all");
  // —— 勾选集合与首屏加载 ——
  const selectedIds = ref<string[]>([]);
  const renderLimit = ref(RENDER_LIMIT);
  // —— 定位与反馈 ——
  const hiddenTarget = ref<string | null>(null); // 目标被筛选排除时暂存其 ID
  const pruneMessage = ref("");                   // 投影删除对象被移出选择时的提示

  // 全部行（跨范围，供搜索全部与批量命令构建）
  const allRows = computed<SheetRow[]>(() => (deps.workspace.value?.sheet_set.subsets ?? []).flatMap(
    (subset) => subset.sheets.map((sheet) => ({subset, sheet})),
  ));
  // 当前范围行
  const scopedRows = computed<SheetRow[]>(() => {
    const current = deps.workspace.value;
    if (!current) return [];
    const currentScope = scope.value;
    if (currentScope.kind === "subset") {
      const subset = current.sheet_set.subsets.find((item) => item.id === currentScope.id);
      if (!subset) return []; // 子集已删除时由 watch 降级为全部
      return subset.sheets.map((sheet) => ({subset, sheet}));
    }
    return allRows.value;
  });
  const scopeTotal = computed(() => scopedRows.value.length);
  const allTotal = computed(() => allRows.value.length);
  const rangeTotal = computed(() => (searchAll.value ? allTotal.value : scopeTotal.value));

  const pendingSheetIds = computed(() => new Set(
    deps.commands.value.flatMap((command) => "sheet_id" in command && typeof command.sheet_id === "string" ? [command.sheet_id] : []),
  ));
  const diagnosticObjectIds = computed(() => new Set(
    (deps.workspace.value?.diagnostics ?? [])
      .filter((item) => item.severity === "error")
      .map((item) => item.object_id)
      .filter((id): id is string => Boolean(id)),
  ));

  // 搜索匹配完整路径与隐藏属性：图号、标题、子集显示名、DWG 文件名/相对路径/解析路径、布局名、全部自定义属性
  function matchesSearch(row: SheetRow, query: string): boolean {
    if (!query) return true;
    return [
      row.sheet.number,
      row.sheet.title,
      row.subset.display_name,
      row.sheet.layout.file_name,
      row.sheet.layout.relative_file_name,
      row.sheet.layout.resolved_path,
      row.sheet.layout.layout_name,
      ...Object.entries(row.sheet.custom_properties).flat(),
    ].filter(Boolean).some((value) => String(value).toLocaleLowerCase().includes(query));
  }

  const filteredRows = computed<SheetRow[]>(() => {
    const query = searchText.value.trim().toLocaleLowerCase();
    const base = searchAll.value ? allRows.value : scopedRows.value;
    return base.filter((row) => {
      const resolved = Boolean(row.sheet.layout.resolved_path);
      if (pathFilter.value === "resolved" && !resolved) return false;
      if (pathFilter.value === "unresolved" && resolved) return false;
      const hasDiagnostic = diagnosticObjectIds.value.has(row.sheet.id);
      if (diagnosticFilter.value === "blocking" && !hasDiagnostic) return false;
      if (diagnosticFilter.value === "clean" && hasDiagnostic) return false;
      const pending = pendingSheetIds.value.has(row.sheet.id);
      if (pendingFilter.value === "pending" && !pending) return false;
      if (pendingFilter.value === "unchanged" && pending) return false;
      return matchesSearch(row, query);
    });
  });

  const visibleRows = computed(() => filteredRows.value.slice(0, renderLimit.value));
  const hiddenSelectedCount = computed(() => [...selectedIds.value]
    .filter((id) => !filteredRows.value.some((row) => row.sheet.id === id)).length);
  const allFilteredSelected = computed(() => filteredRows.value.length > 0
    && filteredRows.value.every((row) => selectedIds.value.includes(row.sheet.id)));

  // —— 范围切换（树与范围筛选共用）——
  function selectAll() { scope.value = {kind: "all"}; } // 只切换范围：不展开树、不自动勾选
  function selectSubset(subsetId: string) { scope.value = {kind: "subset", id: subsetId}; }

  // 点击树中图纸：切换到所属子集并定位对应行，不自动勾选；筛选排除目标时给出提示而非暗中清除
  function locateSheet(sheetId: string) {
    const current = deps.workspace.value;
    const subset = current?.sheet_set.subsets.find((item) => item.sheets.some((sheet) => sheet.id === sheetId));
    focusedSheetId.value = sheetId;
    if (!subset) { hiddenTarget.value = null; return; }
    scope.value = {kind: "subset", id: subset.id};
    renderLimit.value = RENDER_LIMIT;
    // 范围已切换：目标仍被筛选排除 → 标记为被筛选隐藏
    const inFiltered = filteredRows.value.some((row) => row.sheet.id === sheetId);
    hiddenTarget.value = inFiltered ? null : sheetId;
  }

  // 「清除筛选并定位」：清除搜索与全部低频筛选，保留范围与勾选集合
  function clearFilters() {
    searchText.value = "";
    pathFilter.value = "all";
    diagnosticFilter.value = "all";
    pendingFilter.value = "all";
    renderLimit.value = RENDER_LIMIT;
  }

  // 目标重新可见后自动清除隐藏提示
  watch([filteredRows, hiddenTarget], () => {
    if (hiddenTarget.value && filteredRows.value.some((row) => row.sheet.id === hiddenTarget.value)) {
      hiddenTarget.value = null;
    }
  });

  // —— 勾选集合 ——
  function toggleSheet(sheetId: string) {
    selectedIds.value = selectedIds.value.includes(sheetId)
      ? selectedIds.value.filter((id) => id !== sheetId)
      : [...selectedIds.value, sheetId];
  }
  // 全选覆盖全部匹配项（含未加载结果）；取消全选只移除当前匹配
  function toggleFilteredSelection() {
    const ids = filteredRows.value.map((row) => row.sheet.id);
    if (allFilteredSelected.value) {
      selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
    } else {
      selectedIds.value = Array.from(new Set([...selectedIds.value, ...ids]));
    }
  }
  function clearSelection() { selectedIds.value = []; }

  // 搜索变化后回到首屏（沿用旧首屏语义）
  watch(searchText, () => { renderLimit.value = RENDER_LIMIT; });

  // 投影/刷新后：被删除对象从勾选集合修剪并提示；范围子集被删除时降级为全部
  watch(deps.workspace, (current) => {
    if (!current) return;
    const existing = new Set(allRows.value.map((row) => row.sheet.id));
    const pruned = selectedIds.value.filter((id) => !existing.has(id));
    if (pruned.length > 0) {
      selectedIds.value = selectedIds.value.filter((id) => existing.has(id));
      pruneMessage.value = `已从选择中移除 ${pruned.length} 张已删除图纸`;
    }
    const currentScope = scope.value;
    if (currentScope.kind === "subset" && !current.sheet_set.subsets.some((item) => item.id === currentScope.id)) {
      scope.value = {kind: "all"};
    }
  });

  // 重开工作区时清空本域状态
  function reset() {
    scope.value = {kind: "all"};
    focusedSheetId.value = null;
    selectedIds.value = [];
    searchText.value = "";
    searchAll.value = false;
    filtersVisible.value = false;
    pathFilter.value = "all";
    diagnosticFilter.value = "all";
    pendingFilter.value = "all";
    renderLimit.value = RENDER_LIMIT;
    hiddenTarget.value = null;
    pruneMessage.value = "";
  }

  return {
    scope, focusedSheetId, selectedIds, searchText, searchAll, filtersVisible,
    pathFilter, diagnosticFilter, pendingFilter, renderLimit,
    filteredRows, visibleRows, hiddenSelectedCount, allFilteredSelected,
    hiddenTarget, pruneMessage, scopeTotal, allTotal, rangeTotal,
    pendingSheetIds, diagnosticObjectIds, allRows,
    selectAll, selectSubset, locateSheet, clearFilters,
    toggleSheet, toggleFilteredSelection, clearSelection, reset,
  };
}
