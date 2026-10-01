// @vitest-environment happy-dom
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import type {Job} from "../../api/contracts";

const {requestMock} = vi.hoisted(() => ({requestMock: vi.fn()}));
vi.mock("../../api/client", () => ({request: requestMock}));

import {useCreationJob} from "./useCreationJob";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void | Promise<void>) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(readonly url: string) { FakeEventSource.instances.push(this); }
  async send(job: Partial<Job>) { await this.onmessage?.({data: JSON.stringify(job)} as MessageEvent<string>); }
}

beforeEach(() => {
  requestMock.mockReset();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useFakeTimers();
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("useCreationJob 终态代次", () => {
  it("duplicate_terminal_events_notify_once_per_attempt", async () => {
    const onSucceeded = vi.fn();
    const onFailed = vi.fn();
    const monitor = useCreationJob({onSucceeded, onFailed});
    const queued = {id: "creation-1", status: "QUEUED"} as Job;
    monitor.watch(queued);
    const events = FakeEventSource.instances[0]!;

    await events.send({id: "creation-1", status: "SUCCEEDED", workspace_id: "workspace-1"});
    await events.send({id: "creation-1", status: "SUCCEEDED", workspace_id: "workspace-1"});

    expect(onSucceeded).toHaveBeenCalledTimes(1);
    expect(onSucceeded).toHaveBeenCalledWith("workspace-1");
    expect(onFailed).not.toHaveBeenCalled();
  });

  it("同一任务的新监视代次可以再次处理终态", async () => {
    const onFailed = vi.fn();
    const monitor = useCreationJob({onSucceeded: vi.fn(), onFailed});
    const failed = {id: "creation-1", status: "FAILED"} as Job;
    monitor.watch(failed);
    await FakeEventSource.instances[0]!.send(failed);
    monitor.watch(failed);
    await FakeEventSource.instances[1]!.send(failed);

    expect(onFailed).toHaveBeenCalledTimes(2);
  });
});
