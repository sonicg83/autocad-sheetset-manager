// 创建预览纯模型（PLAN-DM-036 Task 9）：按组属性单元格摘要、动态属性列与诊断定位。
// 全部是无状态纯函数，不含 Vue、API 或组件依赖（与 `inputModel.ts` 同一组织方式）。
//
// 这里只做「把后端权威预览投影成表格」：图号范围、紧凑标题、DWG 文件名、逐张属性值与
// 可执行判定都原样来自预览响应，模型不推算、不补默认值、不猜序号。
import type {
  CreationPreview,
  CreationPreviewDiagnostic,
  CreationPreviewPropertyRow,
  CreationPreviewGroup,
  CreationStandardInputs,
  CreationStep,
} from "./types";

/** 一个按组属性单元格的摘要。 */
export interface CreationSheetValuesSummary {
  /** 第一张图纸的实际值（空串表示该属性首张为空）。 */
  text: string;
  /** 组内取值不一致时为真：此时显示首张值 + 可点击的「…」。 */
  showDetails: boolean;
  /** 按组内顺序的全部图纸行（「…」模态使用）。 */
  rows: CreationPreviewPropertyRow[];
}

/** 预览主表里一个动态 sheet 属性列。 */
export interface CreationPreviewPropertyColumn {
  property_id: string;
  /** 标准里的属性名；标准不再声明该属性时回退属性 ID（列不静默消失）。 */
  label: string;
}

/** 组内固定控件的判别（行内顺序：图名｜张数｜基础模板｜布局模板｜图幅）。 */
export type CreationGroupField = "title" | "count" | "base" | "layout" | "paper" | "";

/** 诊断的跳转位置：要回到哪个阶段，以及要定位到哪个组/属性/组内控件。 */
export interface CreationPreviewTarget {
  step: CreationStep;
  /** 空串表示不针对具体图纸组。 */
  groupId: string;
  /** 空串表示不针对具体属性（`project` 阶段此时定位项目路径字段）。 */
  propertyId: string;
  /**
   * 组内要聚焦的固定控件；空串表示没有更具体的控件目标（属性列或整行）。没有它时
   * 定位只能落在行内第一个控件（图名），模板/图幅类诊断会指错控件。
   */
  groupField: CreationGroupField;
}

/**
 * 按组属性单元格摘要：组内全同直接显示值，不一致时显示第一张实际值并给出「…」。
 * 首张为空时 `text` 为空串——占位文案（「（空）」）由视图经语言包渲染，模型不持有文本。
 */
export function summarizeSheetValues(
  rows: readonly CreationPreviewPropertyRow[],
): CreationSheetValuesSummary {
  const first = rows[0]?.value ?? "";
  return {
    text: first,
    showDetails: rows.some(row => row.value !== first),
    rows: [...rows],
  };
}

/**
 * 动态 sheet 属性列：列身份与顺序取后端预览的 `property_cells` 键（标准文档顺序），
 * 名称取当前标准的属性定义；标准未声明的属性以属性 ID 兜底显示，不静默丢列。
 */
export function previewPropertyColumns(
  preview: CreationPreview | null,
  standard: CreationStandardInputs | null,
): CreationPreviewPropertyColumn[] {
  if (preview === null) return [];
  const labels = previewPropertyLabels(standard);
  const propertyIds: string[] = [];
  const seen = new Set<string>();
  for (const group of preview.groups) {
    for (const propertyId of Object.keys(group.property_cells)) {
      if (seen.has(propertyId)) continue;
      seen.add(propertyId);
      propertyIds.push(propertyId);
    }
  }
  return propertyIds.map(propertyId => ({
    property_id: propertyId,
    label: labels.get(propertyId) ?? propertyId,
  }));
}

/** 标准里的属性名映射：可输入 sheet 属性 + 派生 sheet 属性（两者都出现在预览列里）。 */
function previewPropertyLabels(standard: CreationStandardInputs | null): Map<string, string> {
  const labels = new Map<string, string>();
  if (standard === null) return labels;
  for (const property of standard.sheet_properties) {
    labels.set(property.property_id, property.name === "" ? property.property_id : property.name);
  }
  for (const property of standard.derived_properties) {
    if (property.scope !== "sheet") continue;
    labels.set(property.property_id, property.name === "" ? property.property_id : property.name);
  }
  return labels;
}

/** 组内某一属性单元格的摘要；后端没有该属性时返回空摘要（视图据此渲染空单元格）。 */
export function groupSheetValues(
  group: CreationPreviewGroup,
  propertyId: string,
): CreationSheetValuesSummary {
  return summarizeSheetValues(group.property_cells[propertyId]?.sheets ?? []);
}

/** 组内固定控件诊断码 → 控件（`CREATION_ASSET_INVALID` 同时覆盖两种模板资产，另判）。 */
const GROUP_FIELD_BY_CODE: Readonly<Record<string, CreationGroupField>> = {
  CREATION_GROUP_TITLE_EMPTY: "title",
  CREATION_GROUP_TITLE_DUPLICATE: "title",
  CREATION_GROUP_COUNT_INVALID: "count",
  CREATION_PAPER_LAYOUT_INVALID: "paper",
};

/**
 * 组内固定控件：属性诊断定位属性列（空串），其余按诊断码。基础模板与布局模板资产共用
 * `CREATION_ASSET_INVALID`，因此用该组已解析的模板路径判别到底缺的是哪一个（路径为空串
 * 即该资产未解析成功；两者都缺时先指向基础模板）。
 */
function groupFieldOf(
  diagnostic: CreationPreviewDiagnostic,
  group: CreationPreviewGroup | null,
): CreationGroupField {
  if (diagnostic.code === "CREATION_ASSET_INVALID") {
    if (group === null || group.base_template === "") return "base";
    return "layout";
  }
  return GROUP_FIELD_BY_CODE[diagnostic.code] ?? "";
}

/**
 * 诊断的跳转位置：
 * - 带图纸组 → 图纸组阶段的那一行（带属性时定位到该属性的控件，否则按码定位固定控件）；
 * - 带属性（图纸集作用域）→ 项目信息阶段的该字段；
 * - 项目路径诊断 → 项目信息阶段的路径字段；
 * - 空图纸组 → 图纸组阶段；标准资产文件不可用 → 选择标准阶段；
 * - 其余（如布局名重复等没有可修改输入的诊断）返回 null：只呈现消息，不给误导性的跳转。
 *
 * `group` 是该诊断所属的预览组（调用方按 `group_id` 查找），仅用于区分两种模板资产。
 */
export function previewDiagnosticTarget(
  diagnostic: CreationPreviewDiagnostic,
  group: CreationPreviewGroup | null = null,
): CreationPreviewTarget | null {
  if (diagnostic.group_id !== "") {
    return {
      step: "groups",
      groupId: diagnostic.group_id,
      propertyId: diagnostic.property_id,
      groupField: diagnostic.property_id === "" ? groupFieldOf(diagnostic, group) : "",
    };
  }
  if (diagnostic.property_id !== "") {
    return {step: "project", groupId: "", propertyId: diagnostic.property_id, groupField: ""};
  }
  if (diagnostic.code.startsWith("CREATION_TARGET_PATH")) {
    return {step: "project", groupId: "", propertyId: "", groupField: ""};
  }
  if (diagnostic.code === "CREATION_GROUPS_EMPTY") {
    return {step: "groups", groupId: "", propertyId: "", groupField: ""};
  }
  if (diagnostic.code === "CREATION_ASSET_FILE_MISSING") {
    return {step: "standard", groupId: "", propertyId: "", groupField: ""};
  }
  return null;
}

/** 阻断错误与非阻断提示的分区（诊断区只按后端 `severity` 分区，不重新判定严重性）。 */
export function splitPreviewDiagnostics(diagnostics: readonly CreationPreviewDiagnostic[]): {
  errors: CreationPreviewDiagnostic[];
  notices: CreationPreviewDiagnostic[];
} {
  return {
    errors: diagnostics.filter(item => item.severity === "error"),
    notices: diagnostics.filter(item => item.severity !== "error"),
  };
}
