// 图纸页单表工作区公共类型（PLAN-DM-015 任务 1 建立，后续任务复用）。
// PropertyKey 名称按既有大小写匹配规则规范化；实际显示仍保留服务端原名。
// stamp 的 commandKey 是当前有效命令的规范化 JSON，不是发布摘要。
import type {ChangeCommand, Placement, Workspace} from '../../api/contracts';
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
  added: boolean;                 // 当前缓冲已加入草稿动作（保存失败重试不重复加入）
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

// 子集标题编辑（任务 6 接入真实表单，先占位保留同一上下文）
export type RenameEditContext = EditContextBase & {
  kind: "rename";
  original: {title: string};
  values: {title: string};
};

// 新增图纸/新建子集/批量编辑（任务 6/7 接入，先占位保留同一上下文）
export type InsertSheetEditContext = EditContextBase & {
  kind: "insert-sheet";
  original: null;
  values: null;
};
export type InsertSubsetEditContext = EditContextBase & {
  kind: "insert-subset";
  original: null;
  values: null;
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
