// PLAN-DM-016 任务 1：属性三基准模型契约测试（SPEC-DM-010 §5.2/§5.3）。
// 纯函数验证，不依赖页面：33 项图纸集值夹具断言三基准比较（正式基准/草稿投影/当前输入）、
// 名称与「工程名称」身份独立、空串/空格/前导零原样保留、三种搜索模式、仅看修改、
// 活动字段暂留的隐藏计数口径，以及失效字段阻断命令构造。
import {expect, test} from "@playwright/test";
import {
  buildSheetSetCommand,
  createPropertyBuffer,
  filterValueKeys,
  valueStatus,
} from "../../src/features/properties/model";
import type {Workspace} from "../../src/api/contracts";
import type {PropertyBuffer, ValueKey} from "../../src/features/properties/types";

// 33 项虚构图纸集属性值（SPEC-DM-010 P-03）：包含空串、仅空格、前导零与大小写混合值。
const VALUE_ENTRIES: Array<[string, string]> = [
  ["工程名称", "城东安置房一期"],
  ["项目编号", "GC-2026-007"],
  ["设计阶段", "施工图"],
  ["出图日期", "2026-09-01"],
  ["版本号", " "],
  ["备注", ""],
  ["比例", "1:100"],
  ["建设单位", "城东建设开发有限公司"],
  ["设计单位", "山水建筑设计院"],
  ["监理单位", "恒正工程监理"],
  ["施工单位", "宏远建设集团"],
  ["地勘单位", "岩土地质勘察"],
  ["图纸深度", "深"],
  ["保密等级", "内部"],
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
  ["LongNote", "本工程为虚构数据，仅用于契约测试覆盖，不对应任何真实项目。"],
];

function valuesFixture(): Record<string, string> {
  return Object.fromEntries(VALUE_ENTRIES);
}

function fakeWorkspace(name: string, values: Record<string, string>): Workspace {
  return {sheet_set: {name, custom_properties: values}} as unknown as Workspace;
}

// 三基准夹具：
// - base：正式基准；
// - draft：草稿投影（工程名称、项目编号 相对 base 已改 → 待写入）；
// - input：当前输入（工程名称 相对 draft 又改 → 未加入草稿；版本号 仅相对 draft 改）。
function triple(): {base: PropertyBuffer; draft: PropertyBuffer; input: PropertyBuffer} {
  const base: PropertyBuffer = {name: "城东安置房一期", values: valuesFixture()};
  const draft: PropertyBuffer = {
    name: "城东安置房一期",
    values: {...base.values, 工程名称: "城东安置房二期", 项目编号: "GC-2026-008"},
  };
  const input: PropertyBuffer = {
    name: "城东安置房一期",
    values: {...draft.values, 工程名称: "城东二期安置房", 版本号: "B"},
  };
  return {base, draft, input};
}

function statusOfTriple(noInvalid: ReadonlySet<ValueKey> = new Set()) {
  const {base, draft, input} = triple();
  return (key: ValueKey) => valueStatus(base, draft, input, key, noInvalid);
}

test("createPropertyBuffer 快照名称与完整值映射，保留原始顺序与 33 项", () => {
  const workspace = fakeWorkspace("城东安置房一期", valuesFixture());
  const buffer = createPropertyBuffer(workspace);
  expect(Object.keys(buffer.values)).toHaveLength(33);
  expect(Object.keys(buffer.values)).toEqual(VALUE_ENTRIES.map(([name]) => name));
  expect(buffer.values["备注"]).toBe("");
  expect(buffer.values["版本号"]).toBe(" ");
  expect(buffer.values["项目编号"]).toBe("GC-2026-007");
  // 快照语义：改动缓冲不得污染 workspace props（§2「直接修改 props 导致基准污染」风险控制）
  buffer.values["备注"] = "被篡改";
  buffer.name = "被篡改";
  expect(workspace.sheet_set.custom_properties["备注"]).toBe("");
  expect(workspace.sheet_set.name).toBe("城东安置房一期");
});

test("名称与工程名称是不同身份，改名不影响工程名称字段状态", () => {
  const {base, draft, input} = triple();
  // 仅名称被编辑：@name 未加入草稿，工程名称字段不受影响
  expect(valueStatus(base, draft, {...input, name: "城东安置房四期"}, "@name", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
  expect(valueStatus(base, draft, {...input, name: "城东安置房四期"}, "sheetset:工程名称", new Set()))
    .toEqual({dirty: true, pending: true, invalid: false});
  // 同名值也不互相覆盖：base.name 与 base.values["工程名称"] 相同时，两 key 状态独立
  const same = fakeWorkspace("同值", {"工程名称": "同值"});
  const buffer = createPropertyBuffer(same);
  const edited = {...buffer, values: {...buffer.values, "工程名称": "改了"}};
  expect(valueStatus(buffer, buffer, edited, "@name", new Set()))
    .toEqual({dirty: false, pending: false, invalid: false});
  expect(valueStatus(buffer, buffer, edited, "sheetset:工程名称", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
});

test("dirty 与 pending 可并存，且各自可单独出现", () => {
  const {base, draft, input} = triple();
  // 计划 Step 1 verbatim：输入不同于草稿、草稿不同于基准 → 两态同时为真
  expect(valueStatus(base, draft, input, "sheetset:工程名称", new Set()))
    .toEqual({dirty: true, pending: true, invalid: false});
  // 仅待写入：草稿已改、输入与草稿一致
  expect(valueStatus(base, draft, input, "sheetset:项目编号", new Set()))
    .toEqual({dirty: false, pending: true, invalid: false});
  // 仅未加入草稿：草稿与基准一致、输入不同
  expect(valueStatus(base, draft, input, "sheetset:版本号", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
  // 改回基准即清除对应标记（§5.3）
  const reverted = {...input, values: {...input.values, 工程名称: draft.values["工程名称"]}};
  expect(valueStatus(base, draft, reverted, "sheetset:工程名称", new Set()))
    .toEqual({dirty: false, pending: true, invalid: false});
  expect(valueStatus(base, base, input, "sheetset:版本号", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
});

test("空串、空格与前导零原样保留，不做类型转换或裁剪", () => {
  const {base, draft, input} = triple();
  expect(valueStatus(base, draft, input, "sheetset:备注", new Set()))
    .toEqual({dirty: false, pending: false, invalid: false});
  // 空串与仅空格是不同值
  expect(valueStatus(base, draft, {...input, values: {...input.values, 备注: " "}}, "sheetset:备注", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
  // 前导零：007 与 7 是不同字符串
  expect(valueStatus(base, draft, {...input, values: {...input.values, 地上层数: "007"}}, "sheetset:地上层数", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
  // 数字形态文本不自动转换：出图日期保持文本比较
  expect(valueStatus(base, draft, {...input, values: {...input.values, 出图日期: "2026-9-1"}}, "sheetset:出图日期", new Set()))
    .toEqual({dirty: true, pending: false, invalid: false});
  // 命令构造同样原样保留（用未编辑的基准缓冲检查空串/空格）
  const baseCommand = buildSheetSetCommand(base, new Set());
  expect(baseCommand.type).toBe("update_sheet_set");
  expect(baseCommand.custom_properties["备注"]).toBe("");
  expect(baseCommand.custom_properties["版本号"]).toBe(" ");
  expect(baseCommand.custom_properties["地上层数"]).toBe("18");
});

test("字段名/当前值三种搜索模式：包含匹配、英文不区分大小写、结果保持原顺序", () => {
  const input = triple().input;
  const statusOf = statusOfTriple();
  // 仅字段名：值含关键词但字段名不含 → 不匹配
  const byName = filterValueKeys(input, "工程", "name", false, statusOf);
  expect(byName).toEqual(["sheetset:工程名称", "sheetset:工程地点"]);
  expect(byName).not.toContain("sheetset:建设单位");
  // 仅当前值：字段名含关键词但值不含 → 不匹配；英文不区分大小写
  const byValue = filterValueKeys(input, "二期", "value", false, statusOf);
  expect(byValue).toContain("sheetset:工程名称");
  expect(byValue).not.toContain("sheetset:工程地点");
  expect(filterValueKeys(input, "PHASE 2", "value", false, statusOf)).toContain("sheetset:Phase");
  // 字段名或属性值：两者并集
  const all = filterValueKeys(input, "监理", "all", false, statusOf);
  expect(all).toEqual(["sheetset:监理单位"]);
  const allName = filterValueKeys(input, "单位", "all", false, statusOf);
  expect(allName).toContain("sheetset:建设单位");
  expect(allName).toContain("sheetset:设计单位");
  // 名称与值都不含 → 全集为空；空查询匹配全部 33 项
  expect(filterValueKeys(input, "不存在的字段", "all", false, statusOf)).toEqual([]);
  expect(filterValueKeys(input, "", "all", false, statusOf)).toHaveLength(33);
  // 图纸集名称独立展示，不参与自定义属性搜索
  expect(filterValueKeys(input, "城东安置房", "all", false, statusOf)).not.toContain("@name");
  // 保持读取顺序（Phase 在 PhotoCount 之后）
  const phaseAll = filterValueKeys(input, "", "all", false, statusOf);
  expect(phaseAll.indexOf("sheetset:PhotoCount")).toBeLessThan(phaseAll.indexOf("sheetset:Phase"));
});

test("仅看修改：与搜索取交集，未加入草稿或待写入都计入", () => {
  const {input} = triple();
  const statusOf = statusOfTriple();
  // 全部修改字段（dirty 或 pending），不含未修改字段
  const changed = filterValueKeys(input, "", "all", true, statusOf);
  expect(changed).toEqual(["sheetset:工程名称", "sheetset:项目编号", "sheetset:版本号"]);
  // 与搜索取交集：仅字段名含「编号」的修改项
  expect(filterValueKeys(input, "编号", "all", true, statusOf))
    .toEqual(["sheetset:项目编号"]);
  // 搜索命中但未修改 → 不计入
  expect(filterValueKeys(input, "备注", "all", true, statusOf)).toEqual([]);
});

test("活动字段不匹配搜索时由调用方暂留，隐藏修改计数因此为 0", () => {
  const {base, draft, input} = triple();
  // 活动字段：备注 正在编辑（dirty），其值不匹配搜索「工程」；
  // 版本号 撤回输入使其不再是 dirty，保证活动字段是唯一不匹配的修改项。
  const activeKey: ValueKey = "sheetset:备注";
  const edited: PropertyBuffer = {
    name: input.name,
    values: {...input.values, 备注: "补充说明", 版本号: draft.values["版本号"]},
  };
  const statusOfEdited = (key: ValueKey) => valueStatus(base, draft, edited, key, new Set());
  // 契约：filterValueKeys 只按匹配返回，暂留由界面层追加活动字段
  const matches = filterValueKeys(edited, "工程", "all", true, statusOfEdited);
  expect(matches).toEqual(["sheetset:工程名称"]);
  expect(matches).not.toContain(activeKey);
  // 隐藏修改计数口径：dirty 且不在匹配集、且不是暂留活动字段的键数。
  // 唯一不匹配的 dirty 字段正是活动字段 → 暂留后隐藏数为 0（否则会误报 1）。
  const dirtyKeys = Object.keys(edited.values)
    .map((name) => `sheetset:${name}` as ValueKey)
    .filter((key) => statusOfEdited(key).dirty);
  expect(dirtyKeys).toEqual(["sheetset:工程名称", "sheetset:备注"]);
  const hiddenWithRetention = dirtyKeys.filter(
    (key) => !matches.includes(key) && key !== activeKey,
  );
  expect(hiddenWithRetention).toHaveLength(0);
  const hiddenWithoutRetention = dirtyKeys.filter((key) => !matches.includes(key));
  expect(hiddenWithoutRetention).toEqual([activeKey]);
});

test("失效字段阻断命令构造：抛出 PROPERTY_BUFFER_STALE，不进入命令", () => {
  const {input} = triple();
  expect(() => buildSheetSetCommand(input, new Set(["sheetset:出图日期" as ValueKey])))
    .toThrow("PROPERTY_BUFFER_STALE");
  expect(() => buildSheetSetCommand(input, new Set(["@name" as ValueKey])))
    .toThrow("PROPERTY_BUFFER_STALE");
});

test("buildSheetSetCommand 生成完整 update_sheet_set 命令并复制值映射", () => {
  const {input} = triple();
  const command = buildSheetSetCommand(input, new Set());
  // 计划 Step 1 verbatim
  expect(command).toEqual({type: "update_sheet_set", name: input.name, custom_properties: input.values});
  expect(command).toEqual({
    type: "update_sheet_set",
    name: "城东安置房一期",
    custom_properties: expect.objectContaining({"工程名称": "城东二期安置房"}),
  });
  // 完整副本：后续改动命令不得影响输入缓冲
  command.custom_properties["工程名称"] = "篡改";
  expect(input.values["工程名称"]).toBe("城东二期安置房");
});
