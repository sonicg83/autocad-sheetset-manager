// 单个扩展设置的唯一状态所有者（PLAN-DM-025 Task 7 / SPEC-DM-011 SC-17、ARCH-DM-006 §8.1/§8.2）。
// 一个扩展一份快照：服务端快照、编辑缓冲、脏标记、逐字段错误、修订冲突与只读保护都在这里收敛，
// 与核心设置（useSettings）互不相干——不共享一次提交、不共享修订号，核心配置的未保存缓冲
// 也不因保存扩展设置而变化。
//
// 它刻意不做的事：
// - 不重排字段、不重新解释控件词表（items 已由后端合并排序，词表映射在呈现层唯一确定）；
// - 不做本地校验或截断（Provider 是唯一权威，越界值原样上送，由 422 的 params.field 行内定位）；
// - 不决定呈现与焦点（generated/custom 分派与进入焦点归 ExtensionSettingsHost）。
import {computed, ref} from "vue";
import type {ComputedRef, Ref} from "vue";
import {ApiError} from "../api/client";
import {fetchExtensionSettings, putExtensionSettings} from "../api/extensions";
import type {ExtensionSettingsItem, ExtensionSettingsView} from "../api/contracts";

// 逐字段错误：只带稳定 code 与已本地化文案（文案由 api/client 按 message_key 渲染），
// 呈现层不再接触插值参数
export interface ExtensionFieldError {
  code: string;
  message: string;
}

// 修订冲突：服务端已推进修订，本地编辑保留待用户裁决
export interface ExtensionSettingsConflict {
  expectedRevision: number;
  currentRevision: number;
}

export interface ExtensionSettingsState {
  snapshot: Ref<ExtensionSettingsView | null>;
  items: ComputedRef<ExtensionSettingsItem[]>;
  loading: Ref<boolean>;
  loadFailed: Ref<boolean>;
  saving: Ref<boolean>;
  saved: Ref<boolean>;
  edits: Ref<Record<string, unknown>>;
  fieldErrors: Ref<Record<string, ExtensionFieldError>>;
  conflict: Ref<ExtensionSettingsConflict | null>;
  saveFailed: Ref<string>;
  readOnly: ComputedRef<boolean>;
  dirty: ComputedRef<boolean>;
  load: () => Promise<void>;
  setField: (key: string, value: unknown) => void;
  save: () => Promise<void>;
  discardLocalEdits: () => void;
}

const FALLBACK_INVALID_CODE = "EXTENSION_SETTINGS_INVALID";

// 编辑值与服务端持久值的比较：生成表单只产生 JSON 标量，比较按值不做字符串化
function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

export function useExtensionSettings(extensionId: string): ExtensionSettingsState {
  const snapshot = ref<ExtensionSettingsView | null>(null);
  const loading = ref(false);
  const loadFailed = ref(false);
  const saving = ref(false);
  const saved = ref(false);
  const edits = ref<Record<string, unknown>>({});
  const fieldErrors = ref<Record<string, ExtensionFieldError>>({});
  const conflict = ref<ExtensionSettingsConflict | null>(null);
  const saveFailed = ref("");
  let savedTimer: ReturnType<typeof setTimeout> | null = null;

  const items = computed<ExtensionSettingsItem[]>(() => snapshot.value?.items ?? []);
  const readOnly = computed(() => snapshot.value?.read_only === true);
  // 脏 = 至少一个字段的编辑值不同于服务端持久值（输回原值即回到干净）
  const dirty = computed(() => Object.keys(edits.value).some(key => !sameValue(edits.value[key], snapshot.value?.value?.[key])));

  function showSaved(): void {
    saved.value = true;
    if (savedTimer !== null) clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { saved.value = false; }, 2500);
  }

  // 读取快照：不触碰编辑缓冲（409 冲突后的刷新必须保留本地输入）；
  // 只清理冲突与失败提示以外的数据由调用方决定
  async function load(): Promise<void> {
    loading.value = true;
    loadFailed.value = false;
    try {
      snapshot.value = await fetchExtensionSettings(extensionId);
      saveFailed.value = "";
    } catch {
      loadFailed.value = true; // 快照保持上一次成功结果（有值时降级为就地错误提示）
    } finally {
      loading.value = false;
    }
  }

  function setField(key: string, value: unknown): void {
    edits.value = {...edits.value, [key]: value};
    if (fieldErrors.value[key] !== undefined) {
      const next = {...fieldErrors.value};
      delete next[key];
      fieldErrors.value = next;
    }
    saveFailed.value = "";
  }

  function discardLocalEdits(): void {
    edits.value = {};
    fieldErrors.value = {};
    conflict.value = null;
    saveFailed.value = "";
  }

  // 422：Provider 拒绝的值定位到 params.field（字段行内错误），没有字段定位时走横幅
  function applyFieldError(error: ApiError): void {
    const field = typeof error.params?.field === "string" ? error.params.field : undefined;
    if (field === undefined) {
      saveFailed.value = error.message;
      return;
    }
    fieldErrors.value = {...fieldErrors.value, [field]: {code: error.code ?? FALLBACK_INVALID_CODE, message: error.message}};
  }

  // 未知更高 Schema：服务端已存更高版本，无法覆盖保存；本地编辑不能落盘，只读态必须不脏
  async function applyReadOnly(): Promise<void> {
    discardLocalEdits();
    await load();
  }

  async function save(): Promise<void> {
    const current = snapshot.value;
    if (current === null || saving.value || readOnly.value || !dirty.value) return;
    saving.value = true;
    saveFailed.value = "";
    saved.value = false;
    try {
      const next = await putExtensionSettings(extensionId, {
        schema_version: current.schema_version,
        expected_revision: current.revision,
        // 完整规范值：持久值叠加本地编辑，字段之外的 Provider 数据不被丢弃
        value: {...current.value, ...edits.value},
      });
      snapshot.value = next; // 服务端规范化后的值回读（如关键词去重/裁剪空白）
      edits.value = {};
      fieldErrors.value = {};
      conflict.value = null;
      showSaved();
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        applyFieldError(error);
      } else if (error instanceof ApiError && error.status === 409) {
        if (error.code === "EXTENSION_SETTINGS_SCHEMA_NEWER") {
          await applyReadOnly();
        } else {
          // 修订冲突（服务端以 409 表达 expected_revision 漂移）：保留本地输入、刷新快照
          conflict.value = {
            expectedRevision: typeof error.params?.expected_revision === "number" ? error.params.expected_revision : current.revision,
            currentRevision: typeof error.params?.current_revision === "number" ? error.params.current_revision : current.revision,
          };
          await load();
        }
      } else {
        saveFailed.value = errorText(error);
      }
    } finally {
      saving.value = false;
    }
  }

  return {
    snapshot, items, loading, loadFailed, saving, saved, edits, fieldErrors, conflict, saveFailed,
    readOnly, dirty, load, setField, save, discardLocalEdits,
  };
}
