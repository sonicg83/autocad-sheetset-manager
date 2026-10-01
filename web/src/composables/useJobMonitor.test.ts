// @vitest-environment happy-dom
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import {ref} from "vue";
import type {Job, Workspace} from "../api/contracts";
import {useToast, type Toast} from "./useToast";

const {requestMock} = vi.hoisted(() => ({requestMock: vi.fn()}));

vi.mock("../api/client", () => ({request: requestMock}));
vi.mock("vue-i18n", () => ({
  useI18n: () => ({t: (key: string, params?: Record<string, unknown>) => `${key} ${Object.values(params ?? {}).join(" ")}`.trim()}),
}));

import {useJobMonitor} from "./useJobMonitor";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void | Promise<void>) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(readonly url: string) { FakeEventSource.instances.push(this); }
  async send(job: Partial<Job>) {
    await this.onmessage?.({data: JSON.stringify(job)} as MessageEvent<string>);
  }
  fail() { this.onerror?.(); }
}

function makeJob(status: string, overrides: Partial<Job> = {}): Job {
  return {id: "job-1", status, workspace_id: "workspace-1", error_code: null, error_detail: null, ...overrides} as Job;
}

function makeMonitor(extra: {pushToast?: (toast: Omit<Toast, "id">) => void; shouldSuppress?: () => boolean} = {}) {
  const pushToast = vi.fn<(toast: Omit<Toast, "id">) => void>();
  const onJobSucceeded = vi.fn(async () => {});
  const error = ref("");
  const workspace = ref({id: "workspace-1"} as Workspace);
  const monitor = useJobMonitor({isWorkspaceLoading: ref(false), workspace, onJobSucceeded, error, pushToast: extra.pushToast ?? pushToast, shouldSuppress: extra.shouldSuppress});
  return {monitor, pushToast, onJobSucceeded, error, workspace};
}

beforeEach(() => {
  requestMock.mockReset();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useJobMonitor 终态通知", () => {
  it("duplicate_terminal_events_notify_once_per_attempt", async () => {
    const {monitor, pushToast, onJobSucceeded} = makeMonitor();
    monitor.watchJob("job-1", "workspace-1");
    const events = FakeEventSource.instances[0]!;
    const succeeded = makeJob("SUCCEEDED");

    await events.send(succeeded);
    await events.send(succeeded);

    expect(pushToast).toHaveBeenCalledTimes(1);
    expect(onJobSucceeded).toHaveBeenCalledTimes(1);
    expect(events.close).toHaveBeenCalledTimes(1);
  });

  it("polling_fallback_does_not_repeat_notification", async () => {
    const {monitor, pushToast} = makeMonitor();
    requestMock.mockResolvedValue(makeJob("FAILED", {error_code: "PUBLISH_FAILED", error_detail: "整批未发布"}));
    monitor.watchJob("job-1", "workspace-1");
    const events = FakeEventSource.instances[0]!;
    events.fail();

    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(3000);

    expect(monitor.connectionMode.value).toBe("polling");
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(monitor.job.value?.status).toBe("FAILED");
    expect(pushToast).toHaveBeenCalledTimes(1);
    expect(pushToast.mock.calls[0]![0]).toMatchObject({type: "fail", body: expect.stringContaining("PUBLISH_FAILED")});
  });

  it("stale_subscription_has_no_effect", async () => {
    const {monitor, pushToast} = makeMonitor();
    monitor.watchJob("old-job", "workspace-1");
    const oldEvents = FakeEventSource.instances[0]!;
    monitor.watchJob("new-job", "workspace-1");
    const currentEvents = FakeEventSource.instances[1]!;

    await oldEvents.send(makeJob("FAILED", {id: "old-job"}));
    expect(monitor.job.value).toBeNull();
    expect(pushToast).not.toHaveBeenCalled();

    await currentEvents.send(makeJob("NEEDS_REVIEW", {id: "new-job", error_code: "MANUAL_REVIEW"}));
    expect(monitor.job.value?.id).toBe("new-job");
    expect(monitor.job.value?.status).toBe("NEEDS_REVIEW");
    expect(pushToast).toHaveBeenCalledTimes(1);
  });

  it("NEEDS_REVIEW 通知保留目标与恢复信息，尝试重试也不清掉 blocker", async () => {
    const {monitor, pushToast, error} = makeMonitor();
    monitor.watchJob("job-1", "workspace-1");
    const events = FakeEventSource.instances[0]!;
    await events.send(makeJob("NEEDS_REVIEW", {error_code: "PUBLISH_STATE_UNCERTAIN", error_detail: "目标文件保留，需核对发布日志后重新打开。"}));
    const firstNotice = pushToast.mock.calls[0]![0] as {type: string; body: string; jumpTab: string};

    await monitor.retryJob();

    expect(firstNotice).toMatchObject({type: "fail", jumpTab: "prog"});
    expect(firstNotice.body).toContain("PUBLISH_STATE_UNCERTAIN");
    expect(firstNotice.body).toContain("目标文件保留");
    expect(monitor.job.value?.status).toBe("NEEDS_REVIEW");
    expect(error.value).toBe("jobs.errors.needsReviewRetry");
    expect(requestMock).not.toHaveBeenCalled();
  });

  it("同一任务重试后新 attempt 可以重新通知", async () => {
    const {monitor, pushToast} = makeMonitor();
    requestMock.mockResolvedValue(makeJob("QUEUED"));
    monitor.watchJob("job-1", "workspace-1");
    await FakeEventSource.instances[0]!.send(makeJob("FAILED"));
    await monitor.retryJob();
    expect(requestMock).toHaveBeenCalledWith("/api/jobs/job-1/retry", {method: "POST"});
    await FakeEventSource.instances[1]!.send(makeJob("FAILED"));

    expect(pushToast).toHaveBeenCalledTimes(2);
  });

  it("failure_and_conflict_remain_visible_until_recovery", async () => {
    const notices = useToast();
    const {monitor} = makeMonitor({pushToast: notices.pushToast});
    monitor.watchJob("job-1", "workspace-1");
    await FakeEventSource.instances[0]!.send(makeJob("FAILED", {error_code: "PUBLISH_REVISION_CONFLICT", error_detail: "目标文件保留，重新读取修订后再操作。"}));
    const failure = notices.toasts.value.find(item => item.type === "fail");

    vi.advanceTimersByTime(60_000);
    expect(failure?.body).toContain("PUBLISH_REVISION_CONFLICT");
    expect(failure?.body).toContain("目标文件保留");
    expect(notices.toasts.value).toContain(failure);
    expect(monitor.job.value?.status).toBe("FAILED");

    monitor.watchJob("job-1", "workspace-1");
    await FakeEventSource.instances[1]!.send(makeJob("SUCCEEDED"));
    expect(monitor.job.value?.status).toBe("SUCCEEDED");
    expect(notices.toasts.value).toContain(failure);
  });

  it("任务浮层停留在实施进度时不弹通知，任务终态仍保留", async () => {
    const shouldSuppress = vi.fn(() => true);
    const {monitor, pushToast} = makeMonitor({shouldSuppress});
    monitor.watchJob("job-1", "workspace-1");
    await FakeEventSource.instances[0]!.send(makeJob("FAILED", {error_code: "PUBLISH_FAILED"}));

    expect(pushToast).not.toHaveBeenCalled();
    expect(monitor.job.value?.status).toBe("FAILED");
  });
});
