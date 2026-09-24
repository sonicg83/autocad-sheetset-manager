// 创建输入纯模型（PLAN-DM-036 Task 8）：标准文档 → 可输入字段模型、按组即时提示、
// 路径合成与批量修改。全部是无状态纯函数，不含 Vue、API 或组件依赖（与
// `features/standards/draftModel.ts` 同一组织方式），状态与请求编排留在 `store.ts`。
//
// 这里只做「帮用户定位」的即时提示与输入搬运：属性求值、编号、DWG 命名、目标目录状态
// 一律以后端草稿/预览响应为准，模型不复制这些最终规则。
import type {
  CreationAssetOption,
  CreationBatchChange,
  CreationDerivedProperty,
  CreationDraftState,
  CreationGroupIssueCode,
  CreationGroupPatch,
  CreationGroupState,
  CreationIdentity,
  CreationOrdinaryProperty,
  CreationStandardInputs,
} from "./types";
import {
  CREATION_BATCH_BASE,
  CREATION_BATCH_COUNT,
  CREATION_BATCH_LAYOUT,
  CREATION_BATCH_PAPER,
} from "./types";

/** 可输入普通属性种类（派生属性是 mapping/composition，不是输入项）。 */
const ORDINARY_KINDS = new Set(["text", "enum"]);
/** 图纸集与图纸组两级作用域（与后端 `PROPERTY_SCOPES` 同口径）。 */
const SHEETSET_SCOPE = "sheetset";
const SHEET_SCOPE = "sheet";
/** 标准包两种模板资产种类（与后端 `ASSET_KINDS` 同口径）。 */
export const BASE_TEMPLATE_KIND = "base-template";
export const LAYOUT_TEMPLATE_KIND = "layout-template";
/** 路径分隔符固定为 Windows 反斜杠；后端按 `[\\/]` 两种写法校验。 */
const PATH_SEPARATOR = "\\";

/** 读取标准文档里的属性数组；文档缺字段或类型不符时视为空，不抛出（后端已保证形状）。 */
function documentProperties(document: Record<string, unknown>): Record<string, unknown>[] {
  const value = document["properties"];
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> => typeof item === "object" && item !== null,
  );
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function ordinaryProperty(raw: Record<string, unknown>, scope: string): CreationOrdinaryProperty {
  const kind = asString(raw["kind"]);
  const options = Array.isArray(raw["enum_items"]) ? raw["enum_items"] : [];
  return {
    property_id: asString(raw["property_id"]),
    name: asString(raw["name"]),
    scope: scope === SHEET_SCOPE ? SHEET_SCOPE : SHEETSET_SCOPE,
    kind: kind === "enum" ? "enum" : "text",
    required: raw["required"] === true,
    default_value: asString(raw["default_value"]),
    options: options
      .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      .map(item => ({item_id: asString(item["item_id"]), value: asString(item["value"])})),
  };
}

function derivedProperty(raw: Record<string, unknown>, scope: string): CreationDerivedProperty {
  return {
    property_id: asString(raw["property_id"]),
    name: asString(raw["name"]),
    scope,
    kind: asString(raw["kind"]),
  };
}

/**
 * 标准文档 + 资产候选 → 创建输入模型。
 *
 * 资产候选由调用方传入后端标准候选的 `asset_options`（已按真实可用性过滤），
 * 模型不自行推断模板文件是否存在；派生属性只读展示，不产生输入项。
 */
export function creationStandardInputs(
  identity: CreationIdentity,
  name: string,
  document: Record<string, unknown>,
  assetOptions: CreationAssetOption[],
): CreationStandardInputs {
  const sheetset: CreationOrdinaryProperty[] = [];
  const sheet: CreationOrdinaryProperty[] = [];
  const derived: CreationDerivedProperty[] = [];
  for (const raw of documentProperties(document)) {
    const scope = asString(raw["scope"]);
    if (scope !== SHEETSET_SCOPE && scope !== SHEET_SCOPE) continue;
    if (ORDINARY_KINDS.has(asString(raw["kind"]))) {
      const property = ordinaryProperty(raw, scope);
      (scope === SHEET_SCOPE ? sheet : sheetset).push(property);
    } else {
      derived.push(derivedProperty(raw, scope));
    }
  }
  return {
    identity,
    name,
    sheetset_properties: sheetset,
    sheet_properties: sheet,
    derived_properties: derived,
    asset_options: assetOptions,
  };
}

/** 合成完整最终项目路径：上一级目录去掉尾部分隔符后拼接目录名。 */
export function creationTargetPath(parentPath: string, folderName: string): string {
  const parent = parentPath.trim().replace(/[\\/]+$/, "");
  const folder = folderName.trim();
  if (parent === "") return folder;
  if (folder === "") return parent;
  return `${parent}${PATH_SEPARATOR}${folder}`;
}

/** 完整最终路径 → 界面上的「上一级目录 + 目录名」两段（恢复草稿与导入后回填）。 */
export function creationPathParts(targetPath: string): {parentPath: string; folderName: string} {
  const trimmed = targetPath.trim().replace(/[\\/]+$/, "");
  const index = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  if (index === -1) return {parentPath: "", folderName: trimmed};
  return {parentPath: trimmed.slice(0, index), folderName: trimmed.slice(index + 1)};
}

/** 某个资产种类的候选项。 */
export function creationAssetOptions(
  standard: CreationStandardInputs | null,
  kind: string,
): CreationAssetOption[] {
  if (standard === null) return [];
  return standard.asset_options.filter(option => option.kind === kind);
}

/** 所选布局模板的可用布局名（图幅候选项）；未选或候选缺失时为空。 */
export function creationPaperLayouts(
  standard: CreationStandardInputs | null,
  layoutAssetId: string,
): string[] {
  return creationAssetOptions(standard, LAYOUT_TEMPLATE_KIND)
    .find(option => option.asset_id === layoutAssetId)?.layouts ?? [];
}

/** 某作用域可输入属性的标准默认值（`property_id → 默认值`）。 */
export function creationPropertyDefaults(
  standard: CreationStandardInputs | null,
  scope: "sheetset" | "sheet",
): Record<string, string> {
  if (standard === null) return {};
  const properties = scope === SHEET_SCOPE ? standard.sheet_properties : standard.sheetset_properties;
  const values: Record<string, string> = {};
  for (const property of properties) values[property.property_id] = property.default_value;
  return values;
}

/** 按标准顺序补齐可输入属性：缺键按标准默认值补，已有的显式空串原样保留。 */
export function creationWithPropertyDefaults(
  values: Record<string, string>,
  standard: CreationStandardInputs | null,
  scope: "sheetset" | "sheet",
): Record<string, string> {
  const defaults = creationPropertyDefaults(standard, scope);
  const merged: Record<string, string> = {};
  for (const [propertyId, fallback] of Object.entries(defaults)) {
    merged[propertyId] = Object.hasOwn(values, propertyId) ? values[propertyId] ?? "" : fallback;
  }
  // 草稿里存在而标准当前没有的属性不静默丢弃（后端保存时会以稳定码拒绝非可输入字段）
  for (const [propertyId, value] of Object.entries(values)) {
    if (!Object.hasOwn(merged, propertyId)) merged[propertyId] = value;
  }
  return merged;
}

/** 首个图纸组：标准默认值（sheet 普通属性默认值 + 首个基础/布局模板候选与图幅）。 */
export function creationDefaultGroup(
  standard: CreationStandardInputs | null,
  groupId: string,
  createdOrder: number,
): CreationGroupState {
  const base = creationAssetOptions(standard, BASE_TEMPLATE_KIND)[0]?.asset_id ?? "";
  const layout = creationAssetOptions(standard, LAYOUT_TEMPLATE_KIND)[0];
  return {
    group_id: groupId,
    created_order: createdOrder,
    title: "",
    count: 1,
    base_asset_id: base,
    layout_asset_id: layout?.asset_id ?? "",
    paper_layout: layout?.layouts[0] ?? "",
    sheet_values: creationPropertyDefaults(standard, SHEET_SCOPE),
  };
}

/** 复制一个组的全部可编辑输入（图名/张数/模板/图幅/其他 sheet 属性），新组取新身份。 */
export function creationCopiedGroup(
  source: CreationGroupState,
  groupId: string,
  createdOrder: number,
): CreationGroupState {
  return {
    group_id: groupId,
    created_order: createdOrder,
    title: source.title,
    count: source.count,
    base_asset_id: source.base_asset_id,
    layout_asset_id: source.layout_asset_id,
    paper_layout: source.paper_layout,
    sheet_values: {...source.sheet_values},
  };
}

/** 创建序最大的组（「最近创建」按 `created_order`，与数组顺序/重排无关）。 */
export function creationLatestGroup(groups: CreationGroupState[]): CreationGroupState | null {
  let latest: CreationGroupState | null = null;
  for (const group of groups) {
    if (latest === null || group.created_order > latest.created_order) latest = group;
  }
  return latest;
}

/** 下一个图纸组身份：创建序 +1 派生，保证与既有组身份不重复。 */
export function creationNextGroupId(groups: CreationGroupState[], createdOrder: number): string {
  const taken = new Set(groups.map(group => group.group_id));
  const base = `group-${createdOrder + 1}`;
  let candidate = base;
  let suffix = 2;
  while (taken.has(candidate)) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

/** 下一个创建序：单调递增，删除组后不复用（身份与顺序因此稳定）。 */
export function creationNextOrder(groups: CreationGroupState[]): number {
  let next = 0;
  for (const group of groups) next = Math.max(next, group.created_order + 1);
  return next;
}

/**
 * 按组即时提示（只帮定位，不是最终校验）：图名非空、图名唯一（去首尾空格 +
 * 大小写不敏感）、张数为正整数、模板与图幅来自当前标准的可用候选。
 * 同名重复的每个组都标错（不静默改名、不追加序号）。
 */
export function creationGroupIssues(
  groups: CreationGroupState[],
  standard: CreationStandardInputs | null,
): Record<string, CreationGroupIssueCode[]> {
  const titles = new Map<string, number>();
  for (const group of groups) {
    const key = group.title.trim().toLocaleLowerCase();
    if (key === "") continue;
    titles.set(key, (titles.get(key) ?? 0) + 1);
  }
  const issues: Record<string, CreationGroupIssueCode[]> = {};
  for (const group of groups) {
    const codes: CreationGroupIssueCode[] = [];
    const key = group.title.trim().toLocaleLowerCase();
    if (key === "") codes.push("title_empty");
    else if ((titles.get(key) ?? 0) > 1) codes.push("title_duplicate");
    if (!Number.isInteger(group.count) || group.count < 1) codes.push("count_invalid");
    if (
      !creationAssetOptions(standard, BASE_TEMPLATE_KIND).some(
        option => option.asset_id === group.base_asset_id,
      )
    ) {
      codes.push("base_asset_missing");
    }
    if (
      !creationAssetOptions(standard, LAYOUT_TEMPLATE_KIND).some(
        option => option.asset_id === group.layout_asset_id,
      )
    ) {
      codes.push("layout_asset_missing");
    } else if (!creationPaperLayouts(standard, group.layout_asset_id).includes(group.paper_layout)) {
      codes.push("paper_layout_missing");
    }
    if (codes.length > 0) issues[group.group_id] = codes;
  }
  return issues;
}

/**
 * 批量修改的一次应用结果：返回该组的局部更新，字段不支持（未知字段、张数被清空、
 * 张数取值非法）时返回 null 表示不改动这一组。清空是显式操作，空输入不会被当作清空。
 */
export function creationBatchPatch(
  group: CreationGroupState,
  standard: CreationStandardInputs | null,
  fieldId: string,
  change: CreationBatchChange,
): CreationGroupPatch | null {
  if (fieldId === CREATION_BATCH_COUNT) {
    if (change.kind === "clear") return null;
    const count = Number(change.value);
    if (!Number.isInteger(count) || count < 1) return null;
    return {count};
  }
  if (fieldId === CREATION_BATCH_BASE) {
    return {base_asset_id: change.kind === "clear" ? "" : change.value};
  }
  if (fieldId === CREATION_BATCH_LAYOUT) {
    // 只改被选中的字段：图幅是另一个字段，不静默跟随布局模板改写
    //（组合关系由即时提示与后端预览校验，不在批量里替用户决定）
    return {layout_asset_id: change.kind === "clear" ? "" : change.value};
  }
  if (fieldId === CREATION_BATCH_PAPER) {
    return {paper_layout: change.kind === "clear" ? "" : change.value};
  }
  const property = standard?.sheet_properties.find(item => item.property_id === fieldId);
  if (property === undefined) return null;
  return {sheet_values: {...group.sheet_values, [fieldId]: change.kind === "clear" ? "" : change.value}};
}

/** 批量修改当前值：选中组在该字段上的取值集合（用于「值不相同」判定）。 */
export function creationBatchValues(
  groups: CreationGroupState[],
  fieldId: string,
): string[] {
  return groups.map(group => {
    if (fieldId === CREATION_BATCH_COUNT) return String(group.count);
    if (fieldId === CREATION_BATCH_BASE) return group.base_asset_id;
    if (fieldId === CREATION_BATCH_LAYOUT) return group.layout_asset_id;
    if (fieldId === CREATION_BATCH_PAPER) return group.paper_layout;
    return group.sheet_values[fieldId] ?? "";
  });
}

/**
 * 草稿是否已有「用户输入」（导入前的全量覆盖提醒依据）：存在图纸组、已选上一级目录，
 * 或某个可输入属性已偏离标准默认值。刚建草稿时的标准默认值不算用户输入。
 */
export function creationHasInput(
  state: Pick<CreationDraftState, "target_path" | "sheetset_values" | "groups">,
  standard: CreationStandardInputs | null,
): boolean {
  if (state.groups.length > 0) return true;
  if (state.target_path.trim() !== "") return true;
  const defaults = creationPropertyDefaults(standard, SHEETSET_SCOPE);
  return Object.entries(state.sheetset_values).some(
    ([propertyId, value]) => value !== (defaults[propertyId] ?? ""),
  );
}
