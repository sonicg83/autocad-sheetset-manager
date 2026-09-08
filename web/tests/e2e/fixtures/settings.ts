// 设置中心 e2e 夹具：与 tests/global-setup.ts 约定同一隔离配置目录（固定路径，
// 因 globalSetup 的 process.env 无法传给测试 worker）。
// 场景写入均为"外部手编 settings.json"真实路径：后端 GET 前按文件指纹刷新（refresh_if_changed），
// 写坏/写新 schema 后重新打开对话框即可触发对应诊断，无需重启后端。
import {mkdirSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import {expect,type Page} from "@playwright/test";

export const SETTINGS_DIR = path.join(os.tmpdir(), "dst-manager-e2e-settings");
export const SETTINGS_PATH = path.join(SETTINGS_DIR, "settings.json");

export function writeSettingsFile(
  values: Record<string, unknown>,
  configRevision = 0,
  schemaVersion: number | string = 1,
): void {
  mkdirSync(SETTINGS_DIR, {recursive: true});
  const payload = typeof schemaVersion === "number"
    ? JSON.stringify({schema_version: schemaVersion, config_revision: configRevision, values})
    : schemaVersion; // 传入非数字时按原始文本写入（损坏场景）
  writeFileSync(SETTINGS_PATH, payload, "utf-8");
}

export async function openSettingsDialog(page: Page): Promise<void> {
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
}

export async function expectDialog(page: Page): Promise<void> {
  await expect(page.getByRole("dialog", {name: "设置"})).toBeVisible();
  // 快照加载完成的标志：首字段已渲染（load() 为异步，对话框先于数据显示）
  await page.locator('input[data-key="cad_timeout_seconds"]').waitFor();
}
