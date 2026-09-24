import {defineConfig} from "vitest/config";
import vue from "@vitejs/plugin-vue";

// 前端单元测试（PLAN-DM-021 Task 2；挂载 SFC 的能力见 PLAN-DM-029 Task 3 Step 1）：
// 默认仍是 node 环境 + 显式导入 vitest API，绝大多数单测只覆盖纯 TS 模块。
// 加载 vue 插件只为让 `components/ui` 的组件契约测试能真实挂载 SFC；需要 DOM 的
// 测试文件用 `// @vitest-environment happy-dom` 逐文件声明，默认环境与 include 不变。
//
// 加插件的代价不止“能编译 SFC”（核验自 `@vitejs/plugin-vue` 发行代码）：它同时注入
// `__VUE_OPTIONS_API__`（true）、`__VUE_PROD_DEVTOOLS__`（false）、
// `__VUE_PROD_HYDRATION_MISMATCH_DETAILS__`（false）三个编译期 define，并在非 SSR 时
// 加上 `resolve.dedupe: ["vue"]`。这些注入与 `vite.config.ts` 生产构建的插件默认值一致，
// 所以测试与产物不会因环境不同而走不同分支；dedupe 另外保证测试进程内只有一份 `vue`。
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // transform 结果持久化到磁盘，跨次运行复用（此前 transform 占单次运行约 60% 耗时且每次重算）。
    fsModuleCache: true,
  },
});
