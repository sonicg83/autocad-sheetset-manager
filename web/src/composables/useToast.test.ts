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
});
