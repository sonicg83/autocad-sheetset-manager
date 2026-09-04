// 结构投影域组合式函数（PLAN-DM-015 任务 1）：结构动作经内部 /changes/preview 请求
// 以 execution_intent.derived_document 获取权威显示结果，与用户显式发布预览分离——
// 绝不设置 previewContext、不打开发布确认、不启动 CAD，因此不会启用「确认写入」。
// 投影按 workspace/revision/命令快照/请求代次校验；失败保留上一份结果并标为失效。
import {ref} from "vue";
import type {Ref} from "vue";
import {request} from "../api/client";
import type {ChangeCommand, Preview, Workspace} from "../api/contracts";
import {applyDerivedProjection} from "../features/sheets/projection";
import type {ProjectionStamp, SubmitResult} from "../features/sheets/types";

const STRUCTURAL_TYPES = new Set(["update_subset_title", "delete_sheet", "delete_subset", "insert_sheet", "insert_subset"]);

export function useSheetProjection(deps: {
  workspace: Ref<Workspace | null>;
  baseWorkspace: Ref<Workspace | null>;
  commands: Ref<ChangeCommand[]>;
  cadVersion: Ref<string>;
}): {
  projection: Ref<Workspace | null>;
  stamp: Ref<ProjectionStamp | null>;
  pending: Ref<boolean>;
  error: Ref<string>;
  refresh(): Promise<SubmitResult>;
} {
  const projection = ref<Workspace | null>(null);
  const stamp = ref<ProjectionStamp | null>(null);
  const pending = ref(false);
  const error = ref("");
  let generation = 0;

  async function refresh(): Promise<SubmitResult> {
    const current = deps.workspace.value;
    const base = deps.baseWorkspace.value;
    const commands = deps.commands.value;
    // 无结构动作时由本地只读副本投影显示：清空结构投影并失效在途请求，避免旧结构残留
    if (!current || !base || !commands.length || !commands.some((command) => STRUCTURAL_TYPES.has(command.type))) {
      generation += 1;
      projection.value = null;
      stamp.value = null;
      return {ok: true};
    }
    const workspaceId = current.id;
    const baseRevisionId = current.revision_id;
    const commandKey = JSON.stringify(commands);
    const requestGeneration = ++generation;
    pending.value = true;
    try {
      const preview: Preview = await request(`/api/workspaces/${workspaceId}/changes/preview`, {
        method: "POST",
        body: JSON.stringify({base_revision_id: baseRevisionId, commands, cad_version: deps.cadVersion.value}),
      });
      // 乱序响应或快照已变化：只能应用最后一个请求代次
      if (
        requestGeneration !== generation
        || deps.workspace.value?.id !== workspaceId
        || deps.workspace.value.revision_id !== baseRevisionId
        || JSON.stringify(deps.commands.value) !== commandKey
      ) return {ok: true};
      if (!preview.execution_intent?.derived_document) { stamp.value = null; error.value = "缺少结构投影，请重新预览"; return {ok: false, message: "缺少结构投影，请重新预览"}; }
      if (preview.executable === false) { stamp.value = null; error.value = "结构投影不可执行，请检查诊断"; return {ok: false, message: "结构投影不可执行，请检查诊断"}; }
      projection.value = applyDerivedProjection(base, preview);
      stamp.value = {workspaceId, revisionId: baseRevisionId, generation: requestGeneration, commandKey};
      error.value = "";
      return {ok: true};
    } catch (e) {
      // 失败保留输入与上一份结果，仅清除 stamp 标为失效，不展示“已同步”
      if (requestGeneration === generation) { stamp.value = null; error.value = String(e); }
      return {ok: false, message: String(e)};
    } finally {
      if (requestGeneration === generation) pending.value = false;
    }
  }

  return {projection, stamp, pending, error, refresh};
}
