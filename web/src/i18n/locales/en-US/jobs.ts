// en-US 任务域语言资源（PLAN-DM-021 Task 8；ARCH-DM-005 §5.1）。
// 键集合必须与 zh-CN 完全一致（check:i18n 门禁）；状态码 → 语义键只在展示层映射，
// 未知码回退原码；错误码、DWG 名与后端消息（用户数据/协议字段）保持原样。
export default {
  job: {
    title: "Job {id}",
    noChange: "(no change)",
    attempt: "Attempt {attempt}",
    retry: "Safe Retry",
  },
  connection: {
    sse: "SSE",
    polling: "Polling",
  },
  status: {
    queued: "Queued",
    running: "Running",
    succeeded: "Succeeded",
    failed: "Failed",
    rolledBack: "Rolled back",
    blockedFileLock: "File locked",
    needsReview: "Needs review",
    pending: "Pending",
    skipped: "Skipped",
  },
  files: {
    dwg: "DWG",
    operation: "Operation",
    status: "Status",
    progress: "Progress",
    started: "Started",
    finished: "Finished",
    duration: "Duration",
    error: "Error",
    logSummary: "Core Console output log",
    durationMs: "{value} ms",
  },
  toasts: {
    succeededTitle: "Task succeeded",
    succeededBody: "The task finished publishing",
    needsReviewTitle: "Needs manual review",
    needsReviewBody: "The publish state needs manual review; direct retry is disabled",
    failedTitle: "Task failed",
    failedBody: "{code}; the batch was not published",
    failedBodyNoCode: "The batch was not published",
  },
  errors: {
    needsReviewRetry: "The publish state needs manual review; direct retry is disabled",
  },
} as const;
