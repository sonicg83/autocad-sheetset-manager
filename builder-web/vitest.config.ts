import {defineConfig} from "vitest/config";
import vue from "@vitejs/plugin-vue";

// Builder 前端单元测试（controller 裁决：最小单测覆盖 composables——防抖计时、
// 门禁状态机、409 处理）。node 环境 + 显式导入 vitest API；composables 均为纯 TS 模块。
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "node",
    include: ["src/**/*.spec.ts"],
  },
});
