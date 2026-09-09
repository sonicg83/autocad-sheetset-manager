// 参照对象 → 既有 ordinal/placement 命令映射（PLAN-DM-015 任务 6，SPEC-DM-009 §6.3）。
// 仅把稳定对象 ID 映射为既有序号/方向命令，不重新实现后端派生命名、不增加自由排序能力。
// 失效参照抛可见错误、不回退为 1；表单据此保留输入并要求重选，不静默替换对象。
// 非组件模块取唯一 i18n 实例的全局 t 渲染用户可见错误（组件内仍走 useI18n）。
import {i18n} from "../../i18n";
import type {Workspace} from "../../api/contracts";
import type {SheetRef} from "./types";

// 参照图纸 → 其在目标子集内的既有序号（1 起）。参照已删除/失效时抛错。
export function resolveSheetOrdinal(workspace: Workspace, ref: SheetRef): number {
  const subset = workspace.sheet_set.subsets.find((s) => s.id === ref.subsetId);
  const index = subset?.sheets.findIndex((s) => s.id === ref.sheetId) ?? -1;
  if (index < 0) throw new Error(i18n.global.t("sheets.errors.sheetRefStale"));
  return index + 1;
}

// 参照子集 → 其在图纸集内的既有序号（1 起）。空图纸集的首个子集不调用本函数（ordinal=1 契约）。
export function resolveSubsetOrdinal(workspace: Workspace, subsetId: string): number {
  const index = workspace.sheet_set.subsets.findIndex((s) => s.id === subsetId);
  if (index < 0) throw new Error(i18n.global.t("sheets.errors.subsetRefStale"));
  return index + 1;
}
