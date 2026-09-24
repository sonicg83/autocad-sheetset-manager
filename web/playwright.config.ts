import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"tests/e2e",
  globalSetup:"./tests/global-setup.ts",
  // 偶发 goto ERR_ABORTED/超时类基础设施抖动（与用例逻辑无关），重跑一次消抖；
  // 真实回归仍会稳定复现
  retries:1,
  // 历史上单一 vite dev server 在 workers=核数/2 时过载（goto 偶发
  // net::ERR_ABORTED），压到 4。现改为一次性 vite build + vite preview 静态
  // 服务：消除了 dev server 的按需转译热点，静态文件服务的吞吐足以支撑 8 workers。
  workers:8,
  // settings-dialog.spec.ts 会直接改写唯一真实后端使用的共享 settings.json；
  // 先单独跑完该文件，再启动其余并行用例，避免 schema 异常窗口污染其它 spec。
  projects:[
    {
      name:"settings-file-mutating",
      testMatch:"settings-dialog.spec.ts",
    },
    {
      name:"parallel",
      testIgnore:"settings-dialog.spec.ts",
      dependencies:["settings-file-mutating"],
    },
  ],
  use:{baseURL:"http://127.0.0.1:4173"},
  webServer:{
    // preview 服务器默认端口即 4173，并继承 vite.config.ts 的 server.proxy（/api
    // → DST_MANAGER_API_TARGET），与原 dev server 行为一致。
    command:"npx vite build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
    url:"http://127.0.0.1:4173",
    reuseExistingServer:false,
    // 与 global-setup.ts 的 E2E_API_PORT 保持一致：vite 代理目标指向真实测试后端
    env:{DST_MANAGER_API_TARGET:"http://127.0.0.1:9001"},
  },
});
