// 设置中心与关于接口客户端（PLAN-DM-019 任务 9）。
// 后端契约见 src/dst_manager/interfaces/settings_contracts.py（snake_case）；
// 本层负责 snake_case→camelCase 映射，composable 与组件只见 camelCase。
import {request} from "./client";

export type SettingsControl = "path" | "bool" | "int" | "enum";
export type SettingsValue = string | number | boolean | null;
export type SettingsSource = "default" | "env" | "file";

export interface SettingsEnumOption {
  value: number;
  text: string;
}

export interface SettingsItem {
  key: string;
  label: string;
  category: string;
  control: SettingsControl;
  value: SettingsValue;
  // Schema 字段默认值（非当前值，fba1624 起返回）
  default: SettingsValue;
  source: SettingsSource;
  hasFileOverride: boolean;
  // 以下仅特定控件返回（path → nullable/fileFilter；enum → options；int → min/max）
  nullable?: boolean;
  fileFilter?: string;
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
  label: string;
  category: string;
  control: string;
  value: SettingsValue;
  default: SettingsValue;
  source: string;
  has_file_override: boolean;
  nullable?: boolean | null;
  file_filter?: string | null;
  options?: SettingsEnumOption[] | null;
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
    label: raw.label,
    category: raw.category,
    control: raw.control as SettingsControl,
    value: raw.value,
    default: raw.default,
    source: raw.source as SettingsSource,
    hasFileOverride: raw.has_file_override,
    nullable: raw.nullable ?? undefined,
    fileFilter: raw.file_filter ?? undefined,
    options: raw.options ?? undefined,
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
// 409（修订冲突/schema 阻断）与 422（字段级校验错误，ApiError.fields 为 {key: message}）
// 的 ApiError 原样上抛，由对话框层处理行内错误与冲突提示。
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
