// 属性页（PLAN-DM-016 / SPEC-DM-010）纯类型定义。
// 字段身份始终是 `type + name`，不能只用名称；图纸集名称使用独立身份 `@name`，
// 与自定义属性「工程名称」互不等同。属性值只使用字符串。
export type PropertyKey = `${"sheetset" | "sheet"}:${string}`;
export type ValueKey = "@name" | `sheetset:${string}`;
export type PropertySearchMode = "all" | "name" | "value";
export type ValueStatus = {dirty: boolean; pending: boolean; invalid: boolean};
export type PropertyBuffer = {name: string; values: Record<string, string>};
export type PropertySubmitResult = {ok: boolean; message?: string; fields?: Record<string, string>};
