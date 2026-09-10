// 扩展页面贡献编译期映射测试（PLAN-DM-020 Task 10 / ARCH-DM-006 §7）。
// 红线：route_key 必须命中宿主编译期映射才挂载；后端/清单值绝不成为动态 import 路径。
import {describe, expect, it} from "vitest";
import {EXTENSION_PAGE_COMPONENTS, isExtensionRouteKey} from "./pageRegistry";

describe("扩展页面贡献映射（PLAN-DM-020 Task 10）", () => {
  it("只暴露编译期白名单 route key", () => {
    expect(Object.keys(EXTENSION_PAGE_COMPONENTS).sort()).toEqual(["sheet-catalog"]);
  });

  it("内置扩展声明的 route key 命中映射", () => {
    expect(isExtensionRouteKey("sheet-catalog")).toBe(true);
  });

  it("未知 route_key 安全忽略，绝不成为动态 import 路径", () => {
    for (const value of [
      "does-not-exist",
      "template-browser",
      "../../views/SheetsView.vue",
      "sheet-catalog/extra",
      "sheet-catalog%00",
      "__proto__",
      "constructor",
      "",
    ]) {
      expect(isExtensionRouteKey(value)).toBe(false);
    }
  });
});
