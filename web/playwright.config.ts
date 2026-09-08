import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"tests/e2e",
  globalSetup:"./tests/global-setup.ts",
  use:{baseURL:"http://127.0.0.1:4173"},
  webServer:{
    command:"npm run dev -- --host 127.0.0.1 --port 4173",
    url:"http://127.0.0.1:4173",
    reuseExistingServer:false,
    // 与 global-setup.ts 的 E2E_API_PORT 保持一致：vite 代理目标指向真实测试后端
    env:{DST_MANAGER_API_TARGET:"http://127.0.0.1:9001"},
  },
});
