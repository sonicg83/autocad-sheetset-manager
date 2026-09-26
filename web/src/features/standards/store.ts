// 标准状态控制器（PLAN-DM-035 Task 7）。
// 代次保护：每次 open/refresh 递增代次，乱序响应按代次丢弃——旧详情不得覆盖当前标准。
// pending/error 状态显式分离：listPending/detailPending 呈现加载，listError/detailError
// 保留稳定错误码消息；actionPending 覆盖发布/导入等事务动作。
import {ref, type Ref} from "vue";
import type {
  AssetInspection,
  CopiedAssetFile,
  CopyAssetFileInput,
  CreateDraftFromDstInput,
  CreateDraftInput,
  ConfirmImportInput,
  ImportedStandardDraft,
  ImportPreviewInput,
  ImportPreviewResult,
  InspectAssetInput,
  PublishInput,
  PublishedStandard,
  SaveDraftInput,
  StandardDetail,
  StandardDraft,
  StandardIdentity,
  StandardSummary,
} from "./types";

export interface StandardApi {
  list(): Promise<StandardSummary[]>;
  fetchDetail(identity: StandardIdentity): Promise<StandardDetail>;
  fetchDraft(draftId: string): Promise<StandardDraft>;
  createDraft(input: CreateDraftInput): Promise<StandardDraft>;
  saveDraft(input: SaveDraftInput): Promise<StandardDraft>;
  createDraftFromDst(input: CreateDraftFromDstInput): Promise<ImportedStandardDraft>;
  publish(input: PublishInput): Promise<PublishedStandard>;
  previewImport(input: ImportPreviewInput): Promise<ImportPreviewResult>;
  confirmImport(input: ConfirmImportInput): Promise<PublishedStandard>;
  cancelImport(previewId: string): Promise<void>;
  deleteDraft(draftId: string): Promise<void>;
  inspectAsset(input: InspectAssetInput): Promise<AssetInspection>;
  copyAssetFile(input: CopyAssetFileInput): Promise<CopiedAssetFile>;
}

export interface StandardStore {
  summaries: Ref<StandardSummary[]>;
  listPending: Ref<boolean>;
  listError: Ref<string>;
  detail: Ref<StandardDetail | null>;
  detailPending: Ref<boolean>;
  detailError: Ref<string>;
  /** 编辑器加载的草稿（含原始文档）；未进入编辑器时为 null。 */
  draft: Ref<StandardDraft | null>;
  draftPending: Ref<boolean>;
  draftError: Ref<string>;
  actionPending: Ref<boolean>;
  actionError: Ref<string>;
  refresh(): Promise<void>;
  open(identity: StandardIdentity): Promise<void>;
  /** 详情是否与给定身份一致（身份不匹配或在途/失败时一律为 false）。 */
  detailMatches(identity: StandardIdentity): boolean;
  /** 清空详情并使在途详情响应失效（切到草稿等无发布详情的选中项）。 */
  clearDetail(): void;
  /** 加载草稿原始文档；代次保护同 open（乱序响应不覆盖当前草稿）。 */
  loadDraft(draftId: string): Promise<StandardDraft | null>;
  /** 直接采用刚创建的草稿（省去一次冗余 GET）。 */
  adoptDraft(draft: StandardDraft): void;
  /** 卸载当前草稿并使在途加载失效。 */
  closeDraft(): void;
  createDraft(input: CreateDraftInput): Promise<StandardDraft>;
  saveDraft(input: SaveDraftInput): Promise<StandardDraft>;
  createDraftFromDst(input: CreateDraftFromDstInput): Promise<ImportedStandardDraft>;
  publish(input: PublishInput): Promise<PublishedStandard>;
  previewImport(input: ImportPreviewInput): Promise<ImportPreviewResult>;
  confirmImport(input: ConfirmImportInput): Promise<PublishedStandard>;
  cancelImport(previewId: string): Promise<void>;
  deleteDraft(draftId: string): Promise<void>;
  inspectAsset(input: InspectAssetInput): Promise<AssetInspection>;
  /** 本机模板受控复制：成功时返回包内相对路径与按需读取的非 Model 布局。 */
  copyAssetFile(input: CopyAssetFileInput): Promise<CopiedAssetFile>;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

export function createStandardStore(api: StandardApi): StandardStore {
  const summaries: Ref<StandardSummary[]> = ref([]);
  const listPending = ref(false);
  const listError = ref("");
  const detail: Ref<StandardDetail | null> = ref(null);
  const detailPending = ref(false);
  const detailError = ref("");
  const draft: Ref<StandardDraft | null> = ref(null);
  const draftPending = ref(false);
  const draftError = ref("");
  const actionPending = ref(false);
  const actionError = ref("");
  // 代次：open 与 refresh 各自独立编号，只有最新一代允许提交状态
  let listGeneration = 0;
  let detailGeneration = 0;
  let draftGeneration = 0;

  async function refresh(): Promise<void> {
    const generation = ++listGeneration;
    listPending.value = true;
    listError.value = "";
    try {
      const items = await api.list();
      if (generation !== listGeneration) return;
      summaries.value = items;
    } catch (error) {
      if (generation !== listGeneration) return;
      listError.value = errorMessage(error);
    } finally {
      if (generation === listGeneration) listPending.value = false;
    }
  }

  async function open(identity: StandardIdentity): Promise<void> {
    const generation = ++detailGeneration;
    // 切换选择即清除旧详情：在途响应由代次丢弃，派生等动作不得消费上一个标准的详情
    detail.value = null;
    detailPending.value = true;
    detailError.value = "";
    try {
      const loaded = await api.fetchDetail(identity);
      if (generation !== detailGeneration) return;
      detail.value = loaded;
    } catch (error) {
      if (generation !== detailGeneration) return;
      detailError.value = errorMessage(error);
    } finally {
      if (generation === detailGeneration) detailPending.value = false;
    }
  }

  /** 详情是否与给定身份一致（已加载且身份匹配才允许被派生等动作消费）。 */
  function detailMatches(identity: StandardIdentity): boolean {
    const loaded = detail.value;
    return loaded !== null
      && loaded.standard_id === identity.standardId
      && loaded.version === identity.version;
  }

  function clearDetail(): void {
    detailGeneration += 1;
    detail.value = null;
    detailPending.value = false;
    detailError.value = "";
  }

  async function loadDraft(draftId: string): Promise<StandardDraft | null> {
    const generation = ++draftGeneration;
    draftPending.value = true;
    draftError.value = "";
    try {
      const loaded = await api.fetchDraft(draftId);
      if (generation !== draftGeneration) return null;
      draft.value = loaded;
      return loaded;
    } catch (error) {
      if (generation !== draftGeneration) return null;
      draftError.value = errorMessage(error);
      return null;
    } finally {
      if (generation === draftGeneration) draftPending.value = false;
    }
  }

  function adoptDraft(created: StandardDraft): void {
    draftGeneration += 1;
    draft.value = created;
    draftPending.value = false;
    draftError.value = "";
  }

  function closeDraft(): void {
    draftGeneration += 1;
    draft.value = null;
    draftPending.value = false;
    draftError.value = "";
  }

  async function runAction<T>(action: () => Promise<T>): Promise<T> {
    actionPending.value = true;
    actionError.value = "";
    try {
      return await action();
    } catch (error) {
      actionError.value = errorMessage(error);
      throw error;
    } finally {
      actionPending.value = false;
    }
  }

  return {
    summaries,
    listPending,
    listError,
    detail,
    detailPending,
    detailError,
    draft,
    draftPending,
    draftError,
    actionPending,
    actionError,
    refresh,
    open,
    detailMatches,
    clearDetail,
    loadDraft,
    adoptDraft,
    closeDraft,
    createDraft: (input) => runAction(() => api.createDraft(input)),
    saveDraft: (input) => runAction(() => api.saveDraft(input)),
    createDraftFromDst: (input) => runAction(() => api.createDraftFromDst(input)),
    publish: (input) => runAction(() => api.publish(input)),
    previewImport: (input) => runAction(() => api.previewImport(input)),
    confirmImport: (input) => runAction(() => api.confirmImport(input)),
    cancelImport: (previewId) => runAction(() => api.cancelImport(previewId)),
    deleteDraft: (draftId) => runAction(() => api.deleteDraft(draftId)),
    inspectAsset: (input) => runAction(() => api.inspectAsset(input)),
    copyAssetFile: (input) => runAction(() => api.copyAssetFile(input)),
  };
}
