// Builder 后端全量 mock（PLAN-DB-001 Task 5 controller 裁决）：
// e2e 用 page.route 拦截全部 /api/** 端点，不依赖真实后端进程。
// 形状与 builder-web/src/api/openapi.json（SPEC-DB-001 §11）一致；
// 步骤 5～6 端点（/api/plans、/api/builds…）由 Task 9 才实现，
// 这里 mock 的响应形状只服务本任务前端状态机，真实接线时以 Task 9 契约为准。
import type {Page} from "@playwright/test";

export interface MockDiagnostic {
  code: string;
  severity: string;
  message: string;
  field?: string | null;
}

export interface MockDraft {
  schema_version: 1;
  project: {name: string; stage: string; discipline: string; output_path: string};
  numbering: {prefix: string; start: number; width: number};
  cad_version: string;
  sheets: {title: string}[];
  template: {base_asset_id: string; layout_asset_id: string; source_layout: string};
}

export interface BackendMockOptions {
  /** false → GET /api/projects/current 返回 404（未创建项目）。 */
  initialized?: boolean;
  /** 初始恢复的 wizard_step / focused_field。 */
  wizardStep?: number;
  focusedField?: string | null;
  draft?: Partial<MockDraft>;
  /** PATCH 成功响应携带的字段诊断。 */
  patchDiagnostics?: MockDiagnostic[];
  /** "ok" | 409 冲突 | 带 field 的 400 错误。 */
  patchBehavior?: "ok" | "conflict" | "fieldError";
  patchErrorField?: string;
  patchErrorMessage?: string;
  /** 布局探测：默认 501 CAD_VERSION_UNAVAILABLE；"ok" 时返回 layouts。 */
  inspect?: {mode: "unavailable"} | {mode: "ok"; layouts: string[]};
  /** GET /api/builds/{id} 依次返回的状态序列（每次 GET 前进一步，末态后保持）。 */
  buildSequence?: {status: string; progress: number}[];
}

export function defaultDraft(): MockDraft {
  return {
    schema_version: 1,
    project: {
      name: "示例工程",
      stage: "施工图",
      discipline: "建筑",
      output_path: "D:/deliveries/example-package",
    },
    numbering: {prefix: "A-", start: 1, width: 3},
    cad_version: "2020",
    sheets: [{title: "首层平面图"}],
    template: {base_asset_id: "", layout_asset_id: "", source_layout: ""},
  };
}

export class BackendMock {
  readonly calls = {
    createProject: [] as Record<string, unknown>[],
    patchDraft: [] as Record<string, unknown>[],
    createAsset: [] as Record<string, unknown>[],
    inspect: [] as Record<string, unknown>[],
    plans: 0,
    confirm: 0,
    startBuild: 0,
    cancelBuild: 0,
  };

  state: {
    initialized: boolean;
    wizard_step: number;
    focused_field: string | null;
    updated_at: string;
    draft: MockDraft;
    diagnostics: MockDiagnostic[];
  };

  patchBehavior: "ok" | "conflict" | "fieldError";
  patchErrorField: string;
  patchErrorMessage: string;
  patchDiagnostics: MockDiagnostic[];
  inspect: {mode: "unavailable"} | {mode: "ok"; layouts: string[]};
  buildSequence: {status: string; progress: number}[];
  private buildIndex = 0;
  private updatedAtCounter = 0;

  constructor(
    private readonly page: Page,
    options: BackendMockOptions = {},
  ) {
    this.state = {
      initialized: options.initialized ?? false,
      wizard_step: options.wizardStep ?? 1,
      focused_field: options.focusedField ?? null,
      updated_at: "2026-09-17T08:00:00Z",
      draft: {...defaultDraft(), ...options.draft},
      diagnostics: [],
    };
    this.patchBehavior = options.patchBehavior ?? "ok";
    this.patchErrorField = options.patchErrorField ?? "project.output_path";
    this.patchErrorMessage = options.patchErrorMessage ?? "成果目录已存在";
    this.patchDiagnostics = options.patchDiagnostics ?? [];
    this.inspect = options.inspect ?? {mode: "unavailable"};
    this.buildSequence = options.buildSequence ?? [
      {status: "BUILDING_DWG", progress: 20},
      {status: "BUILDING_DST", progress: 60},
      {status: "SUCCEEDED", progress: 100},
    ];
  }

  async install(): Promise<void> {
    // 用谓词精确匹配 /api/ 路径：glob "**/api/**" 会误伤 vite 的模块 URL
    //（如 /src/api/client.ts），导致应用无法加载。
    await this.page.route(
      (url) => url.pathname.startsWith("/api/"),
      (route) => {
        void this.handle(route.request().method(), new URL(route.request().url()).pathname, route);
      },
    );
  }

  private nextState() {
    this.updatedAtCounter += 1;
    return {
      opened_existing: false,
      project: {
        id: "0b0e-uuid",
        name: this.state.draft.project.name,
        stage: this.state.draft.project.stage,
        discipline: this.state.draft.project.discipline,
        output_path: this.state.draft.project.output_path,
        created_at: "2026-09-17T07:00:00Z",
        updated_at: this.state.updated_at,
      },
      draft: this.state.draft,
      wizard_step: this.state.wizard_step,
      focused_field: this.state.focused_field,
      updated_at: this.state.updated_at,
      diagnostics: this.state.diagnostics,
    };
  }

  private patchErrorPayload() {
    return {
      code: "PROJECT_PATH_INVALID",
      message: this.patchErrorMessage,
      field: this.patchErrorField,
      recovery_action: "修改后重试",
      details: null,
    };
  }

  private async handle(method: string, path: string, route: Parameters<Parameters<Page["route"]>[1]>[0]): Promise<void> {
    const reply = (status: number, body: unknown) =>
      route.fulfill({status, contentType: "application/json", body: JSON.stringify(body)});

    if (method === "GET" && path === "/api/projects/current") {
      if (!this.state.initialized) {
        return reply(404, {
          code: "PROJECT_NOT_INITIALIZED",
          message: "尚未绑定项目根目录",
          field: null,
          recovery_action: "先创建项目",
          details: null,
        });
      }
      return reply(200, this.nextState());
    }

    if (method === "POST" && path === "/api/projects") {
      const body = (await route.request().postDataJSON()) as Record<string, unknown>;
      this.calls.createProject.push(body);
      this.state.initialized = true;
      this.state.draft.project = {
        name: String(body.name ?? ""),
        stage: String(body.stage ?? ""),
        discipline: String(body.discipline ?? ""),
        output_path: String(body.output_path ?? ""),
      };
      return reply(201, this.nextState());
    }

    if (method === "PATCH" && path === "/api/projects/current/draft") {
      const body = (await route.request().postDataJSON()) as Record<string, unknown>;
      this.calls.patchDraft.push(body);
      if (this.patchBehavior === "conflict") {
        return reply(409, {
          code: "DRAFT_CONFLICT",
          message: "草稿已被其他会话修改",
          field: null,
          recovery_action: "刷新后重试",
          details: null,
        });
      }
      if (this.patchBehavior === "fieldError") {
        return reply(400, this.patchErrorPayload());
      }
      this.state.draft = body.draft as MockDraft;
      this.state.wizard_step = Number(body.wizard_step ?? 1);
      this.state.focused_field = (body.focused_field as string | null) ?? null;
      this.updatedAtCounter += 1;
      this.state.updated_at = `2026-09-17T08:00:${String(this.updatedAtCounter).padStart(2, "0")}Z`;
      this.state.diagnostics = this.patchDiagnostics;
      return reply(200, this.nextState());
    }

    if (method === "POST" && path === "/api/assets") {
      const body = (await route.request().postDataJSON()) as {role: string; source_path: string};
      this.calls.createAsset.push(body);
      const role = body.role;
      const sha = role === "base" ? "aa11".repeat(16) : "bb22".repeat(16);
      return reply(201, {
        id: role === "base" ? "asset-base-1" : "asset-layout-1",
        role,
        relative_path: `assets/${role}/${sha.slice(0, 12)}.dwg`,
        sha256: sha,
        size: 1024,
        source_name: body.source_path.split(/[\\/]/).pop() ?? "asset.dwg",
      });
    }

    if (method === "POST" && path.startsWith("/api/assets/") && path.endsWith("/inspect")) {
      const assetId = path.split("/")[3];
      const body = (await route.request().postDataJSON()) as {cad_version: string};
      this.calls.inspect.push({asset_id: assetId, ...body});
      if (this.inspect.mode === "unavailable") {
        return reply(501, {
          code: "CAD_VERSION_UNAVAILABLE",
          message: "布局 inspection 端口尚未接线，无法读取布局",
          field: null,
          recovery_action: "等待 CAD 探测接线后重试",
          details: null,
        });
      }
      return reply(200, {asset_id: assetId, cad_version: body.cad_version, layouts: this.inspect.layouts});
    }

    if (method === "GET" && path === "/api/cadabilities") {
      const available = this.inspect.mode === "ok";
      return reply(200, {
        capabilities: [
          {cad_version: "2016", available, console_path: null, plugin_path: null, unavailable_reason: available ? null : "未找到 accoreconsole.exe"},
          {cad_version: "2020", available, console_path: null, plugin_path: null, unavailable_reason: available ? null : "未找到 accoreconsole.exe"},
        ],
      });
    }

    if (method === "POST" && path === "/api/plans") {
      this.calls.plans += 1;
      return reply(201, {
        plan_id: "plan-1",
        revision_id: "rev-1",
        revision_sha256: "f".repeat(64),
        diagnostics: [],
        preview: {
          sheet_number: "A-001",
          layout_name: "A-001 首层平面图",
          dwg_name: "A-001 首层平面图.dwg",
          artifact_path: "A-001 首层平面图.dwg",
        },
      });
    }

    if (method === "POST" && path === "/api/plans/plan-1/confirm") {
      this.calls.confirm += 1;
      return reply(200, {plan_id: "plan-1", confirmed_at: "2026-09-17T08:30:00Z"});
    }

    if (method === "POST" && path === "/api/builds") {
      this.calls.startBuild += 1;
      this.buildIndex = 0;
      return reply(201, {build_id: "build-1", status: "QUEUED", progress: 0});
    }

    if (method === "POST" && path === "/api/builds/build-1/cancel") {
      this.calls.cancelBuild += 1;
      return reply(202, {build_id: "build-1", status: "CANCELLED", progress: 40});
    }

    if (method === "GET" && path === "/api/builds/build-1") {
      const current = this.buildSequence[Math.min(this.buildIndex, this.buildSequence.length - 1)];
      if (this.buildIndex < this.buildSequence.length - 1) {
        this.buildIndex += 1;
      }
      return reply(200, {
        build_id: "build-1",
        plan_id: "plan-1",
        status: current.status,
        progress: current.progress,
        error_code: null,
        published_path: current.status === "SUCCEEDED" ? "D:/deliveries/example-package" : null,
      });
    }

    return reply(404, {code: "NOT_FOUND", message: `mock 未实现 ${method} ${path}`, field: null, recovery_action: "", details: null});
  }
}
