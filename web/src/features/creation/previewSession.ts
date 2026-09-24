// 创建权威预览与执行的会话状态迁移（PLAN-DM-036 Task 9）。
//
// 职责单一：把「按需保存草稿 → 请求权威预览 → 写入摘要与可执行标志 → 按摘要执行创建」
// 的状态迁移集中在一处，并保证任何输入/标准身份/编号设置变化都使旧摘要立即失效。按组
// 投影与单元格摘要在 `previewModel.ts`，界面在 `components/creation/`。
//
// 三条不可让步的语义：
// - 执行只发送 `preview_digest`：目标路径、组表、编号与 DWG 命名结果一律由服务端在入队前
//   重新加载并重算，前端不夹带任何派生输出；
// - 摘要与可执行标志只来自后端响应，前端不自行判定「能不能创建」；
// - 失效即清空（摘要、响应与可执行标志一起清），避免「旧摘要 + 新输入」被误执行。
import type {Job} from "../../api/contracts";
import type {
  CreationApi,
  CreationPreview,
  CreationPreviewSessionState,
} from "./types";

export interface CreationPreviewSession {
  /** 保存草稿（按需）后请求权威预览；成功时写入摘要与可执行标志。 */
  preview(): Promise<boolean>;
  /** 按当前有效摘要执行创建；无有效预览时不发请求并返回 null。 */
  execute(): Promise<Job | null>;
  /** 输入或标准身份变化：旧预览、摘要与可执行标志一并失效。 */
  invalidate(): void;
  /** 编号设置来自设置中心（本向导之外）：同样使旧摘要失效，命名区分调用点。 */
  invalidateForSettingsChange(): void;
}

export interface CreationPreviewSessionOptions {
  api: CreationApi;
  /** 与 store 共享的 reactive 状态片段（唯一读写点）。 */
  state: CreationPreviewSessionState;
  draftId: () => string;
  /** 预览前按需保存：`goToStep` 等路径的保存会递增草稿修订并使旧摘要失效。 */
  save: () => Promise<boolean>;
  /** 失败消息写回 store 的稳定错误通道（本模块不持有用户可见文本）。 */
  onError: (message: string) => void;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

export function createCreationPreviewSession(
  options: CreationPreviewSessionOptions,
): CreationPreviewSession {
  const {api, state} = options;

  function invalidate(): void {
    state.previewState = null;
    state.previewDigest = null;
    state.canExecute = false;
  }

  async function preview(): Promise<boolean> {
    const draftId = options.draftId();
    if (draftId === "") return false;
    // 先落盘：预览绑定草稿修订，未保存的输入不得进入摘要
    if (!(await options.save())) return false;
    state.previewPending = true;
    try {
      const result: CreationPreview = await api.previewDraft(draftId);
      // 草稿身份在请求期间变化（切换标准/重新开始）时丢弃迟到响应
      if (options.draftId() !== draftId) return false;
      state.previewState = result;
      state.previewDigest = result.preview_digest;
      state.canExecute = result.executable;
      return true;
    } catch (error) {
      options.onError(errorMessage(error));
      invalidate();
      return false;
    } finally {
      state.previewPending = false;
    }
  }

  async function execute(): Promise<Job | null> {
    const draftId = options.draftId();
    const digest = state.previewDigest;
    // 在途执行不得重复入队：同一目标目录不能同时跑两个创建任务
    if (draftId === "" || digest === null || !state.canExecute || state.executePending) return null;
    state.executePending = true;
    try {
      return await api.executeDraft(draftId, digest);
    } catch (error) {
      options.onError(errorMessage(error));
      // 入队失败（摘要漂移/计划不可执行等）同样作废旧预览：必须重新检查后再试
      invalidate();
      return null;
    } finally {
      state.executePending = false;
    }
  }

  return {preview, execute, invalidate, invalidateForSettingsChange: invalidate};
}
