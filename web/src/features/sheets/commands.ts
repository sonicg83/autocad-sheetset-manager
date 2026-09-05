// 参照对象 → 既有 ordinal/placement 命令映射（PLAN-DM-015 任务 6，SPEC-DM-009 §6.3）。
// 仅把稳定对象 ID 映射为既有序号/方向命令，不重新实现后端派生命名、不增加自由排序能力。
// 失效参照抛可见错误、不回退为 1；表单据此保留输入并要求重选，不静默替换对象。
import type {Workspace} from "../../api/contracts";
import type {SheetRef} from "./types";

// 参照图纸 → 其在目标子集内的既有序号（1 起）。参照已删除/失效时抛错。
export function resolveSheetOrdinal(workspace: Workspace, ref: SheetRef): number {
  const subset = workspace.sheet_set.subsets.find((s) => s.id === ref.subsetId);
  const index = subset?.sheets.findIndex((s) => s.id === ref.sheetId) ?? -1;
  if (index < 0) throw new Error("参照图纸已失效，请重新选择");
  return index + 1;
}

// 参照子集 → 其在图纸集内的既有序号（1 起）。空图纸集的首个子集不调用本函数（ordinal=1 契约）。
export function resolveSubsetOrdinal(workspace: Workspace, subsetId: string): number {
  const index = workspace.sheet_set.subsets.findIndex((s) => s.id === subsetId);
  if (index < 0) throw new Error("参照子集已失效，请重新选择");
  return index + 1;
}
