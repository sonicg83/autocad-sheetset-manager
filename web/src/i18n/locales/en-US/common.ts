// en-US 通用域语言资源（按功能域拆分，ARCH-DM-005 §5.1）。
// 最小骨架：Task 3 起随各功能域迁移扩展；键集合必须与 zh-CN 完全一致（check:i18n 门禁）。
export default {
  app: {
    title: "DST Sheet Set Manager",
  },
  errors: {
    settingsLoadFailed: "Failed to load settings; UI language resolved from system settings",
  },
} as const;
