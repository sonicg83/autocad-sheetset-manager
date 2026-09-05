<script setup lang="ts">
// 图纸导航树（PLAN-DM-015 任务 3，SPEC-DM-009 §3.1/§4.1）：全部图纸 / 子集 / 图纸。
// 树与范围筛选共用一个范围状态；点击子集切换范围、点击图纸经 locateSheet 定位。
// 扁平渲染 + aria-level 平铺树；方向键/Home/End 漫游焦点，子集支持展开/收起。
import {computed, nextTick, ref, watch} from "vue";
import type {Workspace} from "../../api/contracts";
import type {SheetScope} from "../../features/sheets/types";

const props = defineProps<{
  workspace: Workspace;
  scope: SheetScope;
  focusedSheetId: string | null;
}>();
const emit = defineEmits<{
  selectAll: [];
  selectSubset: [id: string];
  selectSheet: [id: string];
}>();

type TreeNode =
  | {kind: "all"; id: string; label: string; count: number; level: number}
  | {kind: "subset"; id: string; label: string; count: number; level: number; expanded: boolean}
  | {kind: "sheet"; id: string; label: string; number: string; subsetId: string; level: number};

// 全部图纸范围默认只显示子集；选中某个子集时自动展开该子集，减少真实工程中的导航噪声。
const collapsed = ref<Set<string>>(new Set());
const treeEl = ref<HTMLElement | null>(null);
const focusIndex = ref(0);

watch(() => props.workspace.id, () => {
  collapsed.value = new Set(props.workspace.sheet_set.subsets.map((subset) => subset.id));
  focusIndex.value = 0;
}, {immediate: true});
watch(() => props.scope, (scope) => {
  if (scope.kind !== "subset" || !collapsed.value.has(scope.id)) return;
  const nextSet = new Set(collapsed.value);
  nextSet.delete(scope.id);
  collapsed.value = nextSet;
});

const visibleNodes = computed<TreeNode[]>(() => {
  const nodes: TreeNode[] = [];
  nodes.push({kind: "all", id: "all", label: "全部图纸", count: props.workspace.sheet_set.sheet_count, level: 1});
  for (const subset of props.workspace.sheet_set.subsets) {
    const expanded = !collapsed.value.has(subset.id);
    nodes.push({kind: "subset", id: subset.id, label: subset.display_name, count: subset.sheets.length, level: 2, expanded});
    if (expanded) {
      for (const sheet of subset.sheets) {
        nodes.push({kind: "sheet", id: sheet.id, label: `${sheet.number} ${sheet.title}`, number: sheet.number, subsetId: subset.id, level: 3});
      }
    }
  }
  return nodes;
});

function nodeAriaLabel(node: TreeNode): string {
  if (node.kind === "subset") return `${node.label}（${node.count} 张）`;
  if (node.kind === "all") return `${node.label}（${node.count} 张）`;
  return node.label;
}
function isScopeNode(node: TreeNode): boolean {
  return props.scope.kind === "all" ? node.kind === "all"
    : node.kind === "subset" && node.id === props.scope.id;
}
function isSubsetExpanded(node: TreeNode): boolean | undefined {
  return node.kind === "subset" ? node.expanded : undefined;
}

function activate(node: TreeNode) {
  if (node.kind === "all") emit("selectAll");
  else if (node.kind === "subset") emit("selectSubset", node.id);
  else emit("selectSheet", node.id);
}
function toggleCollapse(node: TreeNode) {
  if (node.kind !== "subset") return;
  const nextSet = new Set(collapsed.value);
  if (nextSet.has(node.id)) nextSet.delete(node.id); else nextSet.add(node.id);
  collapsed.value = nextSet;
}
function scrollNodeIntoView(index: number) {
  void nextTick(() => {
    treeEl.value?.querySelectorAll<HTMLElement>("[role=treeitem]")[index]?.scrollIntoView({block: "nearest"});
  });
}

function onKeydown(event: KeyboardEvent) {
  const count = visibleNodes.value.length;
  if (count === 0) return;
  const move = (index: number) => {
    focusIndex.value = index;
    scrollNodeIntoView(index);
    // roving tabindex：方向键真正移动焦点（SPEC-DM-006 §7.2 结构树键盘模型），
    // 焦点停在目标节点，后续按键经事件冒泡回容器处理
    treeEl.value?.querySelectorAll<HTMLElement>("[role=treeitem]")[index]?.focus();
  };
  switch (event.key) {
    case "ArrowDown": event.preventDefault(); move(Math.min(focusIndex.value + 1, count - 1)); break;
    case "ArrowUp": event.preventDefault(); move(Math.max(focusIndex.value - 1, 0)); break;
    case "Home": event.preventDefault(); move(0); break;
    case "End": event.preventDefault(); move(count - 1); break;
    case "ArrowRight": {
      event.preventDefault();
      const node = visibleNodes.value[focusIndex.value];
      if (node.kind === "subset" && !node.expanded) { toggleCollapse(node); scrollNodeIntoView(focusIndex.value); }
      else { activate(node); } // 叶子激活同点击；已展开子集再按右键视为激活（切范围）
      break;
    }
    case "ArrowLeft": {
      event.preventDefault();
      const node = visibleNodes.value[focusIndex.value];
      if (node.kind === "subset" && node.expanded) { toggleCollapse(node); scrollNodeIntoView(focusIndex.value); }
      else if (node.kind === "sheet") {
        const parentIndex = visibleNodes.value.findIndex((item) => item.kind === "subset" && item.id === node.subsetId);
        move(parentIndex >= 0 ? parentIndex : focusIndex.value);
      }
      break;
    }
    case "Enter":
    case " ": event.preventDefault(); activate(visibleNodes.value[focusIndex.value]); break;
  }
}
</script>
<template>
  <div ref="treeEl" class="sheet-tree" role="tree" aria-label="图纸导航" tabindex="0" @keydown="onKeydown">
    <div
      v-for="(node, index) in visibleNodes"
      :key="`${node.kind}-${node.id}`"
      role="treeitem"
      :aria-label="nodeAriaLabel(node)"
      :aria-level="node.level"
      :aria-expanded="isSubsetExpanded(node)"
      :aria-selected="isScopeNode(node)"
      :title="node.label"
      :tabindex="index === focusIndex ? 0 : -1"
      :class="{active: isScopeNode(node), focused: node.kind === 'sheet' && node.id === focusedSheetId}"
      @click="focusIndex = index; activate(node)"
      @focus="focusIndex = index"
    >
      <button
        v-if="node.kind === 'subset'"
        type="button"
        class="chevron"
        :aria-label="node.expanded ? `收起子集 ${node.label}` : `展开子集 ${node.label}`"
        @click.stop="focusIndex = index; toggleCollapse(node)"
      >{{ node.expanded ? "▾" : "▸" }}</button>
      <span v-else class="chevron-placeholder"></span>
      <span class="node-label">{{ node.label }}</span>
      <span class="node-count">{{ node.kind === "sheet" ? "" : `（${node.count} 张）` }}</span>
    </div>
  </div>
</template>
<style scoped>
.sheet-tree{display:flex;flex-direction:column;gap:2px;padding:var(--space-2);outline:none}
.sheet-tree:focus-visible{outline:2px solid var(--color-focus,var(--color-accent));outline-offset:-2px}
.sheet-tree [role=treeitem]{display:flex;align-items:flex-start;gap:6px;padding:5px 8px;border-radius:var(--radius-sm,6px);cursor:pointer;font-size:13px;color:var(--color-text-primary)}
.sheet-tree [role=treeitem]:hover{background:var(--color-bg-hover,var(--color-bg-surface-2))}
.sheet-tree [role=treeitem].active{background:var(--color-accent-soft,var(--color-bg-surface-2));font-weight:600}
.sheet-tree [role=treeitem].focused .node-label{box-shadow:inset 0 -2px 0 var(--color-accent)}
.sheet-tree [role=treeitem][aria-level="2"]{padding-left:20px}
.sheet-tree [role=treeitem][aria-level="3"]{padding-left:36px}
.sheet-tree [role=treeitem]:focus-visible{outline:2px solid var(--color-focus,var(--color-accent));outline-offset:-2px}
.chevron{border:none;background:none;cursor:pointer;font-size:11px;width:16px;height:16px;padding:0;color:var(--color-text-secondary);flex:none}
.chevron-placeholder{width:16px;height:16px;flex:none}
.node-label{min-width:0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;white-space:normal;line-height:1.45;overflow-wrap:anywhere;flex:1}
.node-count{font-size:12px;color:var(--color-text-secondary);white-space:nowrap;line-height:1.45;padding-top:1px}
</style>
