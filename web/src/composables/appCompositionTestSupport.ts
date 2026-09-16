// Task 12 用户验收修复轮（M1）：`appComposition.test.ts` 按域拆分为四个测试文件后，
// 草稿门禁 / 生命周期 / 命令编排三组共用的夹具工厂与 API client mock 收口到本文件，
// 避免复制第二份事实源。纯机械搬迁，不改变任何断言语义。
import {computed, ref} from "vue";
import {vi} from "vitest";
import type {DraftGuardsDeps, EditorApi, PropertiesApi, SheetsFilterApi} from "./useDraftGuards";
import type {ApiError} from "../api/client";
import type {ChangeCommand, Workspace} from "../api/contracts";

// 草稿栈测试要控制草稿读写的 HTTP 结果（尤其 DRAFT_CONFLICT），故只 mock API client。
// `./drafts` 的投影实现**不 mock**：搬运要求沿用既有投影，这也正是「组合而非复制」的守卫点。
// vi.mock 工厂由各测试文件以「工厂内动态 import 本模块 → mockApiClient()」接线；
// 工厂延迟到被测模块首次加载 `../api/client` 时才执行，此刻本模块已初始化完毕，
// 故 apiRequest 无需 vi.hoisted（hoisted 变量不允许从非测试模块导出）。
// 本模块不得**值**导入 `../api/client` 或 `./useDraftGuards`：工厂正在初始化它们，
// 顶层值 import 会与「被测模块 → api client mock → 本模块」的加载顺序成环死锁。
export const apiRequest = vi.fn();

// mock 的 ApiError 构造签名（code, message）与真实类的（HTTP status + body）不同，
// 而模块靠 `instanceof` 判定 DRAFT_CONFLICT，因此用统一的 mock 类构造并强转返回类型。
class MockApiError extends Error {
  code: string;
  fields?: Record<string, string>;
  constructor(code: string, message: string, fields?: Record<string, string>) {
    super(message);
    this.code = code;
    this.fields = fields;
  }
}

export function mockApiClient() {
  return {request: apiRequest, ApiError: MockApiError};
}

export const makeApiError = (code: string, message: string): ApiError => new MockApiError(code, message) as unknown as ApiError;

export function makeEditor(overrides: Partial<EditorApi> = {}): EditorApi {
  return {
    // 每个强转只针对单个成员、转到该成员的真实类型；其余成员仍受结构检查
    context: ref(null) as EditorApi["context"],
    hasUnsavedChanges: computed(() => false),
    guard: vi.fn(async (next: () => void | Promise<void>) => { await next(); }),
    resolveGuard: vi.fn(),
    guardState: ref({open: false, summary: "", canSave: true}) as EditorApi["guardState"],
    ...overrides,
  };
}

export function makeProperties(overrides: Partial<PropertiesApi> = {}): PropertiesApi {
  return {
    guard: vi.fn(async (next: () => void | Promise<void>) => { await next(); }),
    resolveGuard: vi.fn(),
    guardState: ref({open: false, summary: "", canSave: true}) as PropertiesApi["guardState"],
    ...overrides,
  };
}

export function makeSheets(overrides: Partial<SheetsFilterApi> = {}): SheetsFilterApi {
  return {
    filteredRows: rows([]),
    snapshotState: vi.fn(() => ({})),
    restoreState: vi.fn(),
    ...overrides,
  } as unknown as SheetsFilterApi;
}

export function makeDraftDeps(overrides: Partial<DraftGuardsDeps> = {}): DraftGuardsDeps {
  return {
    workspace: ref<Workspace | null>({id: "w1", revision_id: "r1"} as unknown as Workspace),
    baseWorkspace: ref<Workspace | null>(null),
    error: ref(""),
    t: (key: string) => key,
    cloneJson: <T,>(value: T): T => JSON.parse(JSON.stringify(value)),
    invalidatePreview: vi.fn(),
    refreshSheetProjection: vi.fn(async () => ({ok: true})),
    getActive: () => "sheets",
    getEditor: () => makeEditor(),
    getProperties: () => makeProperties(),
    getSheets: () => makeSheets(),
    reloadWorkspace: vi.fn(async () => {}),
    confirmAction: vi.fn(async () => true),
    ...overrides,
  };
}

/** 测试用命令夹具：类型字段由调用方给出，其余按各命令自身字段补。 */
export const cmd = (type: ChangeCommand["type"], extra: Record<string, unknown> = {}): ChangeCommand => ({type, ...extra} as ChangeCommand);

/** 图纸行夹具：本组用例只用到 `row.sheet.id`（可见性判定），其余字段不影响被测行为。 */
export const rows = (ids: string[]): SheetsFilterApi["filteredRows"] => computed(() => ids.map(id => ({sheet: {id}})) as unknown as SheetsFilterApi["filteredRows"]["value"]);

/** 触发一次 DRAFT_CONFLICT，使草稿进入 stale 只读降级。
 * `useDraftGuards` 经动态 import 获取：本模块由 vi.mock 工厂在被测模块初始化路径上加载，
 * 顶层值 import 会与「被测模块 → api client mock → 本模块」的加载顺序成环死锁。 */
export async function makeConflicted(deps: DraftGuardsDeps) {
  const {useDraftGuards} = await import("./useDraftGuards");
  const guards = useDraftGuards(deps);
  guards.addCommand(cmd("delete_sheet", {sheet_id: "s1"}), "structural");
  apiRequest.mockRejectedValueOnce(makeApiError("DRAFT_CONFLICT", "draft version conflict"));
  await guards.pendingDraftSave();
  return guards;
}
