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

// 409 的服务端原样回显：可能是修订冲突，也可能是同一端点上的 Provider 级冲突。
// code 是服务端响应里的稳定码原样透传：呈现层用 isRevisionConflict() 判别，
// 判别之外一律按普通保存失败呈现（横幅文案取 message，即服务端自己的正文）。
export interface ExtensionSettingsConflict {
  code: string;
  expectedRevision: number;
  currentRevision: number;
  // 服务端是否在 params 里同时给出了期望与当前修订：修订漂移的判别依据之一
  //（另一依据是码属 REVISION_CONFLICT_CODES），见 isRevisionConflict
  revisionParamsPresent: boolean;
  // 服务端响应里的正文（PLAN-DM-025 Task 8）：同一 PUT 端点上的 409 不止修订冲突
  //（Provider 级 409 如 SHEET_CATALOG_COLUMN_DUPLICATE 名称重复共用该状态码）。
  // 消费方按 isRevisionConflict 判定后需要原文才能给出可见诊断，故一并透传。
  message: string;
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
  readOnlyCode: ComputedRef<string>;
  dirty: ComputedRef<boolean>;
  load: () => Promise<void>;
  setField: (key: string, value: unknown) => void;
  save: () => Promise<void>;
  discardLocalEdits: () => void;
}

const FALLBACK_INVALID_CODE = "EXTENSION_SETTINGS_INVALID";

// 修订冲突（expected_revision 漂移）的稳定码：服务端在 SettingsRevisionConflictError 映射里
// 发这个码 + params.expected_revision/current_revision（application/extensions/settings.py）。
// 同一 PUT 端点上还有 Provider 级 409（图纸目录的 SHEET_CATALOG_COLUMN_DUPLICATE 名称重复等），
// 它们不是修订问题：把这类 409 当作修订冲突会让用户看到「按新修订重试」却反复重发同一个
// 已是最新的 expected_revision（确定性死循环）。
export const REVISION_CONFLICT_CODES: readonly string[] = ["EXTENSION_SETTINGS_INVALID"];

// 判别口径 = 码在集合内，或服务端在 params 里同时给出期望与当前修订。后者是判据的拓展：
// 修订漂移的语义就是这对参数，服务端换码时它仍成立。**不靠 Provider 错误参数白名单立论**：
// SHEET_CATALOG_TEMPLATE_CONFLICT 的声明里也允许这两个参数（extensions/builtin/
// sheet_catalog/errors.py），它今天不构成误判只因设置 PUT 路径上的 save_templates 不传
// expected_revision（application/extensions/settings.py），两条抛出点因而都不带参数。
// 该可达性前提由任务 9 的后端回归钉住：设置 PUT 路径不得传 expected_revision。
export function isRevisionConflict(value: ExtensionSettingsConflict | null): boolean {
  if (value === null) return false;
  if (REVISION_CONFLICT_CODES.includes(value.code)) return true;
  return value.revisionParamsPresent;
}

// 编辑值与服务端持久值的比较：生成表单只产生 JSON 标量，比较按值不做字符串化。
// 导出供呈现层（GeneratedExtensionSettingsForm 的行级 dirty 判定）复用同一口径：
// 行级状态不得在这里之外重新发明第二套比较（SPEC-DM-015 §2.2，PLAN-DM-034 fix 1）。
export function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
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
  // 高版本只读的粘性判定：服务端一旦以 EXTENSION_SETTINGS_SCHEMA_NEWER 拒绝保存，
  // 本次子视图不再回到可写。只读若只从刷新后的快照推导，刷新失败就会退回陈旧的可写快照
  // （横幅不出现、保存按钮可用、每次保存重复 409）——这是确定的死循环，必须与刷新解耦。
  // 存字符串而非布尔：拒绝保存时返回的稳定码与只读判定同源，供诊断条原样回显。
  const schemaNewerCode = ref("");
  let savedTimer: ReturnType<typeof setTimeout> | null = null;

  const items = computed<ExtensionSettingsItem[]>(() => snapshot.value?.items ?? []);
  // 只读来源二选一：本次会话被服务端以 409 拒绝覆盖（粘性），或当前快照自报只读（首次读取即高版本）
  const readOnly = computed(() => schemaNewerCode.value !== "" || snapshot.value?.read_only === true);
  // 诊断条回显的码优先取粘性码：否则刷新失败时只读横幅会显示空码（快照是陈旧的）
  const readOnlyCode = computed(() => schemaNewerCode.value || snapshot.value?.diagnostic_code || "");
  // 脏 = 至少一个字段的编辑值不同于服务端有效值（含 Provider 默认值）。界面展示与
  // 比较必须共用这一可信基准；保存仍在持久 value 上叠加 edits，避免把未编辑默认值写实。
  const dirty = computed(() => Object.keys(edits.value).some(key => !sameValue(edits.value[key], snapshot.value?.effective_value?.[key])));

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

  // 未知更高 Schema：服务端已存更高版本，无法覆盖保存；本地编辑不能落盘，只读态必须不脏。
  // 先立只读判定再刷新：刷新失败也不撤销只读（刷新只用来把修订与 Schema 徽标对齐服务端）
  async function applyReadOnly(code: string): Promise<void> {
    discardLocalEdits();
    schemaNewerCode.value = code;
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
          await applyReadOnly(error.code);
        } else {
          // 修订冲突（服务端以 409 表达 expected_revision 漂移）：保留本地输入、刷新快照。
          // 码原样取服务端响应，不在前端写死（线上当前为 EXTENSION_SETTINGS_INVALID）；
          // 是否向用户提供「按新修订重试」的出路由 isRevisionConflict 判别，不在此处分岔
          const expectedRevision = typeof error.params?.expected_revision === "number" ? error.params.expected_revision : null;
          const currentRevision = typeof error.params?.current_revision === "number" ? error.params.current_revision : null;
          conflict.value = {
            code: error.code ?? FALLBACK_INVALID_CODE,
            expectedRevision: expectedRevision ?? current.revision,
            currentRevision: currentRevision ?? current.revision,
            revisionParamsPresent: expectedRevision !== null && currentRevision !== null,
            message: error.message,
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
    readOnly, readOnlyCode, dirty, load, setField, save, discardLocalEdits,
  };
}
