import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {useToast} from "./useToast";

describe("useToast 终态通知保留", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("成功通知显示 5000 毫秒后自动关闭", () => {
    const toast = useToast();
    toast.pushToast({type: "ok", title: "完成", body: "任务已完成"});

    vi.advanceTimersByTime(4999);
    expect(toast.toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toast.toasts.value).toEqual([]);
  });

  it("失败通知不会自动关闭，也不会被后续成功通知挤掉", () => {
    const toast = useToast();
    toast.pushToast({type: "fail", title: "任务失败", body: "整批未发布"});
    for (let index = 0; index < 6; index += 1) {
      toast.pushToast({type: "ok", title: `成功 ${index}`, body: "已完成"});
    }

    vi.advanceTimersByTime(5000);
    expect(toast.toasts.value.some(item => item.type === "fail" && item.body === "整批未发布")).toBe(true);
    expect(toast.toasts.value.filter(item => item.type === "fail")).toHaveLength(1);
  });

  it("失败通知只由用户按 id 关闭", () => {
    const toast = useToast();
    toast.pushToast({type: "fail", title: "冲突", body: "保留目标与恢复信息"});
    const id = toast.toasts.value[0]!.id;

    vi.advanceTimersByTime(60_000);
    expect(toast.toasts.value).toHaveLength(1);
    toast.dismiss(id);
    expect(toast.toasts.value).toEqual([]);
  });

  it.each([4, 8])("保留 %i 条失败通知时，新成功通知仍显示完整五秒", failureCount => {
    const toast = useToast();
    for (let index = 0; index < failureCount; index += 1) {
      toast.pushToast({type: "fail", title: `失败 ${index}`, body: "保留恢复信息"});
    }
    const failureIds = toast.toasts.value.map(item => item.id);
    toast.pushToast({type: "ok", title: "新任务成功", body: "任务已完成发布"});

    expect(toast.toasts.value.at(-1)).toMatchObject({type: "ok", title: "新任务成功"});
    vi.advanceTimersByTime(4999);
    expect(toast.toasts.value.some(item => item.title === "新任务成功")).toBe(true);
    vi.advanceTimersByTime(1);
    expect(toast.toasts.value.map(item => item.id)).toEqual(failureIds);
  });

  it("超过通常上限时清理旧成功通知，保留新通知和全部失败", () => {
    const toast = useToast();
    toast.pushToast({type: "ok", title: "旧成功", body: "已有结果"});
    for (let index = 0; index < 3; index += 1) {
      toast.pushToast({type: "fail", title: `失败 ${index}`, body: "保留恢复信息"});
    }
    toast.pushToast({type: "ok", title: "新成功", body: "新结果"});

    expect(toast.toasts.value.map(item => item.title)).toEqual(["失败 0", "失败 1", "失败 2", "新成功"]);
  });
});
