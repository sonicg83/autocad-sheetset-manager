// en-US 扩展域语言资源（PLAN-DM-020 Task 10；ARCH-DM-005 §5.1 / ARCH-DM-006 §7）。
// 键集合必须与 zh-CN 完全一致（check:i18n 门禁）；语义对应关系见 zh-CN 文件头注释。
export default {
  sheetCatalog: {
    name: "Sheet Catalog",
    description: "Generate a configurable sheet catalog from the current workspace snapshot and export it as an XLSX file",
  },
  status: {
    DISCOVERED: "Discovered",
    DISABLED: "Disabled",
    STARTING: "Starting",
    AVAILABLE: "Available",
    WAITING_DEPENDENCY: "Waiting for dependency",
    INCOMPATIBLE: "Incompatible",
    FAILED: "Failed",
    STOPPING: "Stopping",
    STOPPED: "Stopped",
  },
  page: {
    ready: "The extension page is loaded; template configuration and export arrive in a later release.",
    disable: "Disable extension",
  },
};
