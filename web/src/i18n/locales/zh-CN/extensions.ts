// zh-CN 扩展域语言资源（PLAN-DM-020 Task 10；ARCH-DM-005 §5.1 / ARCH-DM-006 §7）。
// 承载扩展页面贡献的宿主侧文案：内置扩展清单的 name_key/description_key 指向
// 本域（src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml），
// 生命周期状态按后端 ExtensionLifecycleStatus 九值逐一登记。
// 键集合必须与 en-US 完全一致（check:i18n 门禁）；扩展平台错误的 message_key
// （errors.extension.*）登记在 errors 域的 extension 小节，与后端目录对称。
export default {
  sheetCatalog: {
    name: "图纸目录",
    description: "从当前工作区快照生成可配置的图纸目录表，并导出为 XLSX 文件",
  },
  status: {
    DISCOVERED: "已发现",
    DISABLED: "已停用",
    STARTING: "正在启动",
    AVAILABLE: "可用",
    WAITING_DEPENDENCY: "等待依赖",
    INCOMPATIBLE: "不兼容",
    FAILED: "启动失败",
    STOPPING: "正在停止",
    STOPPED: "已停止",
  },
  page: {
    ready: "扩展页面已加载，模板配置与导出功能将在后续版本提供。",
    disable: "停用扩展",
  },
};
