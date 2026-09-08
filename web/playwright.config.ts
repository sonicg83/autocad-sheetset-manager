import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"tests/e2e",
  globalSetup:"./tests/global-setup.ts",
  // 全量并行时单一 vite dev server 高负载下偶发 goto ERR_ABORTED/超时类
  // 基础设施抖动（与用例逻辑无关），重跑一次消抖；真实回归仍会稳定复现
  retries:1,
  // 默认 workers=核数/2（本机 10）时单一 vite dev server 过载，goto 偶发
  // net::ERR_ABORTED；压到 4 换取全量结果稳定（实测全量时长可接受）
  workers:4,
  use:{baseURL:"http://127.0.0.1:4173"},
  webServer:{
    command:"npm run dev -- --host 127.0.0.1 --port 4173",
    url:"http://127.0.0.1:4173",
    reuseExistingServer:false,
    // 与 global-setup.ts 的 E2E_API_PORT 保持一致：vite 代理目标指向真实测试后端
    env:{DST_MANAGER_API_TARGET:"http://127.0.0.1:9001"},
  },
});
