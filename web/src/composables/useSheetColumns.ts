// 图纸页显示列配置组合式函数（PLAN-DM-015 任务 4，SPEC-DM-009 §5）。
// 消费任务 2 的 load/save_sheet_columns 壳桥与服务端图纸属性定义；配置按图纸集记忆在应用数据目录。
// builtin:/sheet: 命名空间区分内置列与图纸自定义属性（字段身份含作用域，不与内置列同名冲突）；
// 删除字段只从可见配置移除、偏好以墓碑保留（撤销删除恢复此前开关）；新增字段默认关并在入口提示。
// 保存按工作区 ID 排队，切工作区后旧保存按代次作废，不覆盖新工作区的偏好。
import {computed, ref, watch} from "vue";
import type {Ref} from "vue";
import type {ColumnPreferences, PropertyKey, SheetScope} from "../features/sheets/types";
import type {Workspace} from "../api/contracts";
import {loadSheetColumns, saveSheetColumns} from "../api/shell";

export type BuiltinColumnKey = "select" | "number" | "title" | "subset" | "file" | "layout" | "status" | "actions";
export type BuiltinPrefField = "file" | "layout" | "subsetAll" | "subsetSingle";

export type SheetColumn = {
  key: string;            // builtin:select | sheet:图幅
  label: string;          // 显示名（属性保留服务端原名）
  kind: "builtin" | "sheet";
  fixed: boolean;         // 固定列不可隐藏
  visible: boolean;
};

export type SheetColumnOption = SheetColumn & {
  name?: string;          // sheet: 字段原始名称（配置面板切换用）
  newField: boolean;      // 配置建立后新增的字段（首次默认不视为新增）
  prefField?: BuiltinPrefField; // 可选内置列写入的偏好字段（子集列随范围取 subsetAll/subsetSingle）
};

const BUILTIN_LABELS: Record<BuiltinColumnKey, string> = {
  select: "选择", number: "图号", title: "标题", subset: "子集",
  file: "文件名", layout: "布局", status: "状态", actions: "操作",
};
// 配置面板锁定展示的固定内置列（选择列恒显但不在面板列出）
const LOCKED_BUILTINS: BuiltinColumnKey[] = ["number", "title", "status", "actions"];
const OPTIONAL_BUILTINS: Array<{key: BuiltinColumnKey; pref: BuiltinPrefField}> = [
  {key: "file", pref: "file"},
  {key: "layout", pref: "layout"},
];
// 首次默认开的三项按定义顺序；不足三项全部显示
const DEFAULT_PROPERTY_COUNT = 3;

const SAVE_FAILED_MESSAGE = "列配置保存失败，当前选择仍在本会话生效";
const LOAD_FAILED_MESSAGE = "读取列配置失败，本次使用默认显示";

// PropertyKey 名称按既有大小写匹配规则规范化（与 drafts.ts 的 custom_property 键一致），显示保留原名
function propertyKey(name: string): PropertyKey {
  return `sheet:${name.toLocaleLowerCase()}`;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

// 首次默认：文件名开、布局关、全部/单子集子集列开关、按定义顺序前三项属性开
function buildDefaults(definitions: {name: string}[]): ColumnPreferences {
  const properties: Record<PropertyKey, boolean> = {};
  definitions.forEach((item, index) => {
    properties[propertyKey(item.name)] = index < DEFAULT_PROPERTY_COUNT;
  });
  return {schemaVersion: 1, file: true, layout: false, subsetAll: true, subsetSingle: false, properties};
}

export function useSheetColumns(deps: {
  workspace: Ref<Workspace | null>;
  scope: Ref<SheetScope>;
}) {
  const preferences = ref<ColumnPreferences | null>(null);
  const saveError = ref("");
  let loadGeneration = 0;            // 每次工作区加载递增，作废在途读取/保存结果
  let saveQueue: Promise<void> = Promise.resolve();

  // 仅消费图纸作用域属性定义（图纸集属性不进入表格）
  const sheetDefinitions = computed(() =>
    (deps.workspace.value?.sheet_set.property_definitions ?? [])
      .filter((item) => item.type === "sheet"),
  );

  // 配置建立后新增且尚未被用户处理的字段数（首次默认应用时全在映射内，计数为 0）
  const newPropertyCount = computed(() => {
    const prefs = preferences.value;
    if (!prefs) return 0;
    return sheetDefinitions.value.filter((item) => !(propertyKey(item.name) in prefs.properties)).length;
  });

  // 子集列按当前范围取对应的偏好字段
  function subsetVisible(prefs: ColumnPreferences): boolean {
    return deps.scope.value.kind === "all" ? prefs.subsetAll : prefs.subsetSingle;
  }

  // 表格可见列：固定选择/图号/标题/状态/操作 + 可选子集/文件名/布局 + 可见属性列（状态与操作之间）
  const visibleColumns = computed<SheetColumn[]>(() => {
    const prefs = preferences.value;
    if (!prefs) return [];
    const builtin = (key: BuiltinColumnKey): SheetColumn =>
      ({key: `builtin:${key}`, label: BUILTIN_LABELS[key], kind: "builtin", fixed: LOCKED_BUILTINS.includes(key) || key === "select", visible: true});
    const props: SheetColumn[] = sheetDefinitions.value
      .filter((item) => prefs.properties[propertyKey(item.name)] === true)
      .map((item) => ({key: propertyKey(item.name), label: item.name, kind: "sheet", fixed: false, visible: true}));
    return [
      builtin("select"), builtin("number"), builtin("title"),
      ...(subsetVisible(prefs) ? [builtin("subset")] : []),
      ...(prefs.file ? [builtin("file")] : []),
      ...(prefs.layout ? [builtin("layout")] : []),
      builtin("status"),
      ...props,
      builtin("actions"),
    ];
  });

  // 配置面板选项：固定列锁定 + 可选内置列 + 全部属性（含新增标记）
  const columnOptions = computed<SheetColumnOption[]>(() => {
    const prefs = preferences.value;
    if (!prefs) return [];
    const scopeKey: BuiltinPrefField = deps.scope.value.kind === "all" ? "subsetAll" : "subsetSingle";
    const locked: SheetColumnOption[] = LOCKED_BUILTINS.map((key) => ({
      key: `builtin:${key}`, label: BUILTIN_LABELS[key], kind: "builtin", fixed: true, visible: true, newField: false,
    }));
    const optional: SheetColumnOption[] = [
      {key: "subset", label: "所属子集（当前范围）", kind: "builtin", fixed: false, visible: subsetVisible(prefs), newField: false, prefField: scopeKey},
      ...OPTIONAL_BUILTINS.map(({key, pref}) => ({
        key: `builtin:${key}`, label: BUILTIN_LABELS[key], kind: "builtin" as const, fixed: false,
        visible: prefs[pref], newField: false, prefField: pref,
      })),
    ];
    const props: SheetColumnOption[] = sheetDefinitions.value.map((item) => {
      const key = propertyKey(item.name);
      return {key, label: item.name, name: item.name, kind: "sheet", fixed: false,
        visible: prefs.properties[key] === true, newField: !(key in prefs.properties)};
    });
    return [...locked, ...optional, ...props];
  });

  // 保存按工作区 ID 排队；代次/ID 不匹配时跳过（切工作区不覆盖新工作区偏好）
  function scheduleSave(): Promise<void> {
    const current = deps.workspace.value;
    if (!current || !preferences.value) return Promise.resolve();
    const workspaceId = current.id;
    const generation = loadGeneration;
    const snapshot = clone(preferences.value);
    const run = saveQueue.then(async () => {
      if (generation !== loadGeneration || deps.workspace.value?.id !== workspaceId) return;
      const result = await saveSheetColumns(workspaceId, snapshot);
      if (generation !== loadGeneration || deps.workspace.value?.id !== workspaceId) return;
      if (result === null) return; // 旧桥缺方法：静默降级
      if (!result.ok) saveError.value = result.code === "SHEET_PREFERENCES_IO" ? SAVE_FAILED_MESSAGE : result.message;
    });
    saveQueue = run.catch(() => {});
    return run;
  }

  function setBuiltin(field: BuiltinPrefField, value: boolean) {
    const prefs = preferences.value;
    if (!prefs) return;
    preferences.value = {...prefs, [field]: value};
    void scheduleSave();
  }

  function setProperty(name: string, value: boolean) {
    const prefs = preferences.value;
    if (!prefs) return;
    const key = propertyKey(name);
    preferences.value = {...prefs, properties: {...prefs.properties, [key]: value}};
    void scheduleSave();
  }

  // 恢复默认仅影响当前图纸集：按当前定义重建首次默认并保存
  async function reset(): Promise<void> {
    const current = deps.workspace.value;
    if (!current) return;
    preferences.value = buildDefaults(sheetDefinitions.value);
    saveError.value = "";
    await scheduleSave();
  }

  // 工作区切换：先以默认填充避免空表，再异步读取存储覆盖；旧代次结果作废
  watch(() => deps.workspace.value?.id, (workspaceId) => {
    loadGeneration += 1;
    saveError.value = "";
    if (!workspaceId) {
      preferences.value = null;
      return;
    }
    preferences.value = buildDefaults(sheetDefinitions.value);
    void loadStored(workspaceId);
  });

  async function loadStored(workspaceId: string) {
    const generation = loadGeneration;
    const result = await loadSheetColumns(workspaceId);
    if (generation !== loadGeneration || deps.workspace.value?.id !== workspaceId) return;
    if (result === null) return; // 旧桥缺方法：保持默认降级
    if (!result.ok) {
      saveError.value = LOAD_FAILED_MESSAGE;
      return;
    }
    if (result.value !== null) preferences.value = result.value;
  }

  return {
    visibleColumns, preferences, newPropertyCount, saveError,
    columnOptions, setBuiltin, setProperty, reset,
  };
}
