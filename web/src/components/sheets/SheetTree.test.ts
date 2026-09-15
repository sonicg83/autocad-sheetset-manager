// @vitest-environment happy-dom
// 图纸导航树的键盘与 roving tabindex 契约（PLAN-DM-029 Task 10 Step 1）。
//
// 关注点（SPEC-DM-006 §7.2 结构树键盘模型）：
// 1. **容器不是额外的 Tab 停靠点** —— `role=tree` 容器自身不得可聚焦；Tab 应直接落在活动
//    `treeitem` 上（此前容器带 `tabindex="0"`，于是树里出现两个 Tab 停靠点）。
// 2. **`treeitem` 内不得有常驻嵌套按钮** —— 子集的展开指示器只能是树项自身点击/键盘模型的一部分，
//    不能是嵌套的可聚焦 `button`（否则 Tab 会在树里多出 N 个停靠点，且 AT 会把树项当容器读）。
// 3. 仅活动节点 `tabindex=0`、其余 `-1`；方向键/Home/End 移动焦点并同步 roving tabindex；
//    右/左展开收起；Enter/Space 激活。
//
// happy-dom 不算布局，因此本文件只断言**结构与可聚焦性**（属性、DOM 关系、activeElement），
// 尺寸/颜色一律交给 e2e（`sheets-layout.spec.ts` / `sheets-visual-regressions.spec.ts`）。
import {afterEach,describe,expect,it} from "vitest";
import {mount} from "@vue/test-utils";
import {createI18n} from "vue-i18n";
import {nextTick} from "vue";
import SheetTree from "./SheetTree.vue";
import type {Workspace} from "../../api/contracts";
import type {SheetScope} from "../../features/sheets/types";

const messages = {
  "zh-CN": {
    sheets: {
      tree: {
        navAria: "图纸导航",
        all: "全部图纸",
        countSuffix: "（{count} 张）",
        nodeAria: "{label}（{count} 张）",
        collapseSubset: "收起子集 {label}",
        expandSubset: "展开子集 {label}",
      },
    },
  },
};

/** 只构造组件真正读取的字段（`id` / `sheet_set.{sheet_count,subsets[]}`），其余按契约断言。 */
function fixture(): Workspace {
  return {
    id: "workspace-1",
    sheet_set: {
      sheet_count: 3,
      subsets: [
        {
          id: "subset-1",
          display_name: "建筑施工图",
          sheets: [
            {id: "sheet-1", number: "001", title: "图纸 1"},
            {id: "sheet-2", number: "002", title: "图纸 2"},
          ],
        },
        {
          id: "subset-2",
          display_name: "结构施工图",
          sheets: [{id: "sheet-3", number: "003", title: "图纸 3"}],
        },
      ],
    },
  } as unknown as Workspace;
}

function mountTree(scope: SheetScope = {kind: "all"}) {
  const i18n = createI18n({legacy: false, locale: "zh-CN", messages});
  // 必须 attachTo：元素不入文档时 happy-dom 的 `.focus()` 不会改变 document.activeElement，
  // 焦点断言会假红（已用临时探针核实：裸 div[tabindex] 与组件内树项在文档内均可聚焦）。
  const wrapper = mount(SheetTree, {
    props: {workspace: fixture(), scope, focusedSheetId: null},
    global: {plugins: [i18n]},
    attachTo: document.body,
  });
  mounted.push(wrapper);
  return wrapper;
}
const mounted: Array<{unmount: () => void}> = [];
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

const treeitems = (wrapper: ReturnType<typeof mountTree>) => wrapper.findAll('[role="treeitem"]');
const tabindexes = (wrapper: ReturnType<typeof mountTree>) =>
  treeitems(wrapper).map((node) => node.attributes("tabindex"));

/** 在节点上派发按键：真实用户是在**已聚焦的树项**上按键，事件再冒泡到容器。 */
async function press(wrapper: ReturnType<typeof mountTree>, index: number, key: string) {
  await treeitems(wrapper)[index]!.trigger("keydown", {key});
  await nextTick();
}

describe("SheetTree：结构树键盘模型", () => {
  it("容器不是额外的 Tab 停靠点（role=tree 自身不可聚焦）", () => {
    const wrapper = mountTree();
    const container = wrapper.find(".sheet-tree");
    expect(container.attributes("role")).toBe("tree");
    // Tab 应直接进入活动树项；容器若带 tabindex，树里就多一个停靠点。
    expect(container.attributes("tabindex"), "role=tree 容器不应可聚焦").toBeUndefined();
  });

  it("treeitem 内不得有常驻嵌套按钮（展开指示器不是可聚焦控件）", () => {
    const wrapper = mountTree();
    expect(wrapper.findAll('[role="treeitem"] button'), "树项内的嵌套按钮").toHaveLength(0);
  });

  it("整个树只有活动节点 tabindex=0，其余为 -1", () => {
    const wrapper = mountTree();
    expect(tabindexes(wrapper)).toEqual(["0", "-1", "-1"]);
    expect(wrapper.findAll('[tabindex="0"]'), "树内唯一 Tab 停靠点").toHaveLength(1);
  });

  it("方向键与 Home/End 移动焦点，并同步 roving tabindex", async () => {
    const wrapper = mountTree();
    await press(wrapper, 0, "ArrowDown");
    expect(tabindexes(wrapper)).toEqual(["-1", "0", "-1"]);
    expect(document.activeElement).toBe(treeitems(wrapper)[1]!.element);

    await press(wrapper, 1, "End");
    expect(tabindexes(wrapper)).toEqual(["-1", "-1", "0"]);

    await press(wrapper, 2, "ArrowUp");
    expect(tabindexes(wrapper)).toEqual(["-1", "0", "-1"]);

    await press(wrapper, 1, "Home");
    expect(tabindexes(wrapper)).toEqual(["0", "-1", "-1"]);
  });

  it("ArrowRight 展开子集、ArrowLeft 收起，aria-expanded 同步", async () => {
    const wrapper = mountTree();
    await press(wrapper, 0, "ArrowDown"); // 落到子集 1
    const subset = () => treeitems(wrapper)[1]!;
    expect(subset().attributes("aria-expanded")).toBe("false");

    await press(wrapper, 1, "ArrowRight");
    expect(subset().attributes("aria-expanded")).toBe("true");
    // 展开后子项可见，且活动节点仍是子集本身（roving tabindex 不跳走）
    expect(treeitems(wrapper).length).toBeGreaterThan(3);
    expect(subset().attributes("tabindex")).toBe("0");

    await press(wrapper, 1, "ArrowLeft");
    expect(subset().attributes("aria-expanded")).toBe("false");
    expect(treeitems(wrapper)).toHaveLength(3);
    expect(subset().attributes("tabindex")).toBe("0");
  });

  it("ArrowLeft 从图纸回到其子集", async () => {
    const wrapper = mountTree();
    await press(wrapper, 0, "ArrowDown"); // 子集 1
    await press(wrapper, 1, "ArrowRight"); // 展开
    await press(wrapper, 1, "ArrowDown"); // 落到图纸 1
    expect(tabindexes(wrapper).slice(0, 3)).toEqual(["-1", "-1", "0"]);
    await press(wrapper, 2, "ArrowLeft"); // 图纸 1 → 子集 1
    expect(tabindexes(wrapper).slice(0, 3)).toEqual(["-1", "0", "-1"]);
  });

  it("Enter 与 Space 激活节点（按节点类型发出对应事件）", async () => {
    const wrapper = mountTree();
    await press(wrapper, 0, "Enter");
    expect(wrapper.emitted("selectAll")).toHaveLength(1);

    await press(wrapper, 0, "ArrowDown");
    await press(wrapper, 1, " ");
    expect(wrapper.emitted("selectSubset")).toEqual([["subset-1"]]);

    // 键盘处理器按【当前聚焦索引】取节点，因此必须先用方向键真的把焦点移过去
    await press(wrapper, 1, "ArrowRight"); // 展开
    await press(wrapper, 1, "ArrowDown"); // 焦点落到图纸 1
    await press(wrapper, 2, "Enter");
    expect(wrapper.emitted("selectSheet")).toEqual([["sheet-1"]]);
  });

  it("选中子集后自动展开（真实流程：mount 后再改 scope）", async () => {
    const wrapper = mountTree();
    expect(treeitems(wrapper)).toHaveLength(3);
    await wrapper.setProps({scope: {kind: "subset", id: "subset-1"} as SheetScope});
    // all + subset-1 + 它的 2 张图纸 + subset-2
    expect(treeitems(wrapper)).toHaveLength(5);
    const stops = wrapper.findAll('[tabindex="0"]');
    expect(stops).toHaveLength(1);
    expect(stops[0]!.attributes("role")).toBe("treeitem");
  });

  it("展开指示器仍可鼠标点击（去掉嵌套按钮不等于去掉鼠标路径）", async () => {
    const wrapper = mountTree();
    const chevron = treeitems(wrapper)[1]!.find(".chevron");
    expect(chevron.exists()).toBe(true);
    await chevron.trigger("click");
    expect(treeitems(wrapper)[1]!.attributes("aria-expanded")).toBe("true");
  });

  it("workspace 变化时重置折叠状态与活动节点", async () => {
    const wrapper = mountTree();
    await press(wrapper, 0, "ArrowDown");
    expect(tabindexes(wrapper)).toEqual(["-1", "0", "-1"]);
    await wrapper.setProps({workspace: {...fixture(), id: "workspace-2"} as unknown as Workspace});
    expect(tabindexes(wrapper)).toEqual(["0", "-1", "-1"]);
  });
});
