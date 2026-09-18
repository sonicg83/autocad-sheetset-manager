// 真实后端 e2e（PLAN-DB-001 Task 9 controller 裁决）：vite 代理指向
// tests/e2e/helpers/real_backend.py 拉起的真实 Builder FastAPI（真实项目库与
// 编排/发布链路，CAD 执行器为进程内 fake）。全部 /api/** 端点均走真实后端。
import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {expect, test} from "@playwright/test";

// real_backend.py 启动时重建同一确定性目录（builder-web/.e2e/project）。
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e/project");

let workDir: string;
let outputPath: string;
let baseDwg: string;
let layoutDwt: string;

test.beforeAll(() => {
  workDir = mkdtempSync(join(tmpdir(), "dstb-e2e-"));
  outputPath = join(workDir, "example-package"); // 必须不存在（§4）
  baseDwg = join(workDir, "base.dwg");
  layoutDwt = join(workDir, "layout.dwt");
  writeFileSync(baseDwg, "fake base dwg bytes for e2e");
  writeFileSync(layoutDwt, "fake layout template bytes for e2e");
});

test("真实后端全流程：创建项目 → 资产 → 计划确认 → 构建", async ({page}) => {
  await page.goto("/");
  await expect(page.getByTestId("wizard-shell")).toBeVisible();

  // 第 1 步：创建项目（真实后端写真实项目库）
  await page.getByLabel("项目目录").fill(projectRoot);
  await page.getByLabel("工程名称").fill("示例工程");
  await page.getByLabel("阶段").fill("施工图");
  await page.getByLabel("专业").fill("建筑");
  await page.getByLabel("成果目录").fill(outputPath);
  await page.getByTestId("create-project").click();
  await expect(page.getByTestId("dock-next")).toBeEnabled({timeout: 10_000});

  // 第 2 步：规则
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  await page.getByLabel("图号前缀").fill("A-");
  await expect(page.getByTestId("sheet-number-preview")).toHaveText("A-001");

  // 第 3 步：图纸
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "编排图纸"})).toBeVisible();
  await page.getByLabel("图名").fill("首层平面图");

  // 第 4 步：纳入资产并探测布局（真实落盘 + fake CAD 布局列表）
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "匹配模板"})).toBeVisible();
  await page.getByLabel("基础 DWG 路径").fill(baseDwg);
  await page.getByTestId("intake-base").click();
  await expect(page.getByTestId("asset-base-info")).toBeVisible({timeout: 10_000});
  await page.getByLabel("布局模板路径").fill(layoutDwt);
  await page.getByTestId("intake-layout").click();
  await expect(page.getByTestId("asset-layout-info")).toBeVisible({timeout: 10_000});
  await page.getByTestId("inspect-layout").click();
  await page.getByLabel("源布局").selectOption("A1", {timeout: 10_000});

  // 第 5 步：提交修订 → 用户显式确认
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "构建前检查"})).toBeVisible();
  await page.getByTestId("submit-revision").click();
  await expect(page.getByTestId("plan-preview")).toBeVisible({timeout: 10_000});
  await page.getByTestId("confirm-plan").click();
  await expect(page.getByTestId("plan-confirmed")).toBeVisible({timeout: 10_000});

  // 第 6 步：启动构建（真实编排：fake CAD → DST → 验证 → 原子发布）——向导末步
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "构建成果"})).toBeVisible();
  await page.getByTestId("start-build").click();
  await expect(page.getByTestId("build-status")).toHaveText(/SUCCEEDED/, {timeout: 30_000});
  await expect(page.getByTestId("published-path")).toContainText("example-package");
});
