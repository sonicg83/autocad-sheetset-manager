// zh-CN 通用域语言资源（按功能域拆分，ARCH-DM-005 §5.1）。
// 最小骨架：Task 3 起随各功能域迁移扩展；键集合必须与 en-US 完全一致（check:i18n 门禁）。
export default {
  app: {
    title: "DST 图纸集管理器",
  },
  errors: {
    settingsLoadFailed: "设置加载失败，界面语言按系统设置解析",
  },
  // 原生文件对话框的本地化描述（PLAN-DM-021 Task 4）：只作对话框显示，
  // 扩展名白名单由壳侧按 file_kind 固定拼接；描述经壳侧净化，不得携带模式字符
  shell: {
    fileKinds: {
      dst: "DST 文件",
      template: "DWG DWT 文件",
      exe: "可执行程序",
      dll: "NET 程序集",
    },
  },
} as const;
