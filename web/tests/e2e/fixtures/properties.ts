// 属性页共享 e2e 夹具（PLAN-DM-016 任务 6，P-08）：36 个定义（33 图纸集 + 3 图纸）、
// 33 个真实存在于定义中的图纸集值、3 个 sheet 定义（含与图纸集同名的跨作用域字段）。
// 覆盖空值、长值、拉丁字段名；错误响应经草稿 PUT 失败注入（字段级错误供错误摘要消费）。
// 全部路径、单位、人名与数值均为虚构，不含真实客户路径或工程内容。
// 基于图纸页夹具（假壳/持久草稿/跨工作区）叠加属性定义与图纸集值。
import type {Page} from "@playwright/test";
import type {Workspace} from "../../../src/api/contracts";
import {installSheetsFixture} from "./sheets";

export type DraftSaveFailure = {code: string; message: string; fields?: Record<string, string>};

export type PropertiesFixtureOptions = {
  // 定义总数（图纸集定义 + 3 个 sheet 定义），默认 36；sheetset 定义数量 = count - 3
  definitionsCount?: number;
  // 无图纸集自定义属性（仍展示名称与新增 sheetset 字段入口）
  noValues?: boolean;
  // 覆盖图纸集值（键必须存在于 sheetset 定义中；默认 33 项完整值）
  values?: Record<string, string>;
  // 预置持久草稿（例如 update_sheet_set 待写入批次，演示 pending 三态）
  initialDraft?: unknown;
  // 草稿 PUT 失败注入（提交失败/字段错误/DRAFT_CONFLICT），返回 null 走正常保存
  failDraftSave?: (body: unknown) => DraftSaveFailure | null;
  // 草稿 PUT 请求体捕获
  onDraftPut?: (body: unknown) => void;
  // 跨工作区隔离（切工作区重置用例），复用图纸页夹具能力
  secondWorkspace?: {dstPath: string; id?: string};
  // 主题（经 localStorage 预置，与既有属性页 spec 一致）
  theme?: "light" | "dark";
};

// 33 项图纸集自定义属性（顺序即服务端映射顺序）：含空值（备注/审图日期）、长值（设计说明）、拉丁名
export const SHEETSET_ENTRIES: Array<[string, string]> = [
  ["项目编号", "GC-2026-007"],
  ["工程名称", "城东安置房一期"],
  ["设计阶段", "施工图"],
  ["出图日期", "2026-09-01"],
  ["版本号", "B"],
  ["建设单位", "城东建设开发有限公司"],
  ["设计单位", "山水建筑设计院"],
  ["审图日期", ""],
  ["备注", ""],
  ["校对人", "王校"],
  ["审核人", "李审"],
  ["工程地点", "城东新区纬三路"],
  ["总建筑面积", "128000.50"],
  ["地上层数", "18"],
  ["地下层数", "2"],
  ["建筑高度", "54.30"],
  ["耐火等级", "一级"],
  ["抗震设防", "7度"],
  ["结构类型", "剪力墙"],
  ["基础形式", "桩基"],
  ["人防等级", "核6级"],
  ["屋面防水", "一级"],
  ["节能标准", "75%"],
  ["PhotoCount", "42"],
  ["Phase", "phase 2"],
  ["UnitCode", "unit-a"],
  ["RevMark", "rev007"],
  ["SheetScale", "1:150"],
  ["DummyField", "占位"],
  ["工程代号", "DJ"],
  ["绿化率", "35%"],
  ["车位数量", "860"],
  ["设计说明", "本工程为虚构数据，仅用于属性页分区工作区共享夹具的长值展示、展开编辑与错误响应测试覆盖，全部文字依次罗列以验证长文本不被截断也不丢失内容。"],
];

export const SHEETSET_VALUES: Record<string, string> = Object.fromEntries(SHEETSET_ENTRIES);

// 图纸集默认值：与前 33 项 sheetset 定义一一对应（部分留空、末项长默认值）
function sheetsetDefaultValue(index: number, value: string): string {
  if (index % 7 === 3) return "";                       // 少量空默认值
  if (value.length > 40) return `默认${value.slice(0, 12)}…（长默认值）`;
  return value;
}

/** 构建 36 个定义：`count - 3` 个 sheetset 定义（与值同名同序）+ 3 个 sheet 定义（含同名跨作用域「工程名称」）；count<=0 返回空。 */
export function buildPropertyDefinitions(count = 36): NonNullable<Workspace["sheet_set"]["property_definitions"]> {
  if (count <= 0) return [];
  const sheetsetCount = Math.max(count - 3, 0);
  const sheetset = SHEETSET_ENTRIES.slice(0, sheetsetCount).map(([name, value], index) => ({
    type: "sheetset" as const,
    name,
    default_value: sheetsetDefaultValue(index, value),
  }));
  const sheet = [
    {type: "sheet" as const, name: "工程名称", default_value: "建筑"}, // 与 sheetset「工程名称」同名跨作用域
    {type: "sheet" as const, name: "图幅", default_value: "A1"},
    {type: "sheet" as const, name: "比例", default_value: "1:100"},
  ];
  return [...sheetset, ...sheet];
}

// 预置待写入草稿：把「项目编号」改为草稿值（与正式基准不同 → pending），其余值保持基准原样
export function pendingDraft(): unknown {
  const values = {...SHEETSET_VALUES, 项目编号: "GC-2026-DRAFT"};
  return {
    schema_version: 1,
    workspace_id: "workspace-1",
    base_revision_id: "revision-1",
    repair_status: "VALID",
    version: 1,
    cursor: 1,
    actions: [{id: "prop-pending-1", kind: "command_batch", label: "更新图纸集", commands: [{type: "update_sheet_set", name: "虚构图纸集", custom_properties: values}]}],
  };
}

export async function openProperties(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await page.getByLabel("图纸集名称", {exact: true}).waitFor({state: "visible"});
}

// 安装属性页共享夹具：假壳 + 打开/刷新路由返回带定义与图纸集值的工作区；返回捕获草稿 PUT 的数组
export async function installPropertiesFixture(page: Page, options: PropertiesFixtureOptions = {}): Promise<{workspace: Workspace; draftBodies: unknown[]}> {
  const draftBodies: unknown[] = [];
  if (options.theme) await page.addInitScript((t) => localStorage.setItem("dst-manager-theme", t), options.theme);
  const {workspace} = await installSheetsFixture(page, {
    initialDraft: options.initialDraft,
    secondWorkspace: options.secondWorkspace,
    failDraftSave: options.failDraftSave,
    onDraftPut: (body) => { draftBodies.push(body); options.onDraftPut?.(body); },
  });
  const modified = JSON.parse(JSON.stringify(workspace)) as Workspace;
  modified.sheet_set.property_definitions = buildPropertyDefinitions(options.definitionsCount ?? 36);
  modified.sheet_set.custom_properties = options.values ?? (options.noValues ? {} : {...SHEETSET_VALUES});
  // 后注册的路由优先：打开/刷新均返回带属性定义与图纸集值的工作区
  await page.route("**/api/workspaces/open", (route) => route.fulfill({json: modified}));
  await page.route("**/api/workspaces/workspace-1", (route) => route.fulfill({json: modified}));
  return {workspace: modified, draftBodies};
}
