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

/** 按来源和状态过滤，并在名称与标准 UUID 中搜索；保留服务端顺序。 */
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

/** 格式固定为 YYYY/MM/DD HH:mm；日期字段使用系统时区，分隔符由本函数控制。 */
export function formatPublishedAt(timestamp: number | null | undefined): string | null {
  if (typeof timestamp !== "number" || !Number.isFinite(timestamp)) return null;
  const parts = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  const values = new Map(parts.map(part => [part.type, part.value]));
  const year = values.get("year");
  const month = values.get("month");
  const day = values.get("day");
  const hour = values.get("hour");
  const minute = values.get("minute");
  if (!year || !month || !day || !hour || !minute) return null;
  return `${year}/${month}/${day} ${hour}:${minute}`;
}

export type ReadOnlyReason = "official" | "published";

export interface DetailActions {
  canEdit: boolean;
  canDelete: boolean;
  canDerive: boolean;
  canExport: boolean;
  readOnlyReason: ReadOnlyReason | null;
}

/** 官方标准保持只读；用户已发布标准可删除与派生，草稿可编辑与删除。 */
export function detailActions(summary: StandardSummary): DetailActions {
  if (summary.status === "draft") {
    return {canEdit: true, canDelete: true, canDerive: false, canExport: false, readOnlyReason: null};
  }
  if (summary.source === "official") {
    return {canEdit: false, canDelete: false, canDerive: true, canExport: true, readOnlyReason: "official"};
  }
  if (summary.published_at === null) {
    return {canEdit: false, canDelete: false, canDerive: false, canExport: false, readOnlyReason: "published"};
  }
  return {canEdit: false, canDelete: true, canDerive: true, canExport: true, readOnlyReason: "published"};
}
