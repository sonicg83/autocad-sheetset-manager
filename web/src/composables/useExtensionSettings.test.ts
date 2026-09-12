// 单个扩展设置状态所有者的单测（PLAN-DM-025 任务 7 修复轮）：
// 两条服务端 409 的收口必须在组合层可测，而不是只靠 E2E 的整条链路——
// ① 修订冲突横幅回显「服务端响应里的稳定码」，前端不得写死字面量；
// ② 高版本只读判定必须与「读取只读横幅数据的那次刷新」解耦：刷新失败仍粘住只读，
//    否则会退回陈旧的可写快照，保存按钮可用且每次保存都重复同一个 409（确定性死循环）；
// ③ 修订冲突后的刷新失败必须在状态层留下「快照可能已过期」的可观测事实（loadFailed），
//    否则 .cfg 级别的陈旧提示没有数据源，冲突横幅会叫用户按陈旧徽标重试。
import {beforeEach, describe, expect, it, vi} from "vitest";

const {fetchMock, putMock} = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  putMock: vi.fn(),
}));

vi.mock("../api/extensions", () => ({
  fetchExtensionSettings: fetchMock,
  putExtensionSettings: putMock,
}));
// 按 useSettings.test.ts / api/settings.test.ts 先例 mock i18n 入口（api/client 依赖它渲染
// 已知错误）：单测不需要语言包，只为避免经 i18n/index.ts 把 App.vue 拉进 node 环境
vi.mock("../i18n", () => ({i18n: {global: {t: (key: string) => key, te: () => false}}}));

import {ApiError} from "../api/client";
import type {ExtensionSettingsView} from "../api/contracts";
import {useExtensionSettings} from "./useExtensionSettings";

function view(overrides: Partial<ExtensionSettingsView> = {}): ExtensionSettingsView {
  return {
    schema_version: 1,
    revision: 0,
    value: {batch_limit: 50},
    effective_value: {batch_limit: 50},
    read_only: false,
    diagnostic_code: null,
    items: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useExtensionSettings 服务端 409 收口", () => {
  it("修订冲突：横幅的码取服务端响应，本地输入保留且快照被刷新", async () => {
    // 探针码刻意不同于设置 PUT 的冲突码（生产为 EXTENSION_SETTINGS_INVALID，见
    // application/extensions/settings.py 的 SettingsRevisionConflictError 映射）：
    // 本用例证明的是「原样透传线上返回的码」，不主张设置 PUT 会发哪一个码
    const wireCode = "EXTENSION_SETTINGS_CHANGED";
    fetchMock.mockResolvedValueOnce(view()).mockResolvedValueOnce(view({revision: 1}));
    putMock.mockRejectedValue(new ApiError(
      "设置已被其他保存更新", 409, wireCode,
      undefined, undefined, undefined, {expected_revision: 0, current_revision: 1},
    ));
    const state = useExtensionSettings("demo.frame-update");
    await state.load();
    state.setField("batch_limit", 70);

    await state.save();

    expect(state.conflict.value).toEqual({code: wireCode, expectedRevision: 0, currentRevision: 1});
    expect(state.edits.value).toEqual({batch_limit: 70}); // 本地输入不丢
    expect(fetchMock).toHaveBeenCalledTimes(2); // 冲突后就地刷新服务端快照
  });

  it("高版本只读：随后的刷新失败也不撤销只读判定，且不再重复提交必然 409 的保存", async () => {
    fetchMock.mockResolvedValueOnce(view()); // 首次加载：服务端仍报告可写快照
    putMock.mockRejectedValue(new ApiError("已存设置 schema 更高", 409, "EXTENSION_SETTINGS_SCHEMA_NEWER"));
    const state = useExtensionSettings("demo.frame-update");
    await state.load();
    state.setField("batch_limit", 70);
    fetchMock.mockRejectedValue(new Error("refresh failed")); // 只读横幅数据的那次刷新失败

    await state.save();

    // 只读粘住 + 本地编辑被丢弃（只读不可脏）+ 刷新失败可见；诊断码也随粘性判定回显，
    // 不依赖那次失败刷新后的陈旧快照（否则横幅只剩空码）
    expect(state.readOnly.value).toBe(true);
    expect(state.readOnlyCode.value).toBe("EXTENSION_SETTINGS_SCHEMA_NEWER");
    expect(state.edits.value).toEqual({});
    expect(state.dirty.value).toBe(false);
    expect(state.loadFailed.value).toBe(true);

    await state.save(); // 只读态下再保存是 no-op：不产生第二个必然 409 的请求
    expect(putMock).toHaveBeenCalledTimes(1);
  });

  it("修订冲突后的刷新失败：快照与冲突都保留，只留下可见的刷新失败事实", async () => {
    fetchMock.mockResolvedValueOnce(view()); // 首次加载成功：冲突横幅要回显的陈旧快照
    putMock.mockRejectedValue(new ApiError(
      "设置已被其他保存更新", 409, "EXTENSION_SETTINGS_INVALID",
      undefined, undefined, undefined, {expected_revision: 0, current_revision: 1},
    ));
    const state = useExtensionSettings("demo.frame-update");
    await state.load();
    state.setField("batch_limit", 70);
    fetchMock.mockRejectedValue(new Error("refresh failed")); // 冲突后的那次刷新失败

    await state.save();

    // 快照降级保留（不因刷新失败清空子视图），本地编辑不被丢弃
    expect(state.snapshot.value).toEqual(view());
    expect(state.edits.value).toEqual({batch_limit: 70});
    expect(state.conflict.value).toEqual({code: "EXTENSION_SETTINGS_INVALID", expectedRevision: 0, currentRevision: 1});
    // 「下方内容可能已过期」的可观测事实：呈现层据此在 .cfg 级别就地提示
    expect(state.loadFailed.value).toBe(true);
  });
});
