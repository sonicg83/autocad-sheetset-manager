// zh-CN 扩展域语言资源（PLAN-DM-020 Task 10/11；ARCH-DM-005 §5.1 / ARCH-DM-006 §7）。
// 承载扩展页面贡献的宿主侧文案：内置扩展清单的 name_key/description_key 指向
// 本域（src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml），
// 生命周期状态按后端 ExtensionLifecycleStatus 九值逐一登记；
// Task 11 增补图纸目录页面正文（模板栏/字段浏览器/输出列编辑器/兼容性摘要/
// 预览/导出/三选一守卫）的宿主侧文案；目录错误诊断（errors.sheetCatalog.*）
// 登记在 errors 域，与后端 SHEET_CATALOG_MESSAGE_KEYS 对称。
// 键集合必须与 en-US 完全一致（check:i18n 门禁）。
export default {
  sheetCatalog: {
    name: "图纸目录",
    description: "从当前工作区快照生成可配置的图纸目录表，并导出为 XLSX 文件",
    // 内置默认模板与未命名草稿的显示名（SPEC-DM-012 §3.2/§6.2）
    builtinName: "默认图纸目录（内置）",
    defaultHeaderNumber: "图号",
    defaultHeaderTitle: "图名",
    defaultHeaderFileName: "文件名",
    unnamedDraft: "未命名草稿",
    dirtyBadge: "有未保存修改",
    loading: "正在加载模板与偏好…",
    // 模板栏
    templateBarLabel: "模板栏",
    templateLabel: "选择模板",
    save: "保存修改",
    saving: "保存中…",
    saveAs: "另存为",
    remove: "删除模板",
    saveAsTitle: "另存为模板",
    saveAsNameLabel: "模板名称",
    saveAsConfirm: "保存",
    cancel: "取消",
    saveAsNameRequired: "请输入模板名称",
    removeConfirmTitle: "删除模板",
    removeConfirmMessage: "删除模板“{name}”？删除后回到内置默认模板，历史导出记录保留。",
    removeConfirmConfirm: "删除",
    conflictTitle: "保存冲突",
    conflictMessage: "模板已被其他保存更新，本地编辑已保留。可另存为新模板，或刷新服务端修订后重试。",
    conflictSaveAs: "另存为新模板",
    conflictRetry: "按新修订重试",
    toastSaved: "模板已保存",
    toastDeleted: "模板已删除",
    // 字段浏览器
    fieldBrowserLabel: "字段浏览器",
    fieldGroupBuiltin: "图纸固有字段",
    fieldGroupSheetset: "图纸集自定义属性",
    fieldGroupSheet: "图纸自定义属性",
    fieldGroupEmpty: "当前图纸集没有此作用域的自定义属性",
    fieldHint: "点击插入到当前表达式光标位置",
    // 输出列编辑器
    editorLabel: "输出列编辑器",
    columnHeader: "输出列名 {index}",
    columnExpression: "表达式 {index}",
    addColumn: "添加列",
    removeColumn: "删除列 {index}",
    moveUp: "上移 {index}",
    moveDown: "下移 {index}",
    // 兼容性摘要
    compatibilityLabel: "兼容性摘要",
    blockingTitle: "阻断问题",
    warningTitle: "警告",
    noIssues: "模板与当前图纸集兼容",
    // 预览
    previewLabel: "预览",
    previewTotal: "共 {total} 张图纸",
    previewShown: "显示前 {shown} 行",
    previewEmptySheets: "当前图纸集没有图纸",
    previewPending: "正在更新预览…",
    // 操作区与导出
    actionsLabel: "导出操作",
    refreshPreview: "刷新预览",
    exportButton: "导出 XLSX",
    exporting: "正在导出…",
    noShellNotice: "桌面壳不可用，无法打开原生“另存为”对话框；导出仅在桌面应用中可用。",
    exportStaleHint: "草稿已修改，预览更新后才能导出",
    exportNotExecutableHint: "存在阻断问题，导出不可用",
    exportSuccessTitle: "图纸目录已保存到",
    openFolder: "打开所在文件夹",
    exportRetry: "重试导出",
    exportRepreviewHint: "预览已过期，请先刷新预览再重试导出",
    shellUnsupported: "当前桌面壳不支持打开文件夹",
    // 三选一守卫（SPEC §3.2）
    guardTitle: "未保存的模板修改",
    guardMessage: "{summary} 有未保存的修改。可保存为模板、放弃修改或留在此处。",
    guardStay: "留在此处",
    guardDiscard: "放弃修改",
    guardSave: "保存为模板",
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
    ready: "选择模板并配置输出列后即可导出当前图纸集的图纸目录。",
    disable: "停用扩展",
  },
};
