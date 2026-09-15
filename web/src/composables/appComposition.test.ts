// @vitest-environment happy-dom
// Task 11 第 11b 轮：壳层导航组合层（页签 / 任务浮层）的单测。
//
// 为什么需要这组单测（Step 2 的原意）：11b 是**纯搬迁**——把 `App.vue` 里的页签与浮层导航搬进
// `useShellNavigation`。E2E 能覆盖端到端行为，但搬错时最难发现的恰恰是**组合语义**：
// ① 页签激活态**由既有 `useShellTabs` 驱动**（动态列表里激活项被移除时回退到首个核心页签）——
//    若本模块自己另写一份页签列表状态，E2E 仍可能全绿，而这条语义会静默丢失；
// ② 图纸目录页未保存草稿闸门的**三种走法**（重复点当前页签不重开闸门 / 无草稿同步切换 / 有草稿走闸门）
//    是 PLAN-DM-020 与 SPEC-DM-012 §3.2 的既定语义，搬动时必须逐条保住。
// 本组用例故意不 mock `useShellTabs`：要固定的正是「组合它」这一事实本身。
import {computed, nextTick, ref} from "vue";
import {describe, expect, it, vi} from "vitest";
import {useShellNavigation, type ExtensionPageLike, type ShellNavigationDeps} from "./useShellNavigation";

function makeDeps(overrides: Partial<ShellNavigationDeps> = {}): ShellNavigationDeps {
  return {
    workspace: ref<{id: string} | null>(null),
    extensionPages: computed<readonly ExtensionPageLike[]>(() => []),
    isRestoreExecuting: ref(false),
    isWorkspaceLoading: ref(false),
    // 宿主注入 i18n 与域动作：本模块不自行取 i18n，也不依赖 useRestore/useSheetCatalog
    t: (key: string) => key,
    loadRevisions: vi.fn(async () => {}),
    catalogNavigationNeeded: vi.fn(() => false),
    guardCatalogPage: vi.fn(async (next: () => void | Promise<void>) => {
      await next();
      return "continue";
    }),
    ...overrides,
  };
}

describe("useShellNavigation：页签导航", () => {
  it("无工作区时只有三个核心页签，初始激活为 sheets", () => {
    const nav = useShellNavigation(makeDeps());
    expect(nav.tabDescriptors.value.map(d => d.id)).toEqual(["sheets", "properties", "revisions"]);
    expect(nav.tabDescriptors.value.map(d => d.number)).toEqual(["①", "②", "③"]);
    expect(nav.tabDescriptors.value.every(d => d.source === "core")).toBe(true);
    expect(nav.active.value).toBe("sheets");
  });

  it("有工作区时把扩展页面追加为核心页签之后的扩展页签", () => {
    const nav = useShellNavigation(
      makeDeps({
        workspace: ref<{id: string} | null>({id: "w1"}),
        extensionPages: computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "extensions.sheetCatalog.title"}}]),
      }),
    );
    expect(nav.tabDescriptors.value.map(d => d.id)).toEqual(["sheets", "properties", "revisions", "ext.sheetCatalog"]);
    const ext = nav.tabDescriptors.value[3]!;
    expect(ext.source).toBe("extension");
    expect(ext.number).toBeUndefined();
    // 扩展页签的 label 是宿主 i18n 渲染后的文本（name_key 经注入的 t 翻译）
    expect(ext.label).toBe("extensions.sheetCatalog.title");
  });

  it("恢复执行中或工作区加载中：修订历史与扩展页签停用，核心前两项不受影响", async () => {
    const isRestoreExecuting = ref(false);
    const nav = useShellNavigation(
      makeDeps({
        workspace: ref<{id: string} | null>({id: "w1"}),
        extensionPages: computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "k"}}]),
        isRestoreExecuting,
      }),
    );
    expect(nav.tabDescriptors.value.map(d => Boolean(d.disabled))).toEqual([false, false, false, false]);
    isRestoreExecuting.value = true;
    await nextTick();
    expect(nav.tabDescriptors.value.map(d => Boolean(d.disabled))).toEqual([false, false, true, true]);
  });

  it("动态列表移除激活项时回退到首个核心页签（组合 useShellTabs 的可观测后果）", async () => {
    const workspace = ref<{id: string} | null>({id: "w1"});
    const extensionPages = computed<readonly ExtensionPageLike[]>(() => [{routeKey: "ext.sheetCatalog", summary: {name_key: "k"}}]);
    const nav = useShellNavigation(makeDeps({workspace, extensionPages}));
    nav.selectTab("ext.sheetCatalog");
    await nextTick();
    expect(nav.active.value).toBe("ext.sheetCatalog");
    // 工作区关闭 ⇒ 扩展页签消失 ⇒ 激活项不能在列表里“悬空”
    workspace.value = null;
    await nextTick();
    expect(nav.active.value).toBe("sheets");
  });

  it("切到修订历史会重新加载列表；切到其它页签不会", () => {
    const loadRevisions = vi.fn(async () => {});
    const nav = useShellNavigation(makeDeps({loadRevisions}));
    nav.selectTab("revisions");
    expect(nav.active.value).toBe("revisions");
    expect(loadRevisions).toHaveBeenCalledTimes(1);
    nav.selectTab("properties");
    expect(nav.active.value).toBe("properties");
    expect(loadRevisions).toHaveBeenCalledTimes(1);
  });

  it("重复点击当前页签不重开闸门，但修订历史页签仍重新加载列表", () => {
    const catalogNavigationNeeded = vi.fn(() => true);
    const loadRevisions = vi.fn(async () => {});
    const nav = useShellNavigation(makeDeps({catalogNavigationNeeded, loadRevisions}));
    nav.selectTab("sheets"); // 初始即 sheets：重复点击
    expect(catalogNavigationNeeded).not.toHaveBeenCalled();
    expect(nav.active.value).toBe("sheets");
    nav.selectTab("revisions"); // 目标=revisions：先非重复分支
    expect(catalogNavigationNeeded).toHaveBeenCalledTimes(1);
  });

  it("无未保存草稿时同步切换；有草稿时经闸门切换", async () => {
    const noDraft = makeDeps();
    const navA = useShellNavigation(noDraft);
    navA.selectTab("properties");
    expect(navA.active.value).toBe("properties");
    expect(noDraft.guardCatalogPage).not.toHaveBeenCalled();

    const withDraft = makeDeps({catalogNavigationNeeded: vi.fn(() => true)});
    const navB = useShellNavigation(withDraft);
    navB.selectTab("properties");
    // 有草稿：交给闸门决定，闸门未 resolve 前不切换
    expect(withDraft.guardCatalogPage).toHaveBeenCalledTimes(1);
    await nextTick();
    expect(navB.active.value).toBe("properties");
  });

  it("方向键：无草稿时同步跟随；有草稿时先回退激活项再走闸门（取消则不留在错页签）", async () => {
    const noDraft = makeDeps();
    const navA = useShellNavigation(noDraft);
    navA.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    expect(navA.active.value).toBe("properties");

    // 有草稿且用户【取消】：闸门不执行 next()。此时若没先回退 active，UI 会留在错页签。
    const cancelled = makeDeps({
      catalogNavigationNeeded: vi.fn(() => true),
      guardCatalogPage: vi.fn(async (_next: () => void | Promise<void>) => "cancel"),
    });
    const navB = useShellNavigation(cancelled);
    navB.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    expect(navB.active.value).toBe("sheets");
    expect(cancelled.guardCatalogPage).toHaveBeenCalledTimes(1);

    // 有草稿且闸门放行：闸门内部才真正切换页签
    const proceed = makeDeps({catalogNavigationNeeded: vi.fn(() => true)});
    const navC = useShellNavigation(proceed);
    navC.onTabKeydown(new KeyboardEvent("keydown", {key: "ArrowRight"}));
    await nextTick();
    expect(proceed.guardCatalogPage).toHaveBeenCalledTimes(1);
    expect(navC.active.value).toBe("properties");
  });
});

describe("useShellNavigation：任务浮层", () => {
  it("openOverlay 同时设置页签与展开态；resetOverlay 复位为 prog/收起", () => {
    const nav = useShellNavigation(makeDeps());
    expect(nav.overlayOpen.value).toBe(false);
    expect(nav.overlayTab.value).toBe("prog");
    nav.openOverlay("prev");
    expect(nav.overlayOpen.value).toBe(true);
    expect(nav.overlayTab.value).toBe("prev");
    nav.resetOverlay();
    expect(nav.overlayOpen.value).toBe(false);
    expect(nav.overlayTab.value).toBe("prog");
  });

  it("jumpOverlay 只放行三个合法页签（非法值忽略且不改动状态）", () => {
    const nav = useShellNavigation(makeDeps());
    nav.openOverlay("prev");
    nav.jumpOverlay("diagnostics-typo");
    expect(nav.overlayOpen.value).toBe(true);
    expect(nav.overlayTab.value).toBe("prev");
    nav.jumpOverlay("diag");
    expect(nav.overlayTab.value).toBe("diag");
  });
});
