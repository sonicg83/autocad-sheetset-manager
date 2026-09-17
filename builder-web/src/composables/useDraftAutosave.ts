// 草稿自动保存（SPEC-DB-001 §2）：字段变更 500 ms 防抖 PATCH，
// 携带 base_updated_at 做乐观并发；409 DRAFT_CONFLICT 显式提示冲突，
// 不静默覆盖。与传输层解耦：save 由调用方注入，冲突以 error.status === 409 识别。
import {ref, watch, type Ref} from "vue";

export type AutosaveStatus = "idle" | "dirty" | "saving" | "saved" | "conflict" | "error";

export interface AutosavePatch<TDraft> {
  base_updated_at: string | null;
  draft: TDraft;
  wizard_step: number;
  focused_field: string | null;
}

export interface AutosaveResult {
  updated_at: string;
  diagnostics?: unknown[];
}

export interface DraftAutosave<TDraft> {
  status: Ref<AutosaveStatus>;
  /** 深度监听 draft 的调用方无需手动触发；此方法供显式补调度。 */
  schedule: () => void;
  /** 立即保存待保存变更；force=true 时即使无待保存变更也保存（如步骤切换持久化 wizard_step）。 */
  flush: (force?: boolean) => Promise<void>;
  pause: () => void;
  resume: () => void;
  dispose: () => void;
}

function isConflict(error: unknown): boolean {
  const candidate = error as {status?: unknown; code?: unknown} | null;
  return (
    candidate instanceof Object &&
    (candidate.status === 409 || candidate.code === "DRAFT_CONFLICT")
  );
}

export function createDraftAutosave<TDraft extends object>(options: {
  draft: TDraft;
  save: (patch: AutosavePatch<TDraft>) => Promise<AutosaveResult>;
  getBaseUpdatedAt: () => string | null;
  getWizardStep: () => number;
  getFocusedField: () => string | null;
  debounceMs?: number;
  onSaved?: (result: AutosaveResult) => void;
  onConflict?: (error: unknown) => void;
  onError?: (error: unknown) => void;
}): DraftAutosave<TDraft> {
  const debounceMs = options.debounceMs ?? 500;
  const status = ref<AutosaveStatus>("idle");
  let timer: ReturnType<typeof setTimeout> | null = null;
  let paused = false;
  let disposed = false;

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const persist = async (): Promise<void> => {
    clearTimer();
    status.value = "saving";
    try {
      const result = await options.save({
        base_updated_at: options.getBaseUpdatedAt(),
        draft: options.draft,
        wizard_step: options.getWizardStep(),
        focused_field: options.getFocusedField(),
      });
      status.value = "saved";
      options.onSaved?.(result);
    } catch (error) {
      if (isConflict(error)) {
        status.value = "conflict";
        options.onConflict?.(error);
      } else {
        status.value = "error";
        options.onError?.(error);
      }
    }
  };

  const schedule = (): void => {
    if (paused || disposed) {
      return;
    }
    clearTimer();
    status.value = "dirty";
    timer = setTimeout(() => {
      timer = null;
      void persist();
    }, debounceMs);
  };

  const stop = watch(options.draft, schedule, {deep: true, flush: "sync"});

  return {
    status,
    schedule,
    flush: (force = false) => {
      if (!force && timer === null && status.value !== "dirty") {
        return Promise.resolve();
      }
      return persist();
    },
    pause: () => {
      paused = true;
      clearTimer();
    },
    resume: () => {
      paused = false;
    },
    dispose: () => {
      disposed = true;
      clearTimer();
      stop();
    },
  };
}
