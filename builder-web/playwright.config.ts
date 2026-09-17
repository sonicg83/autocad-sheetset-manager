import {defineConfig} from "@playwright/test";

// Builder e2e（PLAN-DB-001 Task 5/9）：
// 1. wizard-flow / wizard-accessibility：后端端点全部由 page.route mock（controller
//    裁决），vite dev server 即可。
// 2. wizard-real-backend：真实后端场景（Task 9 裁决「你选并在 config 注明」）——
//    webServer 数组第二项用 `uv run python tests/e2e/helpers/real_backend.py`
//    拉起真实 Builder FastAPI（真实项目库与编排/发布链路，CAD 为进程内 fake），
//    监听 127.0.0.1:8101；vite 经 DST_BUILDER_API_TARGET 代理 /api 到它。
//    mock 场景不受影响：page.route 在代理之前拦截 /api。
// retries 保持 0：mock 驱动的用例不应掩盖真实回归；基础设施抖动应显式修复
// 而不是靠重试通过。
export default defineConfig({
  testDir: "tests/e2e",
  workers: 4,
  use: {baseURL: "http://127.0.0.1:4173"},
  webServer: [
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {DST_BUILDER_API_TARGET: "http://127.0.0.1:8101"},
    },
    {
      command: "uv run --project .. python tests/e2e/helpers/real_backend.py",
      url: "http://127.0.0.1:8101/docs",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
