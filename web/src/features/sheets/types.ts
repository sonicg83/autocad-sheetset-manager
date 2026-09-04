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
