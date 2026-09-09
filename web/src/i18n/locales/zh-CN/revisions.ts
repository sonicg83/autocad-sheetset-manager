// zh-CN 修订历史域语言资源（PLAN-DM-021 Task 8；ARCH-DM-005 §5.1）。
// 修订 ID/哈希/路径与 restore-preview 的 action 协议值保持原样；日期经 Intl 按语言区域格式化。
export default {
  ariaLabel: "修订历史",
  panel: {
    title: "永久修订",
    time: "时间",
    revision: "修订",
    resultSummary: "结果摘要",
    previewRestore: "恢复预览",
    confirmTitle: "恢复确认",
    fileConflict: "（当前文件冲突）",
    restoreAsNew: "恢复为新修订",
  },
  empty: {
    title: "暂无修订历史",
    desc: "发布首个变更后，此处会记录每个可恢复的修订版本。",
    action: "前往「图纸」标签发起首个变更，发布后即可在此恢复。",
  },
  confirm: {
    title: "确认恢复为新修订",
    message: "历史修订不会被覆盖。",
    confirmText: "确认恢复",
  },
  errors: {
    contextStale: "工作区或基准修订已变化，请重新生成恢复预览",
  },
} as const;
