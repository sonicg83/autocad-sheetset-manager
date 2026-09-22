// 标准库视图模型（PLAN-DM-035 Task 8）：筛选、空态判别、只读动作边界与版本分组。
// 纯函数无 Vue 依赖，可单测；组件只装配状态。
import type {StandardSummary} from "../../features/standards/types";

export interface StandardFilters {
  source: "all" | "official" | "user";
  status: "all" | "published" | "draft";
  query: string;
}

export const DEFAULT_FILTERS: StandardFilters = {source: "all", status: "all", query: ""};

export type LibraryState =
  | {kind: "empty-library"}
  | {kind: "empty-filter"}
  | {kind: "ready"; items: StandardSummary[]};

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

export function buildLibraryState(items: StandardSummary[], filters: StandardFilters): LibraryState {
  if (items.length === 0) return {kind: "empty-library"};
  const filtered = filterStandardList(items, filters);
  if (filtered.length === 0) return {kind: "empty-filter"};
  return {kind: "ready", items: filtered};
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
  version: string;
  source: "official" | "user";
}

/** 同一标准 ID 的已发布版本历史（草稿无版本号，不进入历史）。 */
export function versionHistory(summary: StandardSummary, items: StandardSummary[]): VersionEntry[] {
  return items
    .filter(item => item.status === "published" && item.standard_id === summary.standard_id)
    .sort((left, right) => right.version.localeCompare(left.version))
    .map(item => ({version: item.version, source: item.source}));
}
