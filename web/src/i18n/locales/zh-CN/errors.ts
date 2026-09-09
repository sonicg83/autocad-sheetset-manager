// zh-CN 错误域语言资源（PLAN-DM-021 Task 9；ARCH-DM-005 §6.2 / I18N-11）。
// 键集合必须与 en-US 完全一致（check:i18n 门禁），且与后端
// src/dst_manager/interfaces/message_catalog.py 的 message_key/参数 schema
// 严格对称（tests/unit/test_message_catalog.py 交叉守护）。
// 参数只承载稳定值（路径/标识/名称/编号等用户数据，原样保留，不做区域化转换）；
// 未知错误显示 ui.unknownSummary 摘要，原始文本仅进可展开诊断详情。
export default {
  workspace: {
    notFound: "工作区不存在，请重新打开图纸集",
    writeBusy: "工作区正被其他操作占用，请稍后重试",
    dstNotFound: "DST 文件不存在：{dst_path}",
  },
  revision: {
    conflict: "基准修订已变化，请重新预览",
    notFound: "修订不存在",
    manifestMissing: "修订清单缺失",
    restoreConflict: "恢复基准已变化，请重新预览恢复",
    restoreSourceChanged: "恢复源文件已偏离预览",
  },
  draft: {
    conflict: "草稿版本冲突，请刷新后重试",
  },
  job: {
    notFound: "任务不存在",
    notRetryable: "当前任务状态不允许重试",
  },
  plan: {
    invalid: "执行计划包含阻断问题，无法继续",
    repreviewRequired: "预览已变化或尚未确认，请重新预览",
  },
  repair: {
    blocked: "存在阻断问题，禁止写入",
    notRequired: "当前 DST 无待确认修复",
    confirmationRequired: "检测到可修复的 DST 元数据缺失，必须先确认并发布修复修订",
    unrecoverable: "DST 存在不可恢复问题，禁止写入",
  },
  export: {
    baselineRequired: "非主 DST 导出必须先预览目标基准",
    outsideWorkspace: "导出位置必须在工作区内",
  },
  cad: {
    versionInvalid: "不支持的 AutoCAD 版本：{cad_version}",
    capabilityUnavailable: "AutoCAD 未配置 Core Console 或 Worker 插件，请运行 dst-manager doctor 检查",
  },
  layout: {
    readFailed: "读取布局失败，DWG 可能正被占用或 CAD 环境不可用",
    sourceNotFound: "来源文件不存在",
    sourceTypeInvalid: "来源文件必须是 .dwg 或 .dwt",
  },
  command: {
    unsupported: "不支持的命令：{command}",
    requiresCad: "该命令需要 CAD 执行：{command}",
  },
  settings: {
    conflict: "设置已被其他进程修改，请刷新后重试",
    schemaBlocked: "设置文件 schema 版本与当前程序不兼容，已进入只读模式",
    schemaOlder: "设置文件 schema 版本低于当前程序，已进入只读模式",
    validationFailed: "设置校验失败，请修正标红的字段",
  },
  sheet: {
    notFound: "图纸不存在：{object_id}",
    nodeNotFound: "图纸节点不存在：{object_id}",
    nodeDuplicated: "图纸节点重复：{object_id}",
    titleEmpty: "图纸标题不能为空",
    layoutCount: "图纸引用的布局数量无效：{object_id}",
    positionInvalid: "插入位置无效：{position}",
    insertCountInvalid: "插入数量必须为正整数：{value}",
  },
  subset: {
    notFound: "子集不存在：{subset_id}",
    nodeNotFound: "子集节点不存在：{object_id}",
    nodeDuplicated: "子集节点重复：{object_id}",
    positionInvalid: "插入位置无效：{position}",
    empty: "子集不能为空",
  },
  sheetSet: {
    invalid: "图纸集节点无效",
    missing: "缺少 AcSmSheetSet 节点",
  },
  property: {
    notFound: "自定义属性不存在：{name}",
    duplicated: "自定义属性重复：{name}",
    valueDuplicated: "自定义属性存在多个 Value：{name}",
    bagDuplicated: "属性包重复：{owner_id}",
    flagsMissing: "自定义属性缺少 Flags 标记：{name}",
    flagsInvalid: "自定义属性 Flags 标记无效：{name}",
    typeInvalid: "自定义属性类型无效：{type}",
    typeConflict: "自定义属性类型冲突：{name}",
    nameDuplicate: "自定义属性名称重复：{name}",
    nameEmpty: "自定义属性名称不能为空",
    nameInvalid: "自定义属性名称包含无效字符",
    valueInvalid: "自定义属性值包含 XML 1.0 禁止字符",
    scopeMismatch: "自定义属性作用域与编辑对象不匹配：{name}",
  },
  dwg: {
    duplicateAcsmId: "AcSm ID 重复：{acsm_id}",
    outsideWorkspace: "DWG 路径超出工作区范围：{path}",
    unknownReferenceBlocked: "存在未登记的引用节点，禁止继续：{object_id}",
    layoutSourceInvalid: "布局来源无效",
  },
  xml: {
    validationFailed: "DST XML 校验失败",
    invalid: "XML 内容无效",
    rootInvalid: "XML 根节点必须为 AcSmDatabase",
    textInvalid: "文本包含 XML 1.0 禁止字符",
    controlledPropertyInvalid: "受控属性写入无效：{name}",
    childReconciliationFailed: "受控子节点协调失败",
  },
  shell: {
    workspaceUnavailable: "当前没有匹配的已打开工作区",
    openFailed: "在资源管理器中打开失败",
    directoryNotFound: "图纸集目录不存在，可能已被移动或删除",
    externalUrlRejected: "仅允许打开登记的 https 链接",
    preferencesIo: "图纸列偏好读写失败",
    preferencesInvalid: "图纸列偏好数据无效",
  },
  ui: {
    unknownSummary: "操作失败，发生未知错误",
    diagnosticsDetails: "原始错误详情",
  },
};
