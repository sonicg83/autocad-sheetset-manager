// 公共图标注册表（PLAN-DM-029 Task 3 Step 4；ARCH-DM-007 §6）。
//
// `UiIconName` 是封闭联合类型，`UiIcon.vue` 只按本文件登记的几何数据渲染本地 SVG，
// 不使用 `v-html`，也不接受调用方传入任意字符串或标记。
//
// 几何数据取自 Lucide（https://lucide.dev，MIT 许可）的 24×24 描边图标：保留其道路
// 数据与 1.5 描边规格，并按本仓库的 `--icon-size-*` 令牌缩放。`settings` 使用齿轮
// 路径加 3 半径内圆；`copy` 保留 Lucide 的圆角矩形加后页路径。
export type UiIconName =
  | "theme"
  | "settings"
  | "close"
  | "chevron-left"
  | "chevron-right"
  | "chevron-up"
  | "chevron-down"
  | "status-dot"
  | "search"
  | "folder"
  | "copy";

/** 图标几何：只支持 Lucide 用到的三种基本图形，避免引入任意标记。 */
export type UiIconShape =
  | {kind: "path"; d: string}
  | {kind: "circle"; cx: number; cy: number; r: number}
  | {kind: "rect"; x: number; y: number; width: number; height: number; rx: number};

export interface UiIconDefinition {
  shapes: UiIconShape[];
  /** 实心图标（如状态点）；省略时为描边图标。 */
  filled?: boolean;
}

export const UI_ICONS: Record<UiIconName, UiIconDefinition> = {
  // Lucide `contrast`：外圆加半明半暗内形，对应旧壳层用 `◐` 表达的主题切换。
  theme: {
    shapes: [
      {kind: "circle", cx: 12, cy: 12, r: 10},
      {kind: "path", d: "M12 18a6 6 0 0 0 0-12v12z"},
    ],
  },
  settings: {
    shapes: [
      {kind: "path", d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"},
      {kind: "circle", cx: 12, cy: 12, r: 3},
    ],
  },
  close: {
    shapes: [
      {kind: "path", d: "M18 6 6 18"},
      {kind: "path", d: "M6 6 18 18"},
    ],
  },
  "chevron-left": {shapes: [{kind: "path", d: "M15 18 9 12 15 6"}]},
  "chevron-right": {shapes: [{kind: "path", d: "M9 18 15 12 9 6"}]},
  "chevron-up": {shapes: [{kind: "path", d: "M18 15 12 9 6 15"}]},
  "chevron-down": {shapes: [{kind: "path", d: "M6 9 12 15 18 9"}]},
  "status-dot": {shapes: [{kind: "circle", cx: 12, cy: 12, r: 5}], filled: true},
  search: {
    shapes: [
      {kind: "circle", cx: 11, cy: 11, r: 8},
      {kind: "path", d: "M21 21 16.7 16.7"},
    ],
  },
  folder: {
    shapes: [
      {kind: "path", d: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"},
    ],
  },
  copy: {
    shapes: [
      {kind: "rect", x: 8, y: 8, width: 14, height: 14, rx: 2},
      {kind: "path", d: "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"},
    ],
  },
};
