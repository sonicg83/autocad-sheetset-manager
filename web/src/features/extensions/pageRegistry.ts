// 扩展页面贡献编译期映射（PLAN-DM-020 Task 10 / ARCH-DM-006 §7）。
// 红线：扩展不能提交 URL、HTML、JavaScript、CSS 或 Vue 模块路径；清单中的
// route_key 必须命中本映射才挂载。动态 import 的路径全部来自本文件内的静态
// 字面量，后端返回的 route_key 只作查表键——未知 route_key 安全忽略，绝不
// 进入 import() 表达式。新增扩展页面时在此登记一行，并同步扩展 pageRegistry.test.ts。
import {defineAsyncComponent} from "vue";

export const EXTENSION_PAGE_COMPONENTS = {
  "sheet-catalog": defineAsyncComponent(() => import("../../views/SheetCatalogView.vue")),
} as const;

export type ExtensionRouteKey = keyof typeof EXTENSION_PAGE_COMPONENTS;

// 受信 route_key 校验：只认本映射自有键（hasOwnProperty，原型链键如
// __proto__/constructor 不放行），未知值由调用方安全忽略。
export function isExtensionRouteKey(value: string): value is ExtensionRouteKey {
  return Object.prototype.hasOwnProperty.call(EXTENSION_PAGE_COMPONENTS, value);
}
