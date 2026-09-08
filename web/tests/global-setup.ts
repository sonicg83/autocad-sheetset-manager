// Playwright 全局 setup（PLAN-DM-019 任务 10 契约红线：设置中心 e2e 必须真实打后端，禁止 mock /api/settings）。
// 启动真实后端（web/tests/e2e/serve_backend.py，端口经 playwright.config.ts 的
// DST_MANAGER_API_TARGET 同步给 vite 代理），并以 DST_MANAGER_SETTINGS_PATH 指向固定
// 临时目录隔离用户真实配置（default_store() 已支持该环境变量）。
// --run-id 写入 /api/health 响应，健康检查同时校验 run_id，防止端口被其他进程占用时误测。
import {spawn, type ChildProcess} from "node:child_process";
import {mkdirSync, rmSync, writeFileSync, openSync} from "node:fs";
import os from "node:os";
import path from "node:path";

// 固定路径：globalSetup 与 e2e 用例（tests/e2e/fixtures/settings.ts）约定一致，
// globalSetup 进程的 process.env 无法传给测试 worker，故用固定目录而非环境变量传递。
export const SETTINGS_DIR = path.join(os.tmpdir(), "dst-manager-e2e-settings");
export const SETTINGS_PATH = path.join(SETTINGS_DIR, "settings.json");
const RUN_ID = "e2e-settings";
// 端口不可用 8000：Windows WinNAT 端口排除区间（netsh interface ipv4 show
// excludedportrange）常覆盖 7959–8058，绑定报 WinError 10013；9001 经实测可用。
// 须与 playwright.config.ts webServer.env 的 DST_MANAGER_API_TARGET 保持一致。
const API_PORT = 9001;
const BASE_URL = `http://127.0.0.1:${API_PORT}`;

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  // 清场重建：上一轮残留的覆盖值/损坏文件不得影响本轮起点
  rmSync(SETTINGS_DIR, {recursive: true, force: true});
  mkdirSync(SETTINGS_DIR, {recursive: true});
  // 预置合法空配置：diagnostics 为空，避免"文件缺失"诊断横幅干扰常规用例
  writeFileSync(SETTINGS_PATH, JSON.stringify({schema_version: 1, config_revision: 0, values: {}}, null, 2), "utf-8");

  const repoRoot = path.resolve(process.cwd(), "..");
  const logFd = openSync(path.join(SETTINGS_DIR, "serve.log"), "a");
  // 不用 `dst-manager serve`：其模块级 create_app() 不注入 RuntimeSettings，设置端点不注册
  // （计划裁决的降级）。改用测试夹具按桌面壳 run_desktop 的同一装配方式启动（见 serve_backend.py）。
  const child: ChildProcess = spawn(
    "uv",
    ["run", "python", "web/tests/e2e/serve_backend.py", "--port", String(API_PORT), "--run-id", RUN_ID],
    {cwd: repoRoot, env: {...process.env, DST_MANAGER_SETTINGS_PATH: SETTINGS_PATH}, stdio: ["ignore", logFd, logFd]},
  );

  const deadline = Date.now() + 120_000; // uv 首次冷启动可能需要同步依赖
  for (;;) {
    if (child.exitCode !== null) {
      throw new Error(`e2e 后端进程提前退出（code=${child.exitCode}），无法运行设置中心 e2e`);
    }
    try {
      const response = await fetch(`${BASE_URL}/api/health`);
      if (response.ok) {
        const body = (await response.json()) as {run_id?: string | null};
        if (body.run_id === RUN_ID) break; // 硘认定端口归属：run_id 匹配才视为本 setup 启动的后端
      }
    } catch {
      // 后端尚未就绪，继续轮询
    }
    if (Date.now() > deadline) {
      await killTree(child);
      throw new Error(`等待 e2e 后端 ${BASE_URL}/api/health 超时（run_id=${RUN_ID}）。若 ${API_PORT} 端口被占用，请先释放`);
    }
    await sleep(500);
  }

  return async () => {
    await killTree(child);
  };
}

async function killTree(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null) return;
  // Windows 下 uv 会再启动 python 子进程，须整树终止；其他平台直接 SIGTERM
  if (process.platform === "win32" && child.pid !== undefined) {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {stdio: "ignore"});
  } else {
    child.kill("SIGTERM");
  }
  await new Promise<void>(resolve => child.once("exit", () => resolve()));
}
