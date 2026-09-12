// 输出列兼容性判定（SPEC-DM-012 §7.2 区域 4；PLAN-DM-023 Task 4）。
// 徽标（输出列卡头）与状态带（摘要正文）必须来自同一处判定，否则会出现
// “卡头说可以导出、正文说阻断”的分裂。这里只做呈现层归一：阻断/警告/检查中/失败
// 的判定全部依据服务端诊断与预览状态，不重新实现后端校验规则。
//
// PLAN-DM-025 Task 8：判定只消费可选的校验反馈（预览诊断与状态），不再需要整个页面
// 控制器——设置中心的 custom 面板没有工作区与预览，因而不传反馈、不显示徽标与摘要，
// 也不伪造一份空诊断。
import type {CatalogDiagnostic} from "../../composables/useSheetCatalogSettings";
import type {SheetCatalogValidationFeedback} from "../../composables/useSheetCatalogSettings";

export type CompatibilityTone = "checking" | "ok" | "warning" | "error" | "failed";

export interface CompatibilityView {
  tone: CompatibilityTone;
  errors: CatalogDiagnostic[];
  warnings: CatalogDiagnostic[];
}

export function catalogCompatibility(feedback: SheetCatalogValidationFeedback): CompatibilityView {
  const preview = feedback.preview.value;
  const errors = preview?.errors ?? [];
  const warnings = preview?.warnings ?? [];
  let tone: CompatibilityTone = "ok";
  if (feedback.previewStatus.value === "failed") tone = "failed";
  else if (errors.length > 0) tone = "error";
  else if (feedback.previewStatus.value === "pending" || preview === null) tone = "checking";
  else if (warnings.length > 0) tone = "warning";
  return {tone, errors, warnings};
}
