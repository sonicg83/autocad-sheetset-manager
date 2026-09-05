// 图纸页单表工作区公共类型（PLAN-DM-015 任务 1 建立，后续任务复用）。
// PropertyKey 名称按既有大小写匹配规则规范化；实际显示仍保留服务端原名。
// stamp 的 commandKey 是当前有效命令的规范化 JSON，不是发布摘要。
import type {ChangeCommand, LayoutSourceType, Placement, Workspace} from '../../api/contracts';
export type SheetScope = {kind:'all'} | {kind:'subset';id:string};
export type ProjectionStamp = {
  workspaceId:string; revisionId:string; generation:number; commandKey:string;
};
export type PropertyKey = `sheet:${string}`;
export type ColumnPreferences = {
  schemaVersion:1; file:boolean; layout:boolean;
  subsetAll:boolean; subsetSingle:boolean;
  properties:Record<PropertyKey,boolean>;
};
export type SheetRef = {subsetId:string;sheetId:string;placement:Placement};
export type SubmitResult =
  | {ok:true}
  | {ok:false;message:string;fields?:Record<string,string>};
export type SubmitCommands = (
  commands:ChangeCommand[], label:string,
  category:'metadata'|'structural'
) => Promise<SubmitResult>;

// —— 活动编辑上下文（SPEC-DM-009 §6.1/§6.2，PLAN-DM-015 任务 5）——
// 唯一上下文为 null 或 sheet/rename/insert-sheet/insert-subset/bulk 联合分支之一，
// 单行编辑/新增表单/子集标题编辑/批量编辑共用，避免多个提交按钮争夺注意力。
// 每分支保留 workspaceId/revisionId/projection stamp/objectId/original/values/errors。
export type EditContextBase = {
  workspaceId: string;
  revisionId: string;
  stamp: ProjectionStamp | null;  // 打开编辑时的投影快照（结构命令前固定，表单提交用于参照重校验）
  objectId: string;               // 目标对象 ID（图纸/子集等）
  subject: string;                // 供提示语显示的主题（如「图纸 001」）
  errors: Record<string, string>; // 字段级错误（字段名 → 错误文案）
  summaryError: string;           // 无字段路径的错误摘要
  invalid: boolean;               // 基准刷新/对象消失后标记失效，禁止提交到新基准
};

// 单行属性编辑：original/values 为 custom_properties 完整副本，翻页/搜索只派生视图
export type PropertyEditContext = EditContextBase & {
  kind: "sheet";
  original: Record<string, string>;
  values: Record<string, string>;
  propertyNames: string[];  // 打开时可编辑属性定义名（原始大小写，含未显示列）
  page: number;             // 当前页（0 起）
  search: string;           // 属性名搜索
};

// 子集标题编辑（任务 6 接入真实表单）：仅缓冲标题，objectId 为编辑目标子集 ID；
// 全部图纸范围下先选择编辑对象（objectId 初始为空），不使用隐含的上次子集。
export type RenameEditContext = EditContextBase & {
  kind: "rename";
  original: {title: string};
  values: {title: string};
};

// 新增图纸表单（任务 6，SPEC-DM-009 §6.3）：目标子集/参照图纸（稳定对象 ID）/前后/数量/模板来源。
// 参照以 SheetRef 绑定当前草稿投影，目标变化后清除不属于新目标的参照；提交时重新核对映射。
export type InsertSheetEditContext = EditContextBase & {
  kind: "insert-sheet";
  original: null;
  values: null;
  targetSubsetId: string;       // 目标子集（单子集范围预填，全部范围必须明确选择）
  reference: SheetRef | null;   // 参照图纸（含 placement），空表示尚未选择
  count: string;                // 数量输入（字符串便于校验）
  sourceType: LayoutSourceType;
  sourceFile: string;
  sourceLayout: string;
  layoutOptions: string[];      // 布局读取状态（上下文代次保护，取消/切表单/切版本不回填旧响应）
  layoutLoading: boolean;
  layoutError: string;
  layoutManual: boolean;
  dirty: boolean;               // 是否已有输入（未提交输入保护三选一的判断依据）
};

// 新建子集表单（任务 6）：标题/参照子集/前后/初始图纸数/基础与布局模板（分开标注）。
// 空图纸集显示「创建首个子集」不展示不存在的参照，沿用首个序号为 1 的契约。
export type InsertSubsetEditContext = EditContextBase & {
  kind: "insert-subset";
  original: null;
  values: null;
  referenceSubsetId: string;    // 参照子集 ID；空图纸集时为 ""（首个子集，ordinal=1）
  placement: Placement;
  title: string;
  initialSheetCount: string;
  baseTemplateFile: string;     // 基础模板决定新 DWG 基底
  templateFile: string;         // 布局模板提供布局
  templateLayout: string;
  layoutOptions: string[];
  layoutLoading: boolean;
  layoutError: string;
  layoutManual: boolean;
  dirty: boolean;
};

export type BulkEditContext = EditContextBase & {
  kind: "bulk";
  original: null;
  values: null;
};

export type EditContext =
  | null
  | PropertyEditContext
  | RenameEditContext
  | InsertSheetEditContext
  | InsertSubsetEditContext
  | BulkEditContext;

// 未提交输入保护三选一（SPEC-DM-009 §6.2）：加入草稿后继续 / 放弃输入 / 留在此处
export type GuardChoice = "save" | "discard" | "stay";
