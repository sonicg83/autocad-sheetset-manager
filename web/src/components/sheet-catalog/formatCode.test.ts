// 字段浏览器格式码纯函数单测（PLAN-DM-026 Task 3 / SPEC-DM-012 §5.4）。
// Vitest 只收 src/**/*.test.ts 且为 node 环境、不加载 vue 插件，因此这里只覆盖
// 纯 TS 模块；FieldBrowser.vue 的入口行为由 e2e 覆盖。
import {describe, expect, it} from "vitest";
import {applyNumberFormat, NUMBER_FORMAT_WIDTHS} from "./formatCode";

describe("applyNumberFormat", () => {
  it("按 0 的个数拼接补零格式码", () => {
    expect(applyNumberFormat("{sheet.number}", 4)).toBe("{sheet.number:0000}");
  });

  it("宽度 0 生成去前导零格式码", () => {
    expect(applyNumberFormat("{sheet.number}", 0)).toBe("{sheet.number:0}");
  });

  it("方括号引用同样可附加格式码", () => {
    expect(applyNumberFormat('{sheet["专业:代码"]}', 2)).toBe('{sheet["专业:代码"]:00}');
  });

  it("拒绝越界宽度与非完整引用", () => {
    expect(() => applyNumberFormat("{sheet.number}", 17)).toThrow();
    expect(() => applyNumberFormat("{sheet.number}", -1)).toThrow();
    expect(() => applyNumberFormat("{sheet.number", 4)).toThrow();
  });

  it("可选宽度集合在 1..16 内且不含 1（去零由专门入口承担）", () => {
    expect(NUMBER_FORMAT_WIDTHS).toEqual([2, 3, 4, 5, 6]);
  });
});
