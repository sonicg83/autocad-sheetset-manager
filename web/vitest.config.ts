import {defineConfig} from "vitest/config";

// 前端单元测试（PLAN-DM-021 Task 2）：node 环境 + 显式导入 vitest API。
// 不加载 vite.config.ts 的 vue 插件——单元测试只覆盖纯 TS 模块（i18n 基础设施），
// bootstrap 对 App.vue/vue createApp 的依赖由测试以 vi.mock 拦截，不真实加载 SFC。
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
