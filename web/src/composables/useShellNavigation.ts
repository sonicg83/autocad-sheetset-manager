import {computed, ref, type ComputedRef, type Ref} from "vue";
import {useShellTabs, type TabDescriptor} from "./useShellTabs";

// 壳层导航组合式函数（PLAN-DM-029 Task 11 Step 4 上半，第 11b 轮）：页签栏状态与任务浮层开关。
//
// **组合而非复制**（Step 4 原文）：页签的 active/select/onKeydown 仍由既有 `useShellTabs` 提供——
// 本模块只组合它，**不重新实现页签列表状态**；全局快捷键仍由根组件那一次 `useHotkeys` 注册，
// 本模块**不注册任何快捷键、也不复制其职责**。
//
// 依赖一律经 `deps` 注入（含 i18n 的 `t`）：这样本模块既不自行取 i18n，也不反过来依赖
// `useRestore`/`useSheetCatalog` 等域模块，单测可以在 node/happy-dom 里直接构造依赖。
export interface ExtensionPageLike {
  routeKey: string;
  summary: {name_key: string};
}

export interface ShellNavigationDeps {
  /** 当前工作区；仅用于「无工作区时只显示核心页签」的判断 */
  workspace: Ref<{id: string} | null>;
  /** 扩展贡献的页面（routeKey + 名称键），与核心页签合成标签列表 */
  extensionPages: ComputedRef<readonly ExtensionPageLike[]>;
  /** 恢复执行中 / 工作区加载中：修订历史与扩展页签在此期间停用 */
  isRestoreExecuting: Ref<boolean>;
  isWorkspaceLoading: Ref<boolean>;
  /** 宿主 i18n；核心页签文案与扩展页签的 name_key 译文都由它渲染 */
  t: (key: string) => string;
  /** 切到修订历史时重新加载列表（由宿主注入，避免本模块依赖 useRestore） */
  loadRevisions: () => Promise<void>;
  /** 图纸目录页未保存草稿闸门（PLAN-DM-020 Task 11 / SPEC-DM-012 §3.2） */
  catalogNavigationNeeded: () => boolean;
  guardCatalogPage: (next: () => void | Promise<void>) => Promise<unknown>;
}

export function useShellNavigation(deps: ShellNavigationDeps) {
  const tabDescriptors = computed<TabDescriptor[]>(() => {
    const busyDisabled = deps.isRestoreExecuting.value || deps.isWorkspaceLoading.value;
    const core: TabDescriptor[] = [
      {id: "sheets", label: deps.t("shell.tabs.sheets"), number: "①", source: "core"},
      {id: "properties", label: deps.t("shell.tabs.properties"), number: "②", source: "core"},
      {id: "revisions", label: deps.t("shell.tabs.revisions"), number: "③", source: "core", disabled: busyDisabled},
    ];
    if (deps.workspace.value === null) return core;
    for (const page of deps.extensionPages.value) {
      core.push({id: page.routeKey, label: deps.t(page.summary.name_key), source: "extension", disabled: busyDisabled});
    }
    return core;
  });
  const tabIds = computed(() => tabDescriptors.value.map(descriptor => descriptor.id));
  // 固定标签栏状态（SPEC-DM-006 §7.2）：active/select/onKeydown 由 useShellTabs 提供，TabBar 为受控组件；
  // 动态列表下激活项被移除时安全校正回首个核心标签
  const {active, select, onKeydown} = useShellTabs<string>(tabIds, "sheets", "sheets");

  // 任务浮层状态（SPEC-DM-006 §4.1）：open/tab 由本模块持有；openOverlay 为唯一自动展开入口。
  // 这两者同时被 Task 7 的 toast 抑制（overlayOpen && overlayTab==="prog"）与 "查看" 跳转依赖。
  const overlayOpen = ref(false);
  const overlayTab = ref<"prog" | "prev" | "diag">("prog");
  function openOverlay(tab: "prog" | "prev" | "diag") {
    overlayTab.value = tab;
    overlayOpen.value = true;
  }
  /** 工作区装载/关闭时把浮层复位（原先散落在两处的 `overlayOpen=false;overlayTab="prog"` 归并到此） */
  function resetOverlay() {
    overlayOpen.value = false;
    overlayTab.value = "prog";
  }
  /** toast "查看" 跳转：只放行三个合法页签，其它值忽略且不改动当前状态 */
  function jumpOverlay(tab: string) {
    if (tab === "prog" || tab === "prev" || tab === "diag") openOverlay(tab);
  }

  // 切换页签先过图纸目录页未保存草稿闸门（PLAN-DM-020 Task 11 / SPEC-DM-012 §3.2：
  // 目录页未挂载时守卫为空操作）；目录页自身草稿在离开前必须三选一。
  // 重复点击当前页签保留既有语义：不重开闸门，修订历史页签仍然重新加载列表
  function selectTab(id: string) {
    if (id === active.value) { if (id === "revisions") void deps.loadRevisions(); return; }
    if (!deps.catalogNavigationNeeded()) { select(id); if (id === "revisions") void deps.loadRevisions(); return; }
    void doSelectTab(id);
  }
  async function doSelectTab(id: string) {
    await deps.guardCatalogPage(() => { select(id); if (id === "revisions") void deps.loadRevisions(); });
  }
  function onTabKeydown(e: KeyboardEvent) {
    const before = active.value; onKeydown(e);
    const target = active.value;
    if (target === before) return;
    // 无未保存草稿时保持既有同步切换（useShellTabs 已改写 active）；有草稿才走闸门。
    // 有草稿时必须先把 active 退回去：否则在闸门 resolve 前 UI 已经切走，取消了也会停在错页签。
    if (!deps.catalogNavigationNeeded()) { if (target === "revisions") void deps.loadRevisions(); return; }
    active.value = before; void doSelectTab(target);
  }

  return {tabDescriptors, active, overlayOpen, overlayTab, openOverlay, resetOverlay, jumpOverlay, selectTab, onTabKeydown};
}
