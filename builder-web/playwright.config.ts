import {defineConfig} from "@playwright/test";

// Builder e2e（PLAN-DB-001 Task 5 controller 裁决）：全部后端端点用 page.route mock，
// 不启动真实后端，webServer 只需 vite dev server。retries 保持 0：mock 驱动的用例
// 不应掩盖真实回归；基础设施抖动应显式修复而不是靠重试通过。
export default defineConfig({
  testDir: "tests/e2e",
  workers: 4,
  use: {baseURL: "http://127.0.0.1:4173"},
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
