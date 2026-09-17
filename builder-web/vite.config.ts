import {defineConfig} from "vite";
import vue from "@vitejs/plugin-vue";

// Builder API 默认监听 127.0.0.1:8100（PLAN-DB-001 Task 3/4）；可经环境变量覆盖。
// e2e 用 page.route mock 全部后端端点（controller 裁决），不依赖真实后端进程。
const apiTarget = process.env.DST_BUILDER_API_TARGET ?? "http://127.0.0.1:8100";

export default defineConfig({
  plugins: [vue()],
  server: {proxy: {"/api": apiTarget}},
});
