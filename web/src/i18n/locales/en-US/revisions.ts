// en-US 修订历史域语言资源（PLAN-DM-021 Task 8；ARCH-DM-005 §5.1）。
// 键集合必须与 zh-CN 完全一致（check:i18n 门禁）；修订 ID/哈希/路径与
// restore-preview 的 action 协议值保持原样；日期经 Intl 按语言区域格式化。
export default {
  ariaLabel: "Revision History",
  panel: {
    title: "Permanent Revisions",
    time: "Time",
    revision: "Revision",
    resultSummary: "Result summary",
    previewRestore: "Restore Preview",
    confirmTitle: "Restore Confirmation",
    fileConflict: "(current file conflict)",
    restoreAsNew: "Restore as New Revision",
  },
  empty: {
    title: "No revision history yet",
    desc: "After you publish the first change, every recoverable revision is recorded here.",
    action: "Go to the Sheets tab to make the first change; it can be restored here after publishing.",
  },
  confirm: {
    title: "Confirm Restore as New Revision",
    message: "Historical revisions will not be overwritten.",
    confirmText: "Confirm Restore",
  },
  errors: {
    contextStale: "The workspace or baseline revision has changed; generate the restore preview again",
  },
} as const;
