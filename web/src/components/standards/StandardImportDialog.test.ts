// @vitest-environment happy-dom
// 标准包导入弹窗状态机（PLAN-DM-041 Task 7）：未选择 / 预检中 / 可确认 / 受阻 /
// 导入中 / 成功六态、空路径禁用、防重复提交、冲突与失败留在弹窗并保留路径、
// 换文件清除旧预检、过期凭证要求重新预检，以及无壳降级与桥迟到注入。
import {afterEach, describe, expect, it, vi, type Mock} from "vitest";
import {flushPromises, mount} from "@vue/test-utils";
import {createI18n} from "vue-i18n";
import StandardImportDialog from "./StandardImportDialog.vue";
import zhCNStandards from "../../i18n/locales/zh-CN/standards";
import zhCNErrors from "../../i18n/locales/zh-CN/errors";
import type {ImportPreviewResult, PublishedStandard} from "../../features/standards/types";

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {"zh-CN": {standards: zhCNStandards, errors: zhCNErrors}},
});

function preview(overrides: Partial<ImportPreviewResult> = {}): ImportPreviewResult {
  return {
    preview_id: "preview-1",
    expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    standard_id: "szmedi.gas",
    version: 3,
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    existing_versions: [
      {source: "official", version: 2},
      {source: "user", version: 1},
    ],
    diagnostics: [],
    can_import: true,
    ...overrides,
  };
}

type Harness = {
  previewImport: Mock<(path: string) => Promise<ImportPreviewResult>>;
  confirmImport: Mock<(previewId: string) => Promise<PublishedStandard>>;
  cancelImport: Mock<(previewId: string) => Promise<void>>;
  selectPath: Mock<(localizedDescription: string) => Promise<string | null | undefined>>;
};

function mountDialog(
  options: {
    shellAvailable?: boolean;
    previewResult?: ImportPreviewResult;
    confirmResult?: PublishedStandard;
    confirmError?: Error;
    selectResult?: string | null | undefined;
  } = {},
) {
  const harness: Harness = {
    previewImport: vi.fn(async (_path: string) => options.previewResult ?? preview()),
    confirmImport: vi.fn(async (_previewId: string) => {
      if (options.confirmError) throw options.confirmError;
      return options.confirmResult ?? {standard_id: "szmedi.gas", version: 3, name: "市政燃气施工图"};
    }),
    cancelImport: vi.fn(async (_previewId: string) => undefined),
    selectPath: vi.fn(async (_localizedDescription: string) => options.selectResult ?? null),
  };
  const wrapper = mount(StandardImportDialog, {
    props: {
      open: true,
      shellAvailable: options.shellAvailable ?? true,
      selectPath: harness.selectPath,
      previewImport: harness.previewImport,
      confirmImport: harness.confirmImport,
      cancelImport: harness.cancelImport,
    },
    global: {plugins: [i18n]},
  });
  return {wrapper, harness};
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("StandardImportDialog", () => {
  it("未选择文件时预检与确认都不可用", () => {
    const {wrapper} = mountDialog();
    expect(wrapper.get('[data-testid="import-preview-button"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="import-confirm-button"]').attributes("disabled")).toBeDefined();
  });

  it("原生选择取消返回 null：不发起预检", async () => {
    const {wrapper, harness} = mountDialog({selectResult: null});
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    expect(harness.previewImport).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="import-preview"]').exists()).toBe(false);
  });

  it("预检中防重复提交：预检按钮在响应前禁用且只调用一次", async () => {
    let release: (value: ImportPreviewResult) => void = () => undefined;
    const pending = new Promise<ImportPreviewResult>(resolve => {
      release = resolve;
    });
    const {wrapper, harness} = mountDialog({selectResult: "C:\\标准包\\a.dststandard"});
    harness.previewImport.mockReturnValueOnce(pending);
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="import-preview-button"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    expect(harness.previewImport).toHaveBeenCalledTimes(1);
    release(preview());
    await flushPromises();
    expect(wrapper.get('[data-testid="import-confirm-button"]').attributes("disabled")).toBeUndefined();
  });

  it("受阻预检展示诊断、禁用确认且不关闭弹窗", async () => {
    const {wrapper} = mountDialog({
      selectResult: "C:\\标准包\\a.dststandard",
      previewResult: preview({
        preview_id: null,
        expires_at: null,
        can_import: false,
        diagnostics: [{code: "STANDARD_VERSION_EXISTS", severity: "error", message: "同一标准 ID 与版本已存在"}],
      }),
    });
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="import-diagnostics"]').text()).toContain("STANDARD_VERSION_EXISTS");
    expect(wrapper.get('[data-testid="import-confirm-button"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="import-selected-path"]').exists()).toBe(true);
  });

  it("确认导入成功进入成功态、发出 imported 且不清空弹窗", async () => {
    const {wrapper, harness} = mountDialog({selectResult: "C:\\标准包\\a.dststandard"});
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-confirm-button"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="import-success"]').exists()).toBe(true);
    expect(harness.confirmImport).toHaveBeenCalledWith("preview-1");
    expect(wrapper.emitted("imported")).toHaveLength(1);
  });

  it("确认失败（预检后库状态变化）留在弹窗、保留路径并清除旧凭证", async () => {
    const {wrapper, harness} = mountDialog({
      selectResult: "C:\\标准包\\a.dststandard",
      confirmError: new Error("STANDARD_VERSION_EXISTS: 同一标准 ID 与版本已存在"),
    });
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-confirm-button"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="import-error"]').text()).toContain("STANDARD_VERSION_EXISTS");
    expect(harness.cancelImport).toHaveBeenCalledWith("preview-1");
    // 路径保留、旧预检清除：用户可直接重新预检
    expect(wrapper.get<HTMLInputElement>('[data-testid="import-selected-path"]').element.value).toBe(
      "C:\\标准包\\a.dststandard",
    );
    expect(wrapper.find('[data-testid="import-preview"]').exists()).toBe(false);
  });

  it("更换文件清除旧预检并取消服务端凭证", async () => {
    const {wrapper, harness} = mountDialog({selectResult: "C:\\标准包\\a.dststandard"});
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    harness.selectPath.mockResolvedValueOnce("C:\\标准包\\b.dststandard");
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    expect(harness.cancelImport).toHaveBeenCalledWith("preview-1");
    expect(wrapper.find('[data-testid="import-preview"]').exists()).toBe(false);
  });

  it("凭证过期后清除旧预检并要求重新预检", async () => {
    vi.useFakeTimers();
    const {wrapper} = mountDialog({
      selectResult: "C:\\标准包\\a.dststandard",
      previewResult: preview({expires_at: new Date(Date.now() + 1000).toISOString()}),
    });
    try {
      await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
      await flushPromises();
      await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
      await flushPromises();
      expect(wrapper.get('[data-testid="import-confirm-button"]').attributes("disabled")).toBeUndefined();
      await vi.advanceTimersByTimeAsync(16000);
      await flushPromises();
      expect(wrapper.get('[data-testid="import-error"]').text()).toContain("重新预检");
      expect(wrapper.find('[data-testid="import-preview"]').exists()).toBe(false);
      expect(wrapper.get('[data-testid="import-confirm-button"]').attributes("disabled")).toBeDefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it("无桌面壳时显示明确标注的本机路径开发态；桥就绪后离开该模式", async () => {
    const {wrapper} = mountDialog({shellAvailable: false});
    expect(wrapper.find('[data-testid="import-dev-fallback"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="import-choose-file"]').exists()).toBe(false);
    await wrapper.setProps({shellAvailable: true});
    expect(wrapper.find('[data-testid="import-dev-fallback"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="import-choose-file"]').exists()).toBe(true);
  });

  it("取消按钮清理在途预检凭证并请求关闭", async () => {
    const {wrapper, harness} = mountDialog({selectResult: "C:\\标准包\\a.dststandard"});
    await wrapper.get('[data-testid="import-choose-file"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-testid="import-preview-button"]').trigger("click");
    await flushPromises();
    await wrapper.findAll("button").find(button => button.text() === "取消")!.trigger("click");
    await flushPromises();
    expect(harness.cancelImport).toHaveBeenCalledWith("preview-1");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });
});
