import {defineConfig} from "vitest/config";
import vue from "@vitejs/plugin-vue";

// 前端单元测试（PLAN-DM-021 Task 2；挂载 SFC 的能力见 PLAN-DM-029 Task 3 Step 1）：
// 默认仍是 node 环境 + 显式导入 vitest API，绝大多数单测只覆盖纯 TS 模块。
// 加载 vue 插件只为让 `components/ui` 的组件契约测试能真实挂载 SFC；需要 DOM 的
// 测试文件用 `// @vitest-environment happy-dom` 逐文件声明，默认环境与 include 不变。
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
