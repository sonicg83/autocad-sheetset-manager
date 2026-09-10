// extensions 域语言资源测试（PLAN-DM-020 Task 10 Step 1 / ARCH-DM-005 §5.1）。
// 锁定三类键集合：扩展清单 name_key/description_key、生命周期状态九值、
// 后端扩展错误 message_key（errors.extension.*）。
// 与后端的事实来源对称：
// - src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml（name_key/description_key）
// - src/dst_manager/interfaces/extension_contracts.py 的 ExtensionLifecycleStatus / EXTENSION_MESSAGE_KEYS
// - src/dst_manager/application/extensions/runtime.py 的 key_override("errors.extension.artifactNotFound")
// - src/dst_manager/extensions/builtin/sheet_catalog/preview.py 的 preferenceSaveFailed 键
// 中英文键集合完全相同另由 check:i18n 门禁全局强制；本测试把“后端键都有前端承接”
// 固化进测试层，防止后端先加键、前端漏登记时静默渲染键名原文。
import {describe, expect, it} from "vitest";
import enExtensions from "./locales/en-US/extensions";
import enErrors from "./locales/en-US/errors";
import zhExtensions from "./locales/zh-CN/extensions";
import zhErrors from "./locales/zh-CN/errors";

function flattenKeys(prefix: string, value: Record<string, unknown>, out: string[] = []): string[] {
  for (const [key, child] of Object.entries(value)) {
    const keyPath = prefix === "" ? key : `${prefix}.${key}`;
    if (child !== null && typeof child === "object") flattenKeys(keyPath, child as Record<string, unknown>, out);
    else out.push(keyPath);
  }
  return out;
}

// 后端 ExtensionLifecycleStatus 九值（extension_contracts.py）
const LIFECYCLE_STATUSES = [
  "DISCOVERED", "DISABLED", "STARTING", "AVAILABLE", "WAITING_DEPENDENCY",
  "INCOMPATIBLE", "FAILED", "STOPPING", "STOPPED",
] as const;

// 后端扩展错误文案键全集：EXTENSION_MESSAGE_KEYS 十平台码 + runtime.py Artifact 404
// key_override + preview.py 偏好保存失败 warning（errors 域 extension 小节承接）
const BACKEND_ERROR_KEYS = [
  "notFound", "disabled", "incompatible", "capabilityUnavailable", "settingsInvalid",
  "actionNotFound", "saveGrantInvalid", "exportDestinationChanged", "repreviewRequired",
  "artifactWriteFailed", "artifactNotFound", "preferenceSaveFailed",
] as const;

describe("extensions 域语言资源（PLAN-DM-020 Task 10）", () => {
  it("中英文键集合完全相同", () => {
    expect(flattenKeys("", zhExtensions).sort()).toEqual(flattenKeys("", enExtensions).sort());
  });

  it("内置扩展清单的 name_key/description_key 两语言都有承接", () => {
    for (const key of ["sheetCatalog.name", "sheetCatalog.description"]) {
      expect(flattenKeys("", zhExtensions)).toContain(key);
      expect(flattenKeys("", enExtensions)).toContain(key);
    }
  });

  it("生命周期状态九值逐一登记", () => {
    for (const status of LIFECYCLE_STATUSES) {
      expect(flattenKeys("", zhExtensions)).toContain(`status.${status}`);
      expect(flattenKeys("", enExtensions)).toContain(`status.${status}`);
    }
  });

  it("后端扩展错误键（errors.extension.*）中英文集合完全相同且全部承接", () => {
    const zhSection = flattenKeys("", zhErrors.extension as Record<string, unknown>);
    const enSection = flattenKeys("", enErrors.extension as Record<string, unknown>);
    expect(zhSection.sort()).toEqual(enSection.sort());
    for (const key of BACKEND_ERROR_KEYS) {
      expect(zhSection).toContain(key);
    }
  });
});
