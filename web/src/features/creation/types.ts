// 创建域前端契约（PLAN-DM-036 Task 8，Task 9 追加权威预览与执行）：创建草稿、标准候选、
// 「可输入字段」输入模型、按组预览响应与执行入口的前端类型。只描述形状与判别，不复制
// 后端的属性求值、编号、DWG 命名与文件名校验规则——预览与最终值一律以后端预览响应为准。
//
// 阶段枚举与后端 `domain/creation.CREATION_STEPS` 同口径；`standard` 只在尚未建立草稿
// （欢迎页入口的第一阶段）时出现，草稿建立后阶段由后端草稿保存（初值为 `project`）。
import type {Job} from "../../api/contracts";

export type CreationStep = "standard" | "project" | "groups" | "review";

/** 固定的标准身份：`standard_id` 与发布版本在草稿初建时确定，此后不可改写。 */
export interface CreationIdentity {
  standardId: string;
  version: number;
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
  version: number;
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
  standard_version: number;
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

/** 一条创建预览诊断：稳定错误码 + 可定位的图纸组/属性（与后端预览响应同形）。 */
export interface CreationPreviewDiagnostic {
  code: string;
  message: string;
  /** `error` 为阻断错误，其余（如 `warning`）是非阻断提示。 */
  severity: string;
  /** 空串表示该诊断不针对具体图纸组。 */
  group_id: string;
  /** 空串表示该诊断不针对具体属性。 */
  property_id: string;
}

/** 逐张属性明细的一行：图号 + 该张实际值。 */
export interface CreationPreviewPropertyRow {
  number: string;
  value: string;
}

/** 一个属性的按组投影：首张实际值 + 完整逐张明细（供「…」模态）。 */
export interface CreationPreviewPropertyCell {
  property_id: string;
  first_value: string;
  sheets: CreationPreviewPropertyRow[];
}

/** 一张展开后的图纸：最终图号/标题/布局名与该张全部属性值。 */
export interface CreationPreviewSheet {
  number: string;
  title: string;
  layout_name: string;
  values: Record<string, string>;
}

/** 预览主表一行（一个图纸组一个主 DWG）。 */
export interface CreationPreviewGroup {
  group_id: string;
  created_order: number;
  title: string;
  /** 组内实际图号的首末值；不编号组是单个补零值（如 `00`）。 */
  number_range: string;
  /** 后端压缩后的图纸标题范围（如 `平面图 (一)-(三)`）。 */
  title_range: string;
  base_template: string;
  layout_template: string;
  paper_layout: string;
  /** 标准 DWG 命名模板对该组真实数据求值后的文件名（带 `.dwg`）。 */
  dwg_name: string;
  target_path: string;
  sheet_count: number;
  sheets: CreationPreviewSheet[];
  property_cells: Record<string, CreationPreviewPropertyCell>;
}

/** 当前标准的编号策略摘要（预览顶部展示，不在前端重算编号）。 */
export interface CreationPreviewNumbering {
  sequence_field: string;
  digits: number;
  start: number;
}

/** 当前有效设置里的标题后缀与不编号关键字。 */
export interface CreationPreviewSuffix {
  enabled: boolean;
  suffix_type: number;
  unnumbered_keywords: string[];
}

/** 权威预览响应：按组表格数据、逐张属性明细、定位诊断与 `preview_digest`。 */
export interface CreationPreview {
  draft_id: string;
  revision: number;
  standard_id: string;
  standard_version: number;
  standard_name: string;
  target_path: string;
  sheetset_values: Record<string, string>;
  group_count: number;
  sheet_count: number;
  dwg_count: number;
  numbering: CreationPreviewNumbering;
  suffix: CreationPreviewSuffix;
  diagnostics: CreationPreviewDiagnostic[];
  groups: CreationPreviewGroup[];
  /** 无阻断错误时为真；执行入口与按钮门禁都以它为准。 */
  executable: boolean;
  preview_digest: string;
}

/**
 * 预览会话状态（`previewSession.ts` 唯一读写）：摘要与可执行标志都来自后端响应，
 * 任何输入、标准身份或编号设置变化都必须使它们失效。
 */
export interface CreationPreviewSessionState {
  /** 权威预览响应；无有效预览时为 null。 */
  previewState: CreationPreview | null;
  /** 权威预览摘要；任何输入变更后为 null。 */
  previewDigest: string | null;
  /** 是否允许执行创建；仅当后端预览无阻断错误时为真。 */
  canExecute: boolean;
  /** 权威预览请求进行中。 */
  previewPending: boolean;
  /** 创建执行请求进行中（门禁在途重复提交）。 */
  executePending: boolean;
}

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
  /** 权威预览：后端重新加载标准、设置、草稿与目标状态后返回按组表格与摘要。 */
  previewDraft(draftId: string): Promise<CreationPreview>;
  /** 执行创建：只发送权威摘要，入队创建任务并返回任务状态。 */
  executeDraft(draftId: string, previewDigest: string): Promise<Job>;
}

/** 向导输入状态：全部是普通值，组件直接读 `store.step` / `store.groups` 等字段。 */
export interface CreationState extends CreationPreviewSessionState {
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
