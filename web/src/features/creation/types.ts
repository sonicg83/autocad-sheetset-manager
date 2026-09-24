// 创建域前端契约（PLAN-DM-036 Task 8）：创建草稿、标准候选与「可输入字段」输入模型的
// 前端类型。只描述形状与判别，不复制后端的属性求值、编号、DWG 命名与文件名校验规则——
// 预览与最终值一律以后端草稿/预览响应为准。
//
// 阶段枚举与后端 `domain/creation.CREATION_STEPS` 同口径；`standard` 只在尚未建立草稿
// （欢迎页入口的第一阶段）时出现，草稿建立后阶段由后端草稿保存（初值为 `project`）。
export type CreationStep = "standard" | "project" | "groups" | "review";

/** 固定的标准身份：`standard_id` 与发布版本在草稿初建时确定，此后不可改写。 */
export interface CreationIdentity {
  standardId: string;
  version: string;
}

/** 标准包内的受控模板资产候选；`kind` 取后端 `base-template` / `layout-template`。 */
export interface CreationAssetOption {
  asset_id: string;
  kind: string;
  label: string;
  /** 布局模板内可用布局名（图幅候选项）；基础模板为空。 */
  layouts: string[];
}

/** 创建标准候选；不可用时 `reasons` 说明为什么不能选（后端已本地化，原样呈现）。 */
export interface CreationStandardCandidate {
  standard_id: string;
  version: string;
  name: string;
  supported_cad_versions: string[];
  available: boolean;
  reasons: string[];
  asset_options: CreationAssetOption[];
}

/**
 * 一个图纸组的输入。`created_order` 是创建序（单调递增），数组顺序才是最终组序：
 * 重排只改数组顺序，不改变 `created_order`，「复制最近创建的组」取它最大的组。
 */
export interface CreationGroupState {
  group_id: string;
  created_order: number;
  title: string;
  count: number;
  base_asset_id: string;
  layout_asset_id: string;
  paper_layout: string;
  /** 只含可输入普通 sheet 属性；显式空串与遗漏键不同义。 */
  sheet_values: Record<string, string>;
}

/** 草稿当前状态（与后端 `CreationDraftResponse` 同形）。 */
export interface CreationDraftState {
  id: string;
  standard_id: string;
  standard_version: string;
  revision: number;
  step: CreationStep;
  target_path: string;
  sheetset_values: Record<string, string>;
  groups: CreationGroupState[];
}

/** 枚举候选项；`item_id` 是稳定身份，`value` 是用户可见取值。 */
export interface CreationEnumOption {
  item_id: string;
  value: string;
}

/** 可输入的普通属性（文本或枚举）；派生属性不在此模型内。 */
export interface CreationOrdinaryProperty {
  property_id: string;
  name: string;
  scope: "sheetset" | "sheet";
  kind: "text" | "enum";
  required: boolean;
  /** 标准默认值：只用于初建输入，用户主动清空后不得回填。 */
  default_value: string;
  options: CreationEnumOption[];
}

/** 派生属性：只读展示（创建阶段不提供输入，求值以后端预览为准）。 */
export interface CreationDerivedProperty {
  property_id: string;
  name: string;
  scope: string;
  kind: string;
}

/**
 * 从固定标准解析出的输入模型：可输入属性、派生属性与模板资产候选。
 * 资产候选直接取后端标准候选的 `asset_options`（已按可用性过滤），不自行推断。
 */
export interface CreationStandardInputs {
  identity: CreationIdentity;
  name: string;
  sheetset_properties: CreationOrdinaryProperty[];
  sheet_properties: CreationOrdinaryProperty[];
  derived_properties: CreationDerivedProperty[];
  asset_options: CreationAssetOption[];
}

/** 一条导入诊断：稳定错误码 + 工作表/行/列定位（列用列字母，与模板表头同口径）。 */
export interface CreationImportDiagnostic {
  code: string;
  message: string;
  sheet: string;
  row: number | null;
  column: string | null;
}

/** 图纸组即时提示的稳定问题码；文案由视图经语言包渲染，模型不持有用户可见文本。 */
export type CreationGroupIssueCode =
  | "title_empty"
  | "title_duplicate"
  | "count_invalid"
  | "base_asset_missing"
  | "layout_asset_missing"
  | "paper_layout_missing";

/** 图纸组局部更新：只接受可编辑字段。 */
export interface CreationGroupPatch {
  title?: string;
  count?: number;
  base_asset_id?: string;
  layout_asset_id?: string;
  paper_layout?: string;
  sheet_values?: Record<string, string>;
}

/** 批量修改的一次变更：显式赋值或显式清空（空输入不等于清空）。 */
export type CreationBatchChange = {kind: "set"; value: string} | {kind: "clear"};

/** 固定批量字段身份（其余批量字段是标准的可输入 sheet 属性 ID）。 */
export const CREATION_BATCH_COUNT = "count";
export const CREATION_BATCH_BASE = "base_asset_id";
export const CREATION_BATCH_LAYOUT = "layout_asset_id";
export const CREATION_BATCH_PAPER = "paper_layout";

/** 批量修改支持的字段种类：用于选择取值控件（数字 / 资产 / 图幅 / 文本 / 枚举）。 */
export type CreationBatchFieldKind =
  | "count"
  | "base-template"
  | "layout-template"
  | "paper-layout"
  | "text"
  | "enum";

// ---- 状态控制器注入端口与负载契约（store 只消费，URL/字段映射留在 `api/creation.ts`）----

/** 草稿保存负载；URL 与负载字段映射留在 `api/creation.ts`。 */
export interface CreationSaveInput {
  draftId: string;
  expectedRevision: number;
  step: CreationStep;
  targetPath: string;
  sheetsetValues: Record<string, string>;
  groups: CreationGroupState[];
}

/** 工作簿导入负载：`expectedRevision` 是乐观修订门禁。 */
export interface CreationImportInput {
  draftId: string;
  file: File;
  expectedRevision: number;
}

/**
 * 导入结果：整批被拒时不产生部分结果，诊断按工作表/行/列定位。
 * 用结果类型而不是异常，是因为「被拒」是导入的常规分支（草稿与预览必须零变化）。
 */
export type CreationImportOutcome =
  | {ok: true; draft: CreationDraftState}
  | {ok: false; message: string; diagnostics: CreationImportDiagnostic[]};

/**
 * 构造期同步起点：调用方已经持有草稿与已解析的标准输入模型时直接给出，省掉一次异步
 * 恢复（例如把刚建好的草稿交给 store，或测试替身装配固定起点）。真实 API 组合实现不
 * 提供该字段，store 以「尚未选择标准」的空态起步并等异步端点对齐。
 */
export interface CreationSeed {
  draft: CreationDraftState;
  standard: CreationStandardInputs;
}

/** 构造选项：项目目录名初值由调用方经语言包给出（store 不持有用户可见文案）。 */
export interface CreationStoreOptions {
  defaultFolderName?: string;
}

export interface CreationApi {
  seed?: CreationSeed | null;
  listStandards(): Promise<CreationStandardCandidate[]>;
  fetchStandardDocument(identity: CreationIdentity): Promise<Record<string, unknown>>;
  createDraft(identity: CreationIdentity): Promise<CreationDraftState>;
  fetchDraft(draftId: string): Promise<CreationDraftState>;
  saveDraft(input: CreationSaveInput): Promise<CreationDraftState>;
  deleteDraft(draftId: string): Promise<void>;
  templateUrl(draftId: string): string;
  importWorkbook(input: CreationImportInput): Promise<CreationImportOutcome>;
}

/** 向导输入状态：全部是普通值，组件直接读 `store.step` / `store.groups` 等字段。 */
export interface CreationState {
  /** 当前阶段；尚未建立草稿时为 `standard`（欢迎页入口的第一阶段）。 */
  step: CreationStep;
  candidates: CreationStandardCandidate[];
  candidatesPending: boolean;
  candidatesError: string;
  /** 固定标准的输入模型；未选择标准时为 null。 */
  standard: CreationStandardInputs | null;
  standardPending: boolean;
  draftId: string;
  revision: number;
  /** 界面上可编辑的上一级目录与项目目录名；两者合成完整最终路径。 */
  parentPath: string;
  folderName: string;
  sheetsetValues: Record<string, string>;
  groups: CreationGroupState[];
  selectedGroupIds: string[];
  /** 权威预览摘要；任何输入变更后为 null（第四阶段在 Task 9 接入）。 */
  previewDigest: string | null;
  /** 是否允许执行创建；预览摘要有效时才为真（第四阶段在 Task 9 接入）。 */
  canExecute: boolean;
  pending: boolean;
  importPending: boolean;
  importDiagnostics: CreationImportDiagnostic[];
  importMessage: string;
  error: string;
}

/**
 * 创建向导控制器：状态 + 派生值 + 动作。派生值（`targetPath`/`groupIssues`/`selectedGroups`）
 * 是纯函数而非 `computed` 字段——函数内读取的仍是同一份 reactive 状态，组件调用时依赖
 * 照常被追踪，同时避免 reactive 对象在自身初始化表达式里引用自己。
 */
