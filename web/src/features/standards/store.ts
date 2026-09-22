// 标准状态控制器（PLAN-DM-035 Task 7）。
// 代次保护：每次 open/refresh 递增代次，乱序响应按代次丢弃——旧详情不得覆盖当前标准。
// pending/error 状态显式分离：listPending/detailPending 呈现加载，listError/detailError
// 保留稳定错误码消息；actionPending 覆盖发布/导入等事务动作。
import {ref, type Ref} from "vue";
import type {
  AssetInspection,
  CreateDraftFromDstInput,
  CreateDraftInput,
  ImportedStandardDraft,
  InspectAssetInput,
  PublishInput,
  PublishedStandard,
  SaveDraftByIdentityInput,
  StandardDetail,
  StandardDraft,
  StandardIdentity,
  StandardSummary,
} from "./types";

export interface StandardApi {
  list(): Promise<StandardSummary[]>;
  fetchDetail(identity: StandardIdentity): Promise<StandardDetail>;
  createDraft(input: CreateDraftInput): Promise<StandardDraft>;
  saveDraftByIdentity(input: SaveDraftByIdentityInput): Promise<StandardDraft>;
  createDraftFromDst(input: CreateDraftFromDstInput): Promise<ImportedStandardDraft>;
  publish(input: PublishInput): Promise<PublishedStandard>;
  importPackage(input: {path: string}): Promise<PublishedStandard>;
  inspectAsset(input: InspectAssetInput): Promise<AssetInspection>;
}

export interface StandardStore {
  summaries: Ref<StandardSummary[]>;
  listPending: Ref<boolean>;
  listError: Ref<string>;
  detail: Ref<StandardDetail | null>;
  detailPending: Ref<boolean>;
  detailError: Ref<string>;
  actionPending: Ref<boolean>;
  actionError: Ref<string>;
  refresh(): Promise<void>;
  open(identity: StandardIdentity): Promise<void>;
  createDraft(input: CreateDraftInput): Promise<StandardDraft>;
  saveDraft(input: SaveDraftByIdentityInput): Promise<StandardDraft>;
  createDraftFromDst(input: CreateDraftFromDstInput): Promise<ImportedStandardDraft>;
  publish(input: PublishInput): Promise<PublishedStandard>;
  importPackage(input: {path: string}): Promise<PublishedStandard>;
  inspectAsset(input: InspectAssetInput): Promise<AssetInspection>;
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
  const actionPending = ref(false);
  const actionError = ref("");
  // 代次：open 与 refresh 各自独立编号，只有最新一代允许提交状态
  let listGeneration = 0;
  let detailGeneration = 0;

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
    actionPending,
    actionError,
    refresh,
    open,
    createDraft: (input) => runAction(() => api.createDraft(input)),
    saveDraft: (input) => runAction(() => api.saveDraftByIdentity(input)),
    createDraftFromDst: (input) => runAction(() => api.createDraftFromDst(input)),
    publish: (input) => runAction(() => api.publish(input)),
    importPackage: (input) => runAction(() => api.importPackage(input)),
    inspectAsset: (input) => runAction(() => api.inspectAsset(input)),
  };
}
