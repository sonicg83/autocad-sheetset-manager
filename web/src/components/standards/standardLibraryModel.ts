// 标准库视图模型（PLAN-DM-035 Task 8；PLAN-DM-041 Task 6）：
// 筛选、按 standard_id 归集、整数版本降序、空态判别与只读动作边界。
// 纯函数无 Vue 依赖，可单测；组件只装配状态并按完整身份键选择。
import type {StandardSummary} from "../../features/standards/types";

export interface StandardFilters {
  source: "all" | "official" | "user";
  status: "all" | "published" | "draft";
  query: string;
}

export const DEFAULT_FILTERS: StandardFilters = {source: "all", status: "all", query: ""};

/** 一个标准 ID 的归集组：组标题取当前筛选结果中最高整数版本的名称。 */
export interface StandardGroup {
  standard_id: string;
  /** 组标题：最高整数版本的名称；仅有草稿时用标准 ID。 */
  title: string;
  /** 已发布版本，整数降序（`v10` 排在 `v9` 之前）。 */
  versions: StandardSummary[];
  /** 组内草稿，按稳定 `draft_id` 升序。 */
  drafts: StandardSummary[];
}

export type LibraryState =
  | {kind: "empty-library"}
  | {kind: "empty-filter"}
  | {kind: "ready"; groups: StandardGroup[]};

/** 版本展示口径：界面加 `v` 前缀，契约字段保持裸整数。 */
export function formatStandardVersion(version: number): string {
  return `v${version}`;
}

/** 查询对标准 ID 与名称做大小写不敏感的包含匹配；来源/状态精确过滤。 */
export function filterStandardList(items: StandardSummary[], filters: StandardFilters): StandardSummary[] {
  const query = filters.query.trim().toLowerCase();
  return items.filter(item => {
    if (filters.source !== "all" && item.source !== filters.source) return false;
    if (filters.status !== "all" && item.status !== filters.status) return false;
    if (query && !item.standard_id.toLowerCase().includes(query) && !item.name.toLowerCase().includes(query)) return false;
    return true;
  });
}

/** 按 `standard_id` 归集：组内版本整数降序、草稿按 `draft_id` 升序，组序沿用首次出现顺序。 */
export function groupStandardList(items: StandardSummary[], filters: StandardFilters): StandardGroup[] {
  const filtered = filterStandardList(items, filters);
  const groups = new Map<string, StandardGroup>();
  for (const item of filtered) {
    const existing = groups.get(item.standard_id);
    if (existing === undefined) {
      groups.set(item.standard_id, {standard_id: item.standard_id, title: item.standard_id, versions: [], drafts: []});
    }
    const group = groups.get(item.standard_id);
    if (group === undefined) continue;
    if (item.status === "published") group.versions.push(item);
    else group.drafts.push(item);
  }
  for (const group of groups.values()) {
    // 整数降序：字符串比较会把 v10 排到 v9 之后（本轮必须避免的缺陷）。
    group.versions.sort((left, right) => (right.version ?? 0) - (left.version ?? 0));
    group.drafts.sort((left, right) => String(left.draft_id ?? "").localeCompare(String(right.draft_id ?? "")));
    const highest = group.versions[0];
    group.title = highest === undefined ? group.standard_id : highest.name;
  }
  return [...groups.values()];
}

export function buildLibraryState(items: StandardSummary[], filters: StandardFilters): LibraryState {
  if (items.length === 0) return {kind: "empty-library"};
  const groups = groupStandardList(items, filters);
  if (groups.length === 0) return {kind: "empty-filter"};
  return {kind: "ready", groups};
}

/** 只读边界稳定原因码；文案由视图经语言包渲染（模型不持有用户可见文本）。 */
export type ReadOnlyReason = "official" | "published";

export interface DetailActions {
  canEdit: boolean;
  canDelete: boolean;
  canDerive: boolean;
  canExport: boolean;
  /** 只读边界可见原因码；可编辑时为 null。 */
  readOnlyReason: ReadOnlyReason | null;
}

// 只读边界（SPEC-DM-016 §5）：官方标准与已发布版本只读；用户草稿可维护。
// 只读边界不静默消失：动作不可用时附可见原因，由视图渲染为可读说明。
export function detailActions(summary: StandardSummary): DetailActions {
  if (summary.status === "draft") {
    return {canEdit: true, canDelete: true, canDerive: false, canExport: false, readOnlyReason: null};
  }
  if (summary.source === "official") {
    return {canEdit: false, canDelete: false, canDerive: true, canExport: true, readOnlyReason: "official"};
  }
  return {canEdit: false, canDelete: false, canDerive: true, canExport: true, readOnlyReason: "published"};
}

export interface VersionEntry {
  version: number;
  source: "official" | "user";
  name: string;
}

/** 同一标准 ID 的已发布版本历史（草稿无版本号，不进入历史），整数降序。 */
export function versionHistory(standardId: string, items: StandardSummary[]): VersionEntry[] {
  return items
    .filter(item => item.status === "published" && item.standard_id === standardId)
    .map(item => ({version: item.version ?? 0, source: item.source, name: item.name}))
    .sort((left, right) => right.version - left.version);
}
