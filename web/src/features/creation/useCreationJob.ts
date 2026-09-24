// 创建任务进度监视（PLAN-DM-036 Task 9）。
//
// 为什么不复用 `useJobMonitor`：创建任务在登记完成前**没有普通工作区**（Task 6 契约，
// `jobs.workspace_id` 为 NULL），而 `useJobMonitor.monitorMatches` 按工作区身份匹配，
// 无工作区时任何响应都会被判为「不属于当前现场」。因此这里只补一层创建专用的订阅，
// 并且**复用同一份终态判定**（`useJobMonitor.TERMINAL_JOB_STATUSES`）与同一个任务面板
// 组件（`components/JobStatusPanel.vue`）——终态集合与呈现都不在创建域另写一份。
//
// 订阅与普通任务同形：SSE 优先，断线回退轮询；终态只通知一次（成功带新建工作区身份）。
import {ref, type Ref} from "vue";
import {request} from "../../api/client";
import {isTerminalJobStatus} from "../../composables/useJobMonitor";
import type {Job} from "../../api/contracts";

export interface CreationJobMonitor {
  /** 最近一次创建任务状态（入队响应或订阅到的最新状态）。 */
  job: Ref<Job | null>;
  /** 连接方式：`sse` 正常、`polling` 为回退态（展示层映射文案）。 */
  connectionMode: Ref<"sse" | "polling">;
  /** 订阅一个已入队的创建任务（入队响应即首个状态）。 */
  watch(job: Job): void;
  /** 使在途订阅失效；`clear` 为真时同时清空任务状态（离开向导/切换标准）。 */
  invalidate(clear?: boolean): void;
}

export function useCreationJob(options: {
  /** 任务成功后的唯一后续动作：用返回的 `workspace_id` 切换普通工作区。 */
  onSucceeded: (workspaceId: string) => void | Promise<void>;
  /** 任务到达非成功终态：旧预览必须失效，草稿与诊断保留供修正后重试。 */
  onFailed: () => void;
}): CreationJobMonitor {
  const job = ref<Job | null>(null);
  const connectionMode = ref<"sse" | "polling">("sse");
  let generation = 0;
  let events: EventSource | null = null;
  let pollTimer: number | null = null;

  function invalidate(clear = false): number {
    generation += 1;
    events?.close();
    events = null;
    if (pollTimer !== null) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (clear) job.value = null;
    return generation;
  }

  /** 终态处理：只按后端终态响应决定成功切换或保留草稿重试。 */
  async function settle(result: Job): Promise<void> {
    if (result.status === "SUCCEEDED") {
      const workspaceId = result.workspace_id ?? "";
      if (workspaceId !== "") await options.onSucceeded(workspaceId);
      return;
    }
    options.onFailed();
  }

  function schedulePoll(id: string, started: number): void {
    if (started !== generation) return;
    if (pollTimer !== null) clearTimeout(pollTimer);
    pollTimer = window.setTimeout(() => {
      pollTimer = null;
      void pollJob(id, started);
    }, 1000);
  }

  async function pollJob(id: string, started: number): Promise<void> {
    if (started !== generation) return;
    try {
      const result = await request<Job>(`/api/jobs/${encodeURIComponent(id)}`);
      if (started !== generation) return;
      job.value = result;
      if (!isTerminalJobStatus(result.status)) {
        schedulePoll(id, started);
        return;
      }
      await settle(result);
    } catch {
      // 轮询失败不改变任务状态：保留最后一次已知状态，由用户决定是否重试
      schedulePoll(id, started);
    }
  }

  function watch(next: Job): void {
    job.value = next;
    const id = next.id ?? "";
    if (id === "") return;
    const started = invalidate(false);
    connectionMode.value = "sse";
    if (typeof EventSource === "undefined") {
      connectionMode.value = "polling";
      schedulePoll(id, started);
      return;
    }
    const source = new EventSource(`/api/jobs/${encodeURIComponent(id)}/events`);
    events = source;
    source.onmessage = async event => {
      if (started !== generation) return;
      const result = JSON.parse(event.data) as Job;
      if (started !== generation) return;
      job.value = result;
      if (!isTerminalJobStatus(result.status)) return;
      source.close();
      if (events === source) events = null;
      await settle(result);
    };
    source.onerror = () => {
      if (started !== generation) return;
      source.close();
      if (events === source) events = null;
      connectionMode.value = "polling";
      schedulePoll(id, started);
    };
  }

  return {job, connectionMode, watch, invalidate};
}
