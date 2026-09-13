---
id: PLAN-DM-025
title: Builtin 扩展全局设置框架实施计划
status: active
document_kind: plan
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-13
related:
  - ARCH-DM-004
  - ARCH-DM-005
  - ARCH-DM-006
  - SPEC-DM-011
  - SPEC-DM-012
  - GUIDE-DM-005
  - PLAN-DM-020
  - PLAN-DM-026
  - MEMO-DM-033
---

# Builtin 扩展全局设置框架实施计划

> **供代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实施。步骤使用 `- [ ]` 跟踪，严格执行 red → green → refactor；每个任务完成后独立复核并提交。

**目标：** 把图纸目录专用设置分派升级为受信 Builtin 扩展通用的当前 Windows 用户级设置框架，提供 Provider 语义、generated/custom 两类设置入口、Schema 迁移、乐观并发和 preview/execute 设置快照门禁，并以图纸目录“输出图纸过滤”作为首个会改变动作输出的真实全局配置验证。

**架构：** 设置值继续存入既有 `extension_settings`，不新增数据库表。Manifest 只声明呈现，`ExtensionSettingsProvider` 唯一定义默认值、校验、规范化、迁移和解析，独立应用服务负责编排，Runtime 只做组合与错误映射；每次动作取得不可变设置快照并把修订与摘要绑定到预览。设置中心保留统一入口，简单字段由宿主生成表单，复杂设置由编译期白名单组件呈现。

**技术栈：** Python 3.12、Pydantic、FastAPI、SQLAlchemy/SQLite、Vue 3、TypeScript、vue-i18n、Vite、Playwright、pytest、UV。

**规范：** [ARCH-DM-006](../../../docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md) §4.2、§7、§8、§11～§14；[ARCH-DM-004](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)；[SPEC-DM-011](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)；[SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md)；[GUIDE-DM-005](../../../docs/dst-manager/guides/GUIDE-DM-005-builtin-extension-development.md) §8。

## 全局约束

- 执行前阅读根 `README.md`、`docs/README.md`、`docs/dst-manager/README.md`、ARCH-DM-001、ARCH-DM-004、ARCH-DM-006、SPEC-DM-011、SPEC-DM-012 与 GUIDE-DM-005。
- 目标环境为 Windows 11 / PowerShell；Python 不低于 3.12，统一使用 UV；本计划不需要新增 Python 或 npm 依赖。
- 只复用 `extension_settings`；不得新增另一份 JSON 文件、插件自建表或插件直接数据库访问。
- 设置作用域固定为当前 Windows 用户且跨工作区共享；工作区偏好继续使用 `workspace_extension_preferences`。
- `value_json` 只存用户显式配置或用户创建的数据；默认值、校验和迁移语义只存在于 Provider。
- 凭据、令牌和 API Key 不进入普通扩展设置；错误、日志、任务记录或摘要不得记录完整设置值。
- Manifest 不携带 Python 模块名、类名、Vue 模块路径或 URL；工厂、Provider 和自定义组件均由编译期白名单直接引用。
- `application/extensions/runtime.py` 已有 781 行，`SettingsDialog.vue` 已有 535 行，均越过容量软上限；新增语义必须进入新模块，入口只保留委托和装配。任务 7 开始前先由任务 6 抽出关于分区，使 `SettingsDialog.vue` 回落到约 500 行以内。
- PLAN-DM-025 与 PLAN-DM-026 都会修改图纸目录 preview、API 类型和前端目录组件，不得并行实施；后开始者必须基于先完成者的提交重新核对文件职责、摘要输入和全量回归，不得覆盖对方的数字格式码或过滤语义。
- 每项运行时代码先写能因目标能力缺失而失败的测试；每个任务更新 `changelog.md` 并只提交自身文件。

## 文件职责

| 文件 | 单一职责 |
| --- | --- |
| `src/dst_manager/extensions/settings.py` | 设置值对象、Provider Protocol、JSON 冻结与摘要 |
| `src/dst_manager/application/extensions/settings.py` | Provider 一致性、读取、迁移、校验、保存和快照编排 |
| `src/dst_manager/extensions/builtin/sheet_catalog/settings.py` | 图纸目录 Provider、过滤关键词规范化与图名排除纯函数，复用模板纯业务函数 |
| `web/src/composables/useExtensionSettings.ts` | 单扩展设置加载、缓冲、保存、冲突和只读状态 |
| `web/src/components/settings/ExtensionSettingsHost.vue` | generated/custom 分派、返回和焦点协调 |
| `web/src/components/settings/GeneratedExtensionSettingsForm.vue` | 简单字段动态表单 |
| `web/src/components/settings/SheetCatalogSettingsPanel.vue` | 不依赖工作区的复杂模板设置界面 |
| `web/src/components/settings/AboutSection.vue` | 关于分区呈现与单次懒加载 |
| `web/src/composables/useSheetCatalogSettings.ts` | 图纸目录模板、过滤文本、草稿、光标与同一设置修订冲突 |

---

### 任务 1：建立 Provider 与 Manifest 契约

**文件：**

- 新建：`src/dst_manager/extensions/settings.py`
- 修改：`src/dst_manager/extensions/contracts.py`
- 修改：`src/dst_manager/extensions/manifest.py`
- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml`
- 修改：`tests/unit/test_extension_manifest.py`
- 新建：`tests/unit/test_extension_settings_contracts.py`
- 修改：`changelog.md`

**接口：** 产出 `SettingsFieldDefinition`、`SettingsContribution`、`ExtensionSettingsProvider`、`ExtensionSettingsSnapshot`、`freeze_json()` 与 `settings_digest()`；`BuiltinExtensionEntry.settings_provider` 为 Provider 或 `None`。

- [x] **步骤 1：写 Manifest 失败测试。** 覆盖 generated/custom 成功解析，以及缺 route、重复字段、混用 payload、未知 presentation 和任意模块路径被拒绝。

  ```python
  def test_custom_settings_contribution_requires_route_key():
      data = valid_manifest()
      data["settings_contribution"] = {"presentation": "custom"}
      with pytest.raises(ManifestError, match="route_key"):
          parse_manifest(data)

  def test_generated_settings_fields_must_be_unique():
      data = valid_manifest()
      data["settings_contribution"] = {
          "presentation": "generated",
          "fields": [field("max_rows"), field("max_rows")],
      }
      with pytest.raises(ManifestError, match="字段 key 必须唯一"):
          parse_manifest(data)
  ```

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_extension_manifest.py tests/unit/test_extension_settings_contracts.py -q
  ```

  预期：新契约尚不存在，且 Manifest 不认识 `settings_contribution`。

- [x] **步骤 3：实现冻结值对象和 Protocol。** 使用递归 `freeze_json()` 把 dict/list 转为只读 Mapping/tuple；摘要对规范 JSON 使用 `sort_keys=True` 和紧凑 separators。

  ```python
  @dataclass(frozen=True, slots=True)
  class ExtensionSettingsSnapshot:
      extension_id: str
      schema_version: int
      revision: int
      value: Mapping[str, FrozenJson]
      digest: str

  class ExtensionSettingsProvider(Protocol):
      extension_id: str
      schema_version: int
      field_definitions: tuple[SettingsFieldDefinition, ...]
      def default_value(self) -> dict[str, object]: ...
      def migrate(self, stored_schema_version: int, value: dict[str, object]) -> dict[str, object]: ...
      def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]: ...
      def resolve(self, value: dict[str, object]) -> dict[str, object]: ...
  ```

- [x] **步骤 4：实现严格呈现声明。** `generated` 要求非空且 key 唯一的 `fields` 并禁止 route；`custom` 要求 `route_key` 并禁止 fields。字段只含 `key/label_key/description_key/order`，不重复类型和约束。

- [x] **步骤 5：图纸目录 Manifest 声明 custom 设置。**

  ```yaml
  settings_contribution:
    presentation: custom
    route_key: sheet-catalog-settings
  ```

- [x] **步骤 6：运行绿灯和注册表回归。**

  ```powershell
  rtk uv run pytest tests/unit/test_extension_manifest.py tests/unit/test_extension_settings_contracts.py tests/unit/test_extension_registry.py -q
  ```

- [x] **步骤 7：记录并提交。** commit message：`建立扩展设置 Provider 与清单契约`。

### 任务 2：实现 Provider 注册、迁移和通用设置编排

**文件：**

- 新建：`src/dst_manager/application/extensions/settings.py`
- 新建：`src/dst_manager/extensions/builtin/sheet_catalog/settings.py`
- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml`
- 修改：`src/dst_manager/extensions/builtin/index.py`
- 修改：`src/dst_manager/application/extensions/runtime.py`
- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/templates.py`
- 新建：`tests/unit/test_extension_settings_service.py`
- 新建：`tests/unit/test_sheet_catalog_settings.py`
- 修改：`tests/unit/test_sheet_catalog_templates.py`
- 修改：`tests/integration/test_extension_api.py`
- 修改：`changelog.md`

**接口：** `ExtensionSettingsService.get/put/snapshot` 返回版本化视图或不可变快照；未知高版本返回原 JSON 的只读视图；旧版本只做内存迁移，用户下一次保存时才写回。`SheetCatalogSettingsProvider.schema_version=2`；`normalize_excluded_title_keywords(value)` 返回去空、按 `casefold()` 去重且保留首次原文顺序的 tuple；`title_matches_exclusion(title, keywords)` 只做大小写不敏感字面子串 OR 匹配。

- [x] **步骤 1：写服务与图纸目录 Provider 红灯。** 使用 FakeStore/FakeProvider 覆盖零值、默认值解析、合法/非法保存、冲突、v1→v2 内存迁移不落库、迁移失败、未知 v3 保留、ID/Schema 不一致和重复 Provider。图纸目录用真实 v1 `{schema_version: 1, user_templates: [...]}` 覆盖迁移后模板原样保留、过滤词默认为空且不主动写库；覆盖 `草图， TEMP,,作废,temp` 规范化为 `("草图", "TEMP", "作废")`、多个词 OR、Unicode 大小写、空图名、50/51 项和 100/101 字符边界。

  ```python
  def test_older_schema_is_migrated_without_writing_store():
      store.current = VersionedJson(1, 4, {"limit": 10})
      view = service.get(manifest(settings_schema=2))
      assert view.value == {"max_rows": 10}
      assert view.revision == 4
      assert store.put_calls == []

  def test_newer_schema_is_read_only_and_preserved():
      raw = {"future": {"keep": [1, 2]}}
      store.current = VersionedJson(3, 8, raw)
      view = service.get(manifest(settings_schema=2))
      assert view.read_only is True
      assert view.value == raw
  ```

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_extension_settings_service.py tests/unit/test_sheet_catalog_settings.py tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q
  ```

- [x] **步骤 3：实现独立设置服务。** 服务可依赖 `ExtensionStore`；Provider 不依赖基础设施。Provider 异常转换成 `ExtensionSettingsError(code,status_code,params)`，Runtime 再映射为平台错误。

- [x] **步骤 4：实现 `SheetCatalogSettingsProvider` 与过滤纯函数，并把图纸目录 Manifest 的 `settings_schema` 从 1 升为 2。** 把 Runtime 的模板解析、UUID/重名/数量/内置不可变校验迁入 Provider；Schema v2 默认持久值为 `{}`，有效值合并代码内置模板与空过滤词，只把用户模板和用户显式过滤词序列化回 Store。v1→v2 保留 `user_templates` 并在解析态补空过滤数组，不主动落库。过滤输入接受 `,`/`，`，trim 后忽略空项、按 `casefold()` 去重；空结果从持久值移除但有效值仍返回空数组；超过 50 项或单项 100 字符时返回字段 `excluded_title_keywords` 的 `EXTENSION_SETTINGS_INVALID`，不得截断。现有实现本来只持久化 `user_templates`，不新增“完整模板集剥离”迁移。Schema 升级与 Provider 在同一提交交付，任务 1 不提前改版本，避免中间提交让现有模板保存被 Manifest 版本检查拒绝。

- [x] **步骤 5：固定索引登记 Provider 并校验 Manifest/Provider 的 ID、Schema 与字段覆盖；单扩展错误只隔离自身。**

- [x] **步骤 6：Runtime 删除 `_TEMPLATE_SETTINGS_EXTENSION_ID`、`_save_catalog_templates()` 和专用 `if`，仅委托设置服务。**

- [x] **步骤 7：运行绿灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_extension_settings_service.py tests/unit/test_extension_persistence.py tests/unit/test_sheet_catalog_settings.py tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q
  ```

- [x] **步骤 8：记录并提交。** commit message：`通用化扩展设置校验与迁移编排`。

### 任务 3：开放设置呈现与只读 API 契约

**文件：**

- 修改：`src/dst_manager/interfaces/extension_contracts.py`
- 修改：`src/dst_manager/interfaces/extension_api.py`
- 修改：`src/dst_manager/interfaces/message_catalog.py`
- 修改：`tests/unit/test_message_catalog.py`
- 修改：`tests/integration/test_extension_api.py`
- 修改：`web/src/api/openapi.json`
- 修改：`web/src/api/schema.d.ts`
- 修改：`changelog.md`

**接口：** Summary 新增 `settings_contribution`；GET/PUT settings 使用 `ExtensionSettingsResponseModel`，保留 `schema_version/revision/value` 并增加 `effective_value/read_only/diagnostic_code/items`。未知高版本 GET 为 200 只读且 `diagnostic_code=EXTENSION_SETTINGS_SCHEMA_NEWER`，PUT 返回同一稳定 `code` 和 HTTP 409。

- [x] **步骤 1：写 API 红灯。** 覆盖 generated 字段合并、custom route、无设置扩展、未知高版本 GET/PUT、非法字段 422 与并发 409；图纸目录 PUT 原始过滤文本后 GET 返回规范化 `excluded_title_keywords` 数组，空文本清除显式覆盖。generated 后端全链路使用测试内临时 Manifest、FakeProvider 和 `BuiltinExtensionEntry(settings_provider=...)`，通过既有 `extension_index`/`ExtensionRuntime` 注入；不得为测试向生产固定索引增加虚构扩展。

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk uv run pytest tests/integration/test_extension_api.py tests/unit/test_message_catalog.py -q
  ```

- [x] **步骤 3：实现响应模型与映射。** 字段项由 Provider 的类型/默认值/约束和 Manifest 的 label/description/order 合并，按 `order,key` 排序；custom 的 `items=[]`。

  ```python
  class ExtensionSettingsResponseModel(ContractModel):
      schema_version: int
      revision: int
      value: dict[str, object]
      effective_value: dict[str, object]
      read_only: bool = False
      diagnostic_code: str | None = None
      items: list[ExtensionSettingsItemModel] = Field(default_factory=list)
  ```

- [x] **步骤 4：把 `EXTENSION_SETTINGS_SCHEMA_NEWER` 登记为稳定错误码及文案键，并生成 OpenAPI。**

  ```powershell
  rtk npm --prefix web run generate:api
  rtk npm --prefix web run check:api
  ```

- [x] **步骤 5：运行绿灯并提交。**

  ```powershell
  rtk uv run pytest tests/integration/test_extension_api.py tests/unit/test_message_catalog.py -q
  ```

  commit message：`开放扩展设置呈现与只读诊断契约`。

### 任务 4：绑定动作级不可变设置快照

**文件：**

- 修改：`src/dst_manager/extensions/capabilities.py`
- 修改：`src/dst_manager/application/extensions/runtime.py`
- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/extension.py`
- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/preview.py`
- 修改：`src/dst_manager/interfaces/extension_contracts.py`
- 修改：`src/dst_manager/interfaces/extension_api.py`
- 修改：`tests/unit/test_extension_snapshot.py`
- 修改：`tests/unit/test_sheet_catalog_preview.py`
- 修改：`tests/integration/test_extension_api.py`
- 修改：`tests/integration/test_sheet_catalog_export.py`
- 修改：`web/src/composables/useSheetCatalog.ts`
- 修改：`web/src/api/openapi.json`
- 修改：`web/src/api/schema.d.ts`
- 修改：`changelog.md`

**接口：** `ExtensionContext.settings` 返回冻结快照；Preview 响应和 Execute 请求新增 `settings_revision`；摘要加入设置 Schema/修订/digest。`SheetCatalogPreview`/`SheetCatalogPreviewResponse` 新增 `filtered_rows: int`，`total_rows` 改为过滤后的实际输出行数。修订不一致返回 `EXTENSION_SETTINGS_CHANGED`/409，且发生在候选目录与授权消费之前。只有会改变输出的工作区偏好才进入动作摘要；当前“上次选中模板 ID”不改变规范化动作请求或输出，因此不绑定。

- [x] **步骤 1：写 Context 红灯。** 断言嵌套值递归冻结、源 dict 修改不影响快照、Context 关闭后设置与工作区能力都拒绝。

- [x] **步骤 2：写过滤投影、摘要与执行漂移红灯。** 覆盖半/全角输入规范化后的关键词对 `SheetSnapshot.title` 大小写不敏感 OR 匹配；排除图纸不进入 rows、不计缺值 warning；部分过滤返回过滤后 `total_rows` 与 `filtered_rows`；全部过滤仍 `executable=true` 并导出只有表头。只改过滤设置也改变设置 digest；预览后 PUT 新过滤词再执行返回 409、授权未消费、无候选文件和 Artifact；预览结束后的 best-effort“上次选中模板”偏好写入不得使该预览自行过期。

  ```python
  preview = client.post(preview_url, json=preview_payload()).json()
  put_settings(client, {"excluded_title_keywords": ["作废"]}, expected_revision=preview["settings_revision"])
  response = client.post(execute_url, json={
      **execute_payload(preview),
      "settings_revision": preview["settings_revision"],
  })
  assert response.status_code == 409
  assert response.json()["code"] == "EXTENSION_SETTINGS_CHANGED"
  assert artifact_exporter.calls == []
  ```

- [x] **步骤 3：运行红灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_extension_snapshot.py tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py tests/integration/test_sheet_catalog_export.py -q
  ```

- [x] **步骤 4：Runtime 在创建 Capability Context 前取得快照，Broker 只转交、不读 Store；ExtensionContext 对关闭后的 settings 访问 fail-closed。**

- [x] **步骤 5：接入过滤投影并扩展 canonical 摘要和 HTTP/前端请求。** Preview 与 Execute 从同一 `ExtensionContext.settings` 快照读取规范关键词，调用任务 2 的同一 `title_matches_exclusion()`；必须先过滤再求值和统计缺值。图纸目录预览回传 `settings_revision`、过滤后的 `total_rows` 与 `filtered_rows`，前端执行时原样重复提交设置修订；按已由 MEMO-DM-033 修订的 ARCH-DM-006 §11/§12，只绑定影响输出且未进入规范化动作请求的工作区偏好。当前 last-selected 偏好不绑定，未来新增影响输出的偏好仍须以 `REPREVIEW_REQUIRED`/409 拒绝漂移。

- [x] **步骤 6：在副作用前检查设置漂移，重新生成 OpenAPI并运行绿灯。**

  ```powershell
  rtk npm --prefix web run generate:api
  rtk uv run pytest tests/unit/test_extension_snapshot.py tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py tests/integration/test_sheet_catalog_export.py -q
  rtk npm --prefix web run check:api
  ```

- [x] **步骤 7：记录并提交。** commit message：`绑定扩展动作设置快照与预览摘要`。

### 任务 5：重开扩展配置入口的 UI 设计门禁

**文件：**

- 修改：`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`
- 修改：`docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html`
- 修改：`web/tests/e2e/settings-demo-visual-evidence.spec.ts`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/g4-13-extension-config-entry-light.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/g4-14-extension-config-generated-light.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/g4-15-extension-config-custom-dark.png`
- 修改：`changelog.md`

**设计裁决：** 卡片本体继续不可点击；仅声明设置时显示文字按钮“配置”。配置进入同一 Settings `<dialog>` 子视图，使用可见“返回扩展列表”，不叠加设置模态。每个扩展独立保存；子视图 dirty 纳入返回、Esc、遮罩和关闭确认。图纸目录 custom 面板包含单行“输出图纸过滤”文本框，说明“图名包含任一关键词时不写入目录，多个关键词用逗号分隔”，占位示例“草图, 作废, TEMP”。

- [x] **步骤 1：更新 SPEC-DM-011。** 修订 SC-16，并新增 SC-17：统一配置入口、generated/custom、无工作区访问、独立保存、焦点归还和脏状态闸门。

- [x] **步骤 2：更新 Demo。** 增加有/无设置卡片、generated 表单、custom 模板设置、输出图纸过滤文本框、字段超限错误、冲突和只读状态；动作行 DOM 顺序固定为“配置按钮 → 状态文字 → 开关”，可访问名为“配置 {name}”。

- [x] **步骤 3：运行 Demo 行为和截图测试。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/settings-demo-visual-evidence.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 4：仅用键盘完成进入、编辑、返回确认、保存和焦点归还，确认所有焦点可见且不被页脚遮挡。**

- [x] **步骤 5：暂停并请求用户确认 G4。** 展示三张新冻结图和 Demo；没有明确确认不得开始任务 7、8，任务 6 的容量拆分可独立进行。确认后记录确认人和日期。

- [x] **步骤 6：记录并提交。** commit message：`重开扩展全局设置入口设计门禁`。

### 任务 6：先拆分超限的 SettingsDialog 关于分区

**文件：**

- 新建：`web/src/components/settings/AboutSection.vue`
- 修改：`web/src/components/settings/SettingsDialog.vue`
- 修改：`web/src/api/settings.ts`
- 新建：`web/src/api/settings.test.ts`
- 修改：`web/tests/e2e/settings-dialog.spec.ts`
- 修改：`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`
- 修改：`changelog.md`

**接口：** `fetchAbout()` 使用模块级 Promise memo，首次调用完成后复用同一静态应用元数据；`AboutSection.vue` 自持 loading/error/about 呈现，反复切换分区不重放 GET；SettingsDialog 只装配分区，不保留关于页请求逻辑。

- [x] **步骤 1：写拆分红灯。** 在 `settings.test.ts` mock `fetch`，并发调用两次 `fetchAbout()` 只允许一个网络请求；首次 Promise reject 后再次调用必须重新请求。在 `settings-dialog.spec.ts` 统计 `/api/about` 请求次数，断言“关于 → 扩展 → 关于”仍只请求一次，并锁定应用名、版本、MIT 正文、外链可访问名和焦点行为。

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:unit -- src/api/settings.test.ts
  rtk npm --prefix web run test:e2e -- tests/e2e/settings-dialog.spec.ts --grep "关于分区.*不重复请求" --workers=1 --retries=0
  ```

  预期：单元测试因当前 `fetchAbout()` 每次直接请求而失败；既有 E2E 行为保持通过，作为拆分前安全网。

- [x] **步骤 3：实现模块级 memo 与 AboutSection。** Promise 失败时清除 memo，允许下次显式重试；成功结果在应用会话内复用。迁移现有模板和样式时保持 i18n key、可访问名、加载/失败态与外链行为不变。

- [x] **步骤 4：复核容量与完整回归。** `SettingsDialog.vue` 必须回落到 500 行以内；若仍超限，不得开始任务 7，应在本任务继续抽取具有独立职责的分区呈现，而不是追加 generated 装配。

  ```powershell
  rtk powershell -NoProfile -Command "(Get-Content -LiteralPath 'web/src/components/settings/SettingsDialog.vue' -Encoding UTF8).Count"
  rtk npm --prefix web run test:unit -- src/api/settings.test.ts
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e -- tests/e2e/settings-dialog.spec.ts tests/e2e/extensions-settings.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 5：更新 SPEC-DM-011 的关于分区加载语义，记录并提交。** commit message：`拆分设置对话框关于分区`。

### 任务 7：实现 generated 设置宿主与导航

**文件：**

- 修改：`web/src/api/extensions.ts`
- 新建：`web/src/composables/useExtensionSettings.ts`
- 新建：`web/src/components/settings/ExtensionSettingsHost.vue`
- 新建：`web/src/components/settings/GeneratedExtensionSettingsForm.vue`
- 修改：`web/src/components/settings/ExtensionCard.vue`
- 修改：`web/src/components/settings/ExtensionsSection.vue`
- 修改：`web/src/components/settings/SettingsDialog.vue`
- 修改：`web/src/i18n/locales/zh-CN/settings.ts`
- 修改：`web/src/i18n/locales/en-US/settings.ts`
- 修改：`web/tests/e2e/fixtures/extensions.ts`
- 修改：`web/tests/e2e/extensions-settings.spec.ts`
- 修改：`web/tests/e2e/settings-extensions-production-evidence.spec.ts`
- 修改：`changelog.md`

**接口：** `useExtensionSettings(id)` 独占该扩展的快照、edits、dirty、loading、saving、fieldErrors、conflict 和 readOnly；Host 负责分派和焦点，SettingsDialog 只装配当前 ID 与 dirty。

- [x] **步骤 1：写 generated E2E 红灯。** 覆盖按钮条件、无工作区、默认值、保存与重开、422 聚焦、409 保留输入、未知高版本只读、返回/关闭确认和焦点归还。显式重写 SC-16 旧钉子：声明设置的卡片按 DOM 顺序只有“配置”按钮与开关两个可聚焦元素；无设置卡片仍只有开关；卡片容器本身继续不可点击、不可聚焦。

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/extensions-settings.spec.ts --grep "扩展配置入口|generated 设置|设置冲突|高版本只读" --workers=1 --retries=0
  ```

- [x] **步骤 3：实现 API 与 composable。** 保存携带服务端 Schema 和 revision；409 刷新服务端快照但保留 edits；成功后才清 dirty。

  ```ts
  await putExtensionSettings(extensionId, {
    schema_version: snapshot.value.schema_version,
    expected_revision: snapshot.value.revision,
    value: editableValue.value,
  });
  ```

- [x] **步骤 4：实现表单。** 映射 boolean/integer/number/string/enum，复用 `BooleanSwitch`；未知 object/array 控件显示不支持诊断，不提供 JSON 文本框。

- [x] **步骤 5：实现同模态子视图。** 配置按钮为 opener；进入聚焦标题/首字段，返回恢复同一卡片按钮；错误聚焦摘要；SettingsDialog 的 `hasUnsaved` 合并扩展 dirty。

- [x] **步骤 6：运行绿灯、i18n 和构建。**

  ```powershell
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e -- tests/e2e/extensions-settings.spec.ts tests/e2e/settings-dialog.spec.ts tests/e2e/settings-extensions-production-evidence.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 7：记录并提交。** commit message：`接入扩展 generated 设置与统一入口`。

### 任务 8：迁移图纸目录 custom 设置界面

**文件：**

- 新建：`web/src/composables/useSheetCatalogSettings.ts`
- 修改：`web/src/composables/useSheetCatalog.ts`
- 修改：`web/src/components/sheet-catalog/TemplateBar.vue`
- 修改：`web/src/components/sheet-catalog/ColumnEditor.vue`
- 修改：`web/src/components/sheet-catalog/CompatibilitySummary.vue`
- 修改：`web/src/components/sheet-catalog/catalogCompatibility.ts`
- 新建：`web/src/components/settings/SheetCatalogSettingsPanel.vue`
- 修改：`web/src/components/settings/ExtensionSettingsHost.vue`
- 修改：`web/src/i18n/locales/zh-CN/extensions.ts`
- 修改：`web/src/i18n/locales/en-US/extensions.ts`
- 修改：`web/tests/e2e/fixtures/sheetCatalog.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`web/tests/e2e/extensions-settings.spec.ts`
- 修改：`changelog.md`

**接口：** `useSheetCatalogSettings()` 管理同一扩展设置修订内的全局模板 CRUD、过滤文本、草稿、光标和修订冲突；`useSheetCatalog()` 组合该 controller 与工作区预览/导出，并从 API 映射 `filtered_rows -> filteredRows`；`CUSTOM_SETTINGS_PANELS` 固定映射 `sheet-catalog-settings` 到专属组件。

`SheetCatalogTemplateController` 只暴露 `loading/templates/selectedId/draft/dirty/canSaveInPlace/saving/saveError/conflict/caretRequest`，以及 `selectTemplate(id): Promise<void>`、`saveInPlace(): Promise<boolean>`、`saveAs(name): Promise<boolean>`、`retryAfterConflict(): Promise<boolean>`、`addColumn()`、`updateColumn(columnId, patch)`、`removeColumn(columnId)`、`moveColumn(columnId, direction)`、`trackCaret(columnId,start,end)`。`SheetCatalogSettingsController extends SheetCatalogTemplateController`，增加 `filterText/filterError/filterDirty`、`setFilterText(value)` 与 `saveFilter(): Promise<boolean>`；保存模板或过滤词都提交同一设置快照中的完整 `user_templates + excluded_title_keywords`，不得互相覆盖。另定义 `SheetCatalogValidationFeedback`，只含 `preview/previewStatus/previewError`。`TemplateBar` 只接收模板接口；`ColumnEditor` 接收模板接口和可选校验反馈；custom 设置面板接收完整设置接口。业务页传入设置接口与校验反馈并显示兼容性徽标/摘要；无工作区的设置面板不传校验反馈，隐藏兼容性徽标与摘要，不伪造 preview，也不把 `trackCaret` 降级为 no-op。

- [x] **步骤 1：写 custom 与过滤 E2E 红灯。** 无工作区新增模板/列、输入 `草图， TEMP,,作废,temp`、保存后规范化回显为 `草图, TEMP, 作废`、重开保留；打开工作区后同一模板可选，预览显示过滤后的行与“已过滤 N 张图纸”。覆盖过滤词 50/51 项、100/101 字符字段错误、全部过滤仍可导出、删除确认、冲突保留草稿、未知 route fail-closed 和无设置按钮。

- [x] **步骤 2：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/extensions-settings.spec.ts tests/e2e/sheet-catalog.spec.ts --grep "custom 设置|无工作区配置模板|输出图纸过滤|模板设置冲突" --workers=1 --retries=0
  ```

- [x] **步骤 3：抽取唯一扩展设置状态所有者。** 按本任务接口段拆出 `SheetCatalogTemplateController`、`SheetCatalogSettingsController` 与可选 `SheetCatalogValidationFeedback`；同步收窄 `catalogCompatibility`/`CompatibilitySummary`。保留 UUID、名称、光标和导航闸门语义。

- [x] **步骤 4：实现 custom 面板和编译期白名单。** 未加载工作区时不显示字段浏览器，允许编辑表达式文本；增加单行“输出图纸过滤”文本框、说明与示例占位，GET 数组以 `, ` 连接回显，PUT 提交原始文本交由 Provider 规范化，成功后以服务端数组重建文本。服务端最终校验语法、结构、关键词数量与长度。绝不按服务端 route 动态 import。

- [x] **步骤 5：验证业务页无回归与容量回落。** 两处共享 API/状态模型但不共享可变实例；并行编辑靠 revision 冲突，不采用最后写入覆盖。抽取后 `useSheetCatalog.ts` 必须回落到 500 行以内；目录生产证据测试保持通过，若出现预期视觉变化只新增经 G4/G8 裁决的证据，不覆盖既有历史截图。

- [x] **步骤 6：运行绿灯。**

  ```powershell
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e -- tests/e2e/extensions-settings.spec.ts tests/e2e/sheet-catalog.spec.ts tests/e2e/sheet-catalog-visual-evidence.spec.ts tests/e2e/extensions-navigation.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 7：记录并提交。** commit message：`迁移图纸目录 custom 全局设置界面`。

### 任务 9：文档、打包守护和全量验收

**文件：**

- 修改：`tests/unit/test_packaging_spec.py`
- 修改：`tests/unit/test_sheet_catalog_settings.py`（R26 可达性前提的行为化回归钉）
- 修改：`docs/dst-manager/guides/GUIDE-DM-005-builtin-extension-development.md`
- 修改：`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`
- 修改：`docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md`
- 修改：`docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md`（R19：设置 PUT 复用 `EXTENSION_SETTINGS_INVALID` + 409 的口径）
- 修改：`docs/dst-manager/README.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`
- 修改：`web/tests/e2e/settings-extensions-production-evidence.spec.ts`
- 修改：`web/tests/e2e/fixtures/extensions.ts`（M-9：`generatedSettingsItems()` 的 `order` 改为非单调 3/1/5/2/4，使字段顺序断言具备鉴别力）
- 新增：`.planning/todos/dst-manager/2026-09-13-settings-dialog-escape-gate.md`
- 新增：`.planning/todos/dst-manager/2026-09-13-extension-settings-capacity-debt.md`
- 清理失效引用：`.planning/memos/dst-manager/2026-09-10-plan-dm022-sdd-handoff.md`、`.planning/memos/dst-manager/2026-09-12-plan-dm025-review.md`、`.planning/plans/dst-manager/PLAN-DM-022-extension-card-baseline.md`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-06-config-entry-light.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-07-generated-light.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-08-custom-dark.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-09-custom-filter-edited-light.png`（控制者裁定追加，R27）
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-10-custom-filter-error-light.png`（控制者裁定追加，R27）
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-012/production/g8-filter-partial-light-1440x1000.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-012/production/g8-filter-all-dark-900x700.png`
- 修改：`.planning/plans/dst-manager/PLAN-DM-025-extension-global-settings.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`changelog.md`

**只运行、不修改：** `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`。两张目录过滤证据由它在 `DST_MANAGER_WRITE_G8_EVIDENCE=1` 下产出，用例本身在任务 8 之后已存在，本任务未改动该文件（修复轮也未改）。

- [x] **步骤 1：补打包守护。** 断言固定索引中的 Provider/custom route 有编译期引用、Manifest 无 module/class/url，现有 PyInstaller datas 继续包含清单资源。

- [x] **步骤 2：更新 GUIDE-DM-005。** 替换专用设置 `if` 说明，加入 Provider 模板、两类呈现选择表、迁移/高版本/快照测试和新增扩展 SOP；以“输出图纸过滤”记录会改变动作输出的设置如何进入 Provider 规范化、设置 digest、预览计数和执行门禁。

- [x] **步骤 3：运行后端完整门禁。**

  ```powershell
  $env:UV_LINK_MODE = "copy"
  rtk uv sync --dev
  rtk uv run ruff check .
  rtk uv run pytest -q
  rtk uv lock --check
  rtk uv run alembic upgrade head
  ```

- [x] **步骤 4：运行前端完整门禁。**

  ```powershell
  rtk npm --prefix web ci
  rtk npm --prefix web run check:api
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e
  ```

- [x] **步骤 5：执行 G8。** 对任务 5 的三张冻结图，在浅/深主题、1280×720、900×600、200% 缩放下生成 `g8-ext-06～08` 生产证据并逐张记录差异；custom 图必须覆盖“输出图纸过滤”默认、编辑和字段错误态。重跑既有设置扩展与图纸目录视觉证据用例，并新增 `g8-filter-partial-light-1440x1000.png` 和 `g8-filter-all-dark-900x700.png`，分别证明部分过滤汇总与全部过滤空表状态。既有 `g8-ext-01～05` 和图纸目录历史截图不得覆盖；新增目录图无冻结对照，只能算补充检查，目录页其余区域若无获批视觉变化则历史证据必须继续通过。

- [ ] **步骤 6：执行 G9。** 在 pywebview/WebView2 壳验证无工作区配置过滤词、键盘焦点、真实项目部分/全部过滤、全部过滤时只有表头的 XLSX、保存后新动作生效，以及预览后外部修改过滤设置触发 `EXTENSION_SETTINGS_CHANGED` 并重新预览。环境缺失时保持 `active` 并记录恢复条件，不代替用户填写通过。

- [x] **步骤 7：更新状态与索引。** 自动化、G8、G9 全部通过后才标记 `completed`；否则记录实际验证并保留 `active`。

- [x] **步骤 8：最终检查并提交。**

  ```powershell
  rtk git diff --check
  rtk git status --short
  ```

  commit message：`完成扩展全局设置框架验收`。

## MEMO-DM-033 审查处置

| 意见 | 处置 | 落点 |
| --- | --- | --- |
| B1 OpenAPI 命令不存在 | 采纳 | 任务 3、4 改用既有 `npm --prefix web run generate:api` |
| B2 偏好绑定与架构冲突 | 采纳并收窄规则 | ARCH-DM-006 §11/§12；任务 4 只绑定影响输出且未进入动作请求的偏好 |
| M1 generated 无运行载体 | 采纳 | 任务 3 使用测试内 Manifest/Provider/index 注入，不增加生产扩展 |
| M2 SettingsDialog 超限待办 | 采纳并独立成任务 | 任务 6；原 Todo 已被正式计划吸收并移除 |
| M3 既有 E2E 与生产证据 | 采纳 | 任务 5、7～9 的 SC-16、设置扩展证据和目录证据回归 |
| M4 ColumnEditor 边界含糊 | 采纳 | 任务 8 固定模板 controller 与可选 validation feedback 的字段/方法 |
| 高版本错误码含糊 | 采纳 | ARCH-DM-006 §8/§12；任务 3 使用 `EXTENSION_SETTINGS_SCHEMA_NEWER` |
| `useSheetCatalog.ts` 超限 | 采纳 | 任务 8 设置 500 行以内门禁 |
| 可能存在“完整模板集”存量 | 经代码核实不成立，不设计迁移 | 当前 `save_templates()` 只写 `user_templates`；任务 2 增加真实存量形状兼容测试 |

## 风险与回退

- preview 后设置改变是最高一致性风险；修订检查必须在候选目录和授权消费之前，并由无 Artifact/授权未消费测试锁定。
- 未知高 Schema 不能当空配置保存；GET 返回原 JSON 只读视图，PUT fail-closed。
- 不得让 SettingsDialog 继续膨胀或叠加第二个设置模态；子视图状态下沉到 Host/composable。
- 业务页和设置页不能各持一套模板/过滤语义；先抽取 `useSheetCatalogSettings`，同一实例内保存完整设置，并行实例靠 revision 冲突。
- generated 遇到嵌套 object/array 时显示不支持诊断，复杂结构使用 custom。
- 过滤必须先于表达式求值且 Preview/Execute 复用同一纯函数；否则被排除图纸仍会产生缺值警告，或出现预览与 XLSX 行数漂移。
- 若需要新数据库表、动态模块加载、凭据存储或后台任务，立即停止并回到 ARCH-DM-006 评审。

## 完成标准

- 第二个 Builtin 扩展只登记 Provider 和 Manifest 呈现元数据，无需修改 Runtime 专用 `if` 即获得设置 CRUD、校验、迁移和并发保护。
- 图纸目录设置由 Provider 强制校验；既有 API 数据、UUID、模板上限和高版本保护不回退。
- “输出图纸过滤”按两种逗号拆分、trim、Unicode 大小写不敏感去重与 OR 子串匹配；预览返回过滤后的 `total_rows` 和 `filtered_rows`，全部过滤仍导出只有表头的 XLSX。
- generated 与 custom 都从“设置 → 扩展 → 配置”进入，无工作区可用；卡片本体保持不可点击。
- 保存只影响后续调用；活动调用使用冻结快照；preview 后设置变化返回 `EXTENSION_SETTINGS_CHANGED`/409，不消费授权、不创建 Artifact。
- Provider、扩展和前端不能取得 Store、数据库会话、任意模块路径或完整应用设置；凭据不进入普通设置。
- Ruff、全量 pytest、UV lock、Alembic、OpenAPI、i18n、生产构建和全量 Playwright 全部通过。
- SPEC-DM-011 新入口的 G4/G8 有可核验证据；真实桌面 G9 由用户或具备环境的执行者明确记录。

## 实际验证（2026-09-13）

实施与自动化验收已全部完成；**G9 真实验收待用户执行，本计划因此保持 `active`，不标记 `completed`。**

- **提交链**：任务 1～9 共 28 个实施/收口提交，另有 2 个评审修复轮提交（`c3c5b6d` 与第二轮修复提交），分支合计 **30** 个提交（基 `main` 79c61a3，功能分支 `feature/plan-dm-025-extension-global-settings`；含 G4 用户确认记录与最终验收提交），逐任务实施、逐任务独立评审并对评审意见做定向复审；每个任务至少一次修复轮，修复均有可失败性证据（变异 → 失败断言 `文件:行` → 按字节还原）。
- **评审与修复轮**：任务 1～9 的逐任务独立评审与定向复审均已闭环；任务 9 评审（1 项 Important + 10 项 Minor）由控制器直接修复并提交 `c3c5b6d`；随后两条只读通道对全分支 `79c61a3..c3c5b6d` 做最终复核（通道 A「门禁复算」Approved、通道 B「修复闭环复核」Needs fixes），**以验证为准**合并判为 Needs fixes 后按第二轮修复收口（计划清单回归、打包守护传递链、用例覆盖退化、口径与数字）。已知残留缺口不施加修，登记为待办 `.planning/todos/dst-manager/2026-09-13-extension-packaging-guard-gaps.md`。
- **后端**：`uv sync --dev` 通过；`uv run ruff check .` All checks passed；`uv run pytest -q` **1327 passed / 72 skipped / 0 failed**（86s；两轮评审修复各补 1 例，分支 HEAD 复测 **1329 passed / 72 skipped / 0 failed**，77.45s；PLAN-DM-026 收口时为 1182 passed / 72 skipped，本计划新增 147 例）；`uv lock --check` 无漂移；`uv run alembic upgrade head` 迁移链到 `0006_dm020_extension_platform` 正常。
- **前端**：`npm ci` 通过；`check:api` 无漂移（未手改 `openapi.json`/`schema.d.ts`）；`check:i18n` **938 键 / 9 域**且无未登记硬编码中文；`build` exit 0（`vue-tsc -b` + `vite build ✓ built in 1.51s`）；`test:e2e` 全量首测 **486 passed / 0 failed / 2 flaky**（`g8-ext-07` 与「50 列极限」在 4 worker 并行下首跑 30s 超时、重跑通过；与 PLAN-DM-026 收口时记录的同类抖动一致）。**flaky 成员每次运行随机漂移，不得当作已收敛的名单**：独立复核复跑一次为 **484 passed / 0 failed / 4 flaky**（`extensions-settings.spec.ts:443`、`main.spec.ts:216`、`main.spec.ts:644`、`properties-csv.spec.ts:258`），用例总数 488 一致；门禁判据是 **exit 0 + 0 failed**，超时项重跑通过即可。
- **容量**：`SettingsDialog.vue` 535 → **469** 行（软上限内）；`useSheetCatalog.ts` 701 → **409**；`useSheetCatalogSettings.ts` **496**（接近上限，已立待办）；`extensions-settings.spec.ts` **1148** 行、`sheet-catalog.spec.ts` **1233** 行（均超上限，已立待办）。以上为收口提交 `04f303f` 的实测值；修复轮已更正早前误抄的 494/1109（见 changelog 2026-09-13 修复轮）。其余新增/改动文件均在 500 行以内。
- **G4**：2026-09-12 经用户确认通过（MEMO-DM-034），确认时显式告知的 4 项保留条件已在任务 9 收口（第 ④ 项关闭，①②③ 由 `g8-ext-06～g8-ext-10` 部分补足并写明像素级复核归 G9）。
- **G8**：2026-09-11 用户确认结论不变；2026-09-13 由 `settings-extensions-production-evidence.spec.ts`（10 例）补 5 张扩展设置证据与 2 张输出过滤证据（后者由 `sheet-catalog-visual-evidence.spec.ts` 产出）。既有冻结件 `g4-01～g4-15`、`g8-ext-01～05`、`g8-catalog-*`、`g8-format-menu-*` **未重取、未覆盖**。
- **PLAN-DM-026 回归再验证**：全量后端与全量 E2E 均在 PLAN-DM-026 的改动之上重跑通过（数字见上），未发现 PLAN-DM-026 引入的行为回退；`catalogCompatibility.ts`、数字格式码入口与其证据链未被本计划改动。
- **未由实施代理完成的事**：G9 真实验收（pywebview/WebView2 + Excel）与其像素级差异裁决；两处容量债拆分（待办已立）；枚举选项文案键的契约扩展（需要时另立计划）。
