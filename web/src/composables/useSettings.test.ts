// 设置语言切换事务单测（PLAN-DM-021 Task 3，I18N-05/06）：
// 只有保存成功（PUT 200）才允许切换语言且恰好切换一次；选择/刷新、取消、
// 422/409/5xx 均不得切换；切换目标语言以响应快照的 ui_locale 为准。
// 语言切换唯一入口是 i18n 的 applyLocale：以 spy 断言调用次数与目标语言。
import {beforeEach, describe, expect, it, vi} from "vitest";

const {fetchSettingsMock, putSettingsMock, applyLocaleMock} = vi.hoisted(() => ({
  fetchSettingsMock: vi.fn(),
  putSettingsMock: vi.fn(),
  applyLocaleMock: vi.fn(),
}));

vi.mock("../api/settings", () => ({fetchSettings: fetchSettingsMock, putSettings: putSettingsMock}));
// 只 mock i18n 入口（applyLocale）；resolveLocale 来自纯逻辑模块 ../i18n/locale，不 mock
vi.mock("../i18n", () => ({applyLocale: applyLocaleMock}));

import {ApiError} from "../api/client";
import type {SettingsItem, SettingsSnapshot, SettingsValue} from "../api/settings";

function makeItem(key: string, value: SettingsValue): SettingsItem {
  return {key, control: "enum", value, default: "system", source: "file", hasFileOverride: false};
}

function makeSnapshot(uiLocale: SettingsValue, configRevision = 1): SettingsSnapshot {
  return {
    schemaVersion: 1,
    configRevision,
    items: [makeItem("ui_locale", uiLocale)],
    diagnostics: [],
    schemaBlocked: false,
  };
}

// useSettings 为模块级单例状态：每个用例重置模块后重新实例化，避免用例间串扰
async function freshUseSettings() {
  vi.resetModules();
  const module = await import("./useSettings");
  return module.useSettings();
}

beforeEach(() => {
  vi.clearAllMocks();
  applyLocaleMock.mockResolvedValue(undefined);
  vi.unstubAllGlobals();
});

describe("useSettings 语言切换事务", () => {
  it("load 只刷新快照，不触发语言切换（选择未保存/409 刷新不切换）", async () => {
    fetchSettingsMock.mockResolvedValue(makeSnapshot("en-US"));
    const {load} = await freshUseSettings();
    await load();
    expect(applyLocaleMock).not.toHaveBeenCalled();
  });

  it("PUT 成功且响应语言变化：恰好切换一次到响应快照语言，并整体替换快照", async () => {
    fetchSettingsMock.mockResolvedValue(makeSnapshot("zh-CN", 1));
    putSettingsMock.mockResolvedValue(makeSnapshot("en-US", 2));
    const {load, save, snapshot} = await freshUseSettings();
    await load();
    await save({"ui_locale": "en-US"}, []);
    expect(applyLocaleMock).toHaveBeenCalledTimes(1);
    expect(applyLocaleMock).toHaveBeenCalledWith("en-US");
    expect(snapshot.value?.configRevision).toBe(2); // 成功后用响应快照整体替换
  });

  it("PUT 成功但语言未变：不切换", async () => {
    fetchSettingsMock.mockResolvedValue(makeSnapshot("zh-CN", 1));
    putSettingsMock.mockResolvedValue(makeSnapshot("zh-CN", 2));
    const {load, save} = await freshUseSettings();
    await load();
    await save({"cad_timeout_seconds": 900}, []);
    expect(applyLocaleMock).not.toHaveBeenCalled();
  });

  it("切换目标以响应快照的 ui_locale 为准，而非提交值（system 按系统规则解析）", async () => {
    vi.stubGlobal("navigator", {languages: ["en-US"], language: "en-US"});
    fetchSettingsMock.mockResolvedValue(makeSnapshot("zh-CN", 1));
    putSettingsMock.mockResolvedValue(makeSnapshot("system", 2));
    const {load, save} = await freshUseSettings();
    await load();
    await save({"ui_locale": "en-US"}, []); // 提交值 en-US，但响应快照为 system
    expect(applyLocaleMock).toHaveBeenCalledTimes(1);
    expect(applyLocaleMock).toHaveBeenCalledWith("en-US"); // system + 英文系统 → en-US
  });

  it.each([
    [422, "SETTINGS_VALIDATION_FAILED"],
    [409, "SETTINGS_CONFLICT"],
    [500, "INTERNAL_ERROR"],
  ])("PUT %i 失败：不切换语言且快照保持不变", async (status, code) => {
    fetchSettingsMock.mockResolvedValue(makeSnapshot("zh-CN", 1));
    putSettingsMock.mockRejectedValue(new ApiError("保存失败", status, code));
    const {load, save, snapshot} = await freshUseSettings();
    await load();
    await expect(save({"ui_locale": "en-US"}, [])).rejects.toBeInstanceOf(ApiError);
    expect(applyLocaleMock).not.toHaveBeenCalled();
    expect(snapshot.value?.configRevision).toBe(1); // 失败不替换快照（本地编辑保留的前提）
  });

  it("快照未加载时 save 直接失败，不触发任何切换", async () => {
    const {save} = await freshUseSettings();
    await expect(save({"ui_locale": "en-US"}, [])).rejects.toThrow();
    expect(putSettingsMock).not.toHaveBeenCalled();
    expect(applyLocaleMock).not.toHaveBeenCalled();
  });
});
