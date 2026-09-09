// zh-CN 任务域语言资源（PLAN-DM-021 Task 8；ARCH-DM-005 §5.1）。
// SSE/任务 payload 保持稳定状态码（I18N-12）：状态码 → 语义键只在展示层映射，
// 未知码回退原码；错误码、DWG 名与后端消息（用户数据/协议字段）保持原样。
export default {
  job: {
    title: "任务 {id}",
    noChange: "（无变更）",
    attempt: "第 {attempt} 次",
    retry: "安全重试",
  },
  connection: {
    sse: "SSE",
    polling: "轮询",
  },
  status: {
    queued: "已排队",
    running: "执行中",
    succeeded: "已成功",
    failed: "已失败",
    rolledBack: "已回滚",
    blockedFileLock: "文件被占用",
    needsReview: "需人工检查",
    pending: "待执行",
    skipped: "已跳过",
  },
  files: {
    dwg: "DWG",
    operation: "操作",
    status: "状态",
    progress: "进度",
    started: "开始",
    finished: "结束",
    duration: "耗时",
    error: "错误",
    logSummary: "Core Console 输出日志",
    durationMs: "{value} ms",
  },
  toasts: {
    succeededTitle: "任务成功",
    succeededBody: "任务已完成发布",
    needsReviewTitle: "需人工检查",
    needsReviewBody: "发布状态需要人工检查，禁止直接重试",
    failedTitle: "任务失败",
    failedBody: "{code}，整批未发布",
    failedBodyNoCode: "整批未发布",
  },
  errors: {
    needsReviewRetry: "发布状态需要人工检查，禁止直接重试",
  },
} as const;
