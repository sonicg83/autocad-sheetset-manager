// 设置中心与关于接口客户端（PLAN-DM-019 任务 9）。
// 后端契约见 src/dst_manager/interfaces/settings_contracts.py（snake_case）；
// 本层负责 snake_case→camelCase 映射，composable 与组件只见 camelCase。
import {request} from "./client";

export type SettingsControl = "path" | "bool" | "int" | "enum";
export type SettingsValue = string | number | boolean | null;
export type SettingsSource = "default" | "env" | "file";
// 仅 path 控件返回：ShellBridge 固定扩展名种类（PLAN-DM-021 Task 1）
export type SettingsFileKind = "exe" | "dll";

export interface SettingsEnumOption {
  // ui_locale 为字符串枚举（system/zh-CN/en-US），其余枚举为 int
  value: number | string;
  textKey?: string; // 稳定选项文本键（PLAN-DM-021 Task 1）
  text?: string; // 迁移期兼容中文文本（阶段三随 label/category 一并删除）
}

// PLAN-DM-021 Task 3 起组件只消费稳定显示键（labelKey/categoryKey/textKey/
// fileFilterKey）做 i18n 渲染；label/category/text/fileFilter 为迁移期兼容
// 中文文本（I18N-17），仅在前端语言资源缺键时作回退，阶段三验收后删除。
export interface SettingsItem {
  key: string;
  labelKey?: string; // 前端文案键，如 settings.items.uiLocale
  categoryKey?: string; // 前端文案键，如 settings.categories.interface
  label?: string; // 迁移期兼容：中文显示名
  category?: string; // 迁移期兼容：中文分类
  control: SettingsControl;
  value: SettingsValue;
  // Schema 字段默认值（非当前值，fba1624 起返回）
  default: SettingsValue;
  source: SettingsSource;
  hasFileOverride: boolean;
  // 以下仅特定控件返回（path → nullable/fileFilterKey/fileKind；enum → options；int → min/max）
  nullable?: boolean;
  fileFilterKey?: string; // 过滤器显示名文案键，如 settings.fileFilters.executable
  fileKind?: SettingsFileKind; // ShellBridge 固定扩展名种类
  fileFilter?: string; // 迁移期兼容：中文过滤器文本
  options?: SettingsEnumOption[];
  min?: number;
  max?: number;
}

export interface SettingsSnapshot {
  schemaVersion: number;
  configRevision: number;
  items: SettingsItem[];
  // 后端 diagnostics 为字符串数组（首元素为机器码，其余为人类可读说明）
  diagnostics: string[];
  schemaBlocked: boolean;
}

export interface AboutInfo {
  appName: string;
  version: string;
  license: {spdx: string; text: string};
  homepage: string;
  feedbackUrl: string;
}

// ---- 后端原始响应（snake_case），仅在本文件内出现 ----

interface RawSettingsItem {
  key: string;
  label_key?: string | null;
  category_key?: string | null;
  label?: string | null;
  category?: string | null;
  control: string;
  value: SettingsValue;
  default: SettingsValue;
  source: string;
  has_file_override: boolean;
  nullable?: boolean | null;
  file_filter_key?: string | null;
  file_kind?: string | null;
  file_filter?: string | null;
  options?: {value: number | string; text_key?: string | null; text?: string | null}[] | null;
  min?: number | null;
  max?: number | null;
}

interface RawSettingsResponse {
  schema_version: number;
  config_revision: number;
  items: RawSettingsItem[];
  diagnostics: string[];
  schema_blocked: boolean;
}

interface RawAboutResponse {
  app_name: string;
  version: string;
  license: {spdx: string; text: string};
  homepage: string;
  feedback_url: string;
}

function mapItem(raw: RawSettingsItem): SettingsItem {
  return {
    key: raw.key,
    labelKey: raw.label_key ?? undefined,
    categoryKey: raw.category_key ?? undefined,
    label: raw.label ?? undefined,
    category: raw.category ?? undefined,
    control: raw.control as SettingsControl,
    value: raw.value,
    default: raw.default,
    source: raw.source as SettingsSource,
    hasFileOverride: raw.has_file_override,
    nullable: raw.nullable ?? undefined,
    fileFilterKey: raw.file_filter_key ?? undefined,
    fileKind: (raw.file_kind ?? undefined) as SettingsFileKind | undefined,
    fileFilter: raw.file_filter ?? undefined,
    options: raw.options?.map(option => ({
      value: option.value,
      textKey: option.text_key ?? undefined,
      text: option.text ?? undefined,
    })),
    min: raw.min ?? undefined,
    max: raw.max ?? undefined,
  };
}

function mapSnapshot(raw: RawSettingsResponse): SettingsSnapshot {
  return {
    schemaVersion: raw.schema_version,
    configRevision: raw.config_revision,
    items: raw.items.map(mapItem),
    diagnostics: raw.diagnostics,
    schemaBlocked: raw.schema_blocked,
  };
}

function mapAbout(raw: RawAboutResponse): AboutInfo {
  return {
    appName: raw.app_name,
    version: raw.version,
    license: raw.license,
    homepage: raw.homepage,
    feedbackUrl: raw.feedback_url,
  };
}

export async function fetchSettings(): Promise<SettingsSnapshot> {
  return mapSnapshot(await request<RawSettingsResponse>("/api/settings"));
}

// 保存设置：expectedRevision 由调用方取当前快照的 configRevision 传入。
// 409（修订冲突/schema 阻断）与 422（字段级结构化错误，ApiError.fieldErrors 为
// {key: {code, messageKey, params, message}}，ARCH-DM-005 §6.2）的 ApiError
// 原样上抛，由对话框层处理行内错误、错误摘要与冲突提示。
export async function putSettings(
  expectedRevision: number,
  set: Record<string, unknown>,
  unset: string[],
): Promise<SettingsSnapshot> {
  const raw = await request<RawSettingsResponse>("/api/settings", {
    method: "PUT",
    body: JSON.stringify({expected_revision: expectedRevision, set, unset}),
  });
  return mapSnapshot(raw);
}

export async function fetchAbout(): Promise<AboutInfo> {
  return mapAbout(await request<RawAboutResponse>("/api/about"));
}
