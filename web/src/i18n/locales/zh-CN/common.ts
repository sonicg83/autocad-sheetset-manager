// zh-CN 通用域语言资源（按功能域拆分，ARCH-DM-005 §5.1）。
// 最小骨架：Task 3 起随各功能域迁移扩展；键集合必须与 en-US 完全一致（check:i18n 门禁）。
export default {
  app: {
    title: "DST 图纸集管理器",
  },
  errors: {
    settingsLoadFailed: "设置加载失败，界面语言按系统设置解析",
  },
} as const;
