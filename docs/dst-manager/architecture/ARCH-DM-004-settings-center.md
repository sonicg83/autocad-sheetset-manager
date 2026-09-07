---
id: ARCH-DM-004
title: 设置中心（应用内配置 + 关于页）
status: draft
owners:
  - dst-manager
created: 2026-09-07
updated: 2026-09-08
related:
  - PRD-DM-001
  - ARCH-DM-001
  - ARCH-DM-002
  - ARCH-DM-003
document_kind: architecture
---

# 设置中心（应用内配置 + 关于页）

> 状态：草稿（2026-09-08 按[设计审查备忘](../../../.planning/memos/dst-manager/2026-09-07-settings-center-design-review.md)完成修订：补跨进程配置传播、显式覆盖存储、保存事务与恢复语义；复审通过后转 `accepted`）
> 定位：DST Manager 桌面软件形态下的应用内配置中心权威设计——以界面配置取代"编辑 .env"的用户路径，并提供关于/版本/开源协议页；同时为 [PRD-DM-001](../product/prds/PRD-DM-001-extensible-capability-platform.md) 扩展平台的设置分区预留接入结构。
> 原则：Pydantic `Settings` 为配置语义唯一权威、用户配置文件只存显式覆盖值且原子写入、全部界面配置即时生效（含跨进程边界）、不堵死扩展平台接入。

## 1. 目标与边界

### 1.1 背景

打包为 exe 后（ARCH-DM-002 绿色分发包），通过编辑 `.env` 修改配置不符合桌面软件习惯：`.env` 不随包分发给最终用户、编辑需要理解环境变量命名、且程序目录可能无写权限。需要应用内配置界面，同时保持开发态 `.env`/环境变量工作流不变。

### 1.2 目标

- 未加载 DST 工作区时即可查看和修改全部应用配置（顶部齿轮入口 + 模态对话框）。
- 配置保存后即时生效，无需重启应用；API 进程与 CAD Worker 子进程对运行期配置的可见性边界有明确定义（§2.4）。
- 提供关于页：应用名称与版本号、MIT 开源协议、项目主页/反馈入口。
- 新增配置项时前后端表单零改动（注册表 + 动态渲染），并为扩展平台贡献的设置分区预留统一挂载点。

### 1.3 范围外（YAGNI）

- **扩展设置本体**：按 `extension_id` 隔离的扩展设置存储、启停与校验属 PRD-DM-001 后续立项，本期只预留结构（见 §6），不实现。
- **`data_dir`/`draft_dir` 界面化**：两者属启动期配置（建目录、派生数据库 URL），改动的收益不抵重启与数据迁移风险；不进注册表、不进界面。开发态仍可用环境变量覆盖。
- **模板目录（`template_dir`）**：作为配置中心扩展能力的后续需求，本期不实现（用户已确认）。
- **第三方组件声明页**：维护成本高，后续再补。
- **凭据类配置**：按 PRD-DM-001 SEC-003，凭据永远不进普通设置。
- 配置导入导出、远程配置、多配置方案切换。

## 2. 配置模型与存储

### 2.1 权威来源与注册表

- **Pydantic `Settings`（`src/dst_manager/config.py`）保持唯一权威**：字段、默认值、类型约束、validator 语义（含 `EnableAddNumberSuffix`/`NumberSuffixType` 字符串容错与 CAD 路径规范化）全部不变；`data_dir`/`draft_dir` 相关校验留在原处。
- **注册表**（`src/dst_manager/settings/registry.py`）只保存**展示元数据**，不重复语义定义：

| 字段 | 说明 |
| --- | --- |
| `key` | 与 `Settings` 字段同名 |
| `label` | 中文显示名 |
| `category` | 分组（"AutoCAD 2016"、"AutoCAD 2020"、"任务执行"、"编号规则"） |
| `control` | 控件类型：`path` / `bool` / `int` / `enum` |
| `nullable` | 仅 `path` 有：是否允许"未配置"（四个 CAD 路径字段均为 `true`） |
| `file_filter` | 仅 `path` 有：`exe`（Core Console）/ `dll`（Worker 插件），按字段分别声明 |
| 帮助文案 | 说明文字 |

- 默认值、int 的 min/max、enum 选项**从 Settings Schema 派生**（如 `cad_max_parallel` 的 1–10 来自 `Field(ge=1, le=10)`），注册表不存第二份。
- **依赖方向单向**：`registry.py` → `config.py`；`config.py` 不得反向导入注册表（避免循环依赖）。完整性测试保证：`Settings` 每个 UI 字段都有注册项、派生的默认值/约束与 Schema 一致。
- **可空路径契约**：`null` 表示"未配置"；空字符串/纯空白在进入 Settings 之前统一按 `null` 处理（pydantic 会把 `Path("")` 解析为当前工作目录，绝不允许该值落盘或生效）。路径控件提供"清除"动作。

现有 9 个界面配置项全部登记：`autocad_2016_console`、`autocad_2016_plugin`、`autocad_2020_console`、`autocad_2020_plugin`、`cad_timeout_seconds`、`cad_max_parallel`、`worker_lease_seconds`、`enable_add_number_suffix`、`number_suffix_type`。

### 2.2 用户配置文件：只存显式覆盖值

- 路径：`%LOCALAPPDATA%\dst-manager\settings.json`（`LOCALAPPDATA` 缺失时回退 `~/AppData/Local`，与现有 `_default_data_dir` 同规则）。
- 新增 `src/dst_manager/settings/store.py`（infrastructure）：**原子写入**（同目录临时文件 + `os.replace`）。

```json
{
  "schema_version": 1,
  "config_revision": 7,
  "values": { "cad_timeout_seconds": 900 }
}
```

- **`values` 语义：用户显式覆盖值集合，不是有效配置快照。** 未出现的字段按 环境 → 默认 继承。前端保存绝不把 env/default 值固化进文件——否则修改 `.env` 不再生效、升级后的新默认值被旧文件遮蔽、frozen 态插件默认路径（exe 同级）会把某次安装位置固化，移动绿色包后继续引用旧路径。
- `config_revision`：单调递增，保存成功时 +1；供 Worker 变更检测（§2.4）与 API 冲突判断（§3）。
- 诊断码四类：`SETTINGS_FILE_MISSING`（无文件，正常首启）、`SETTINGS_FILE_CORRUPT`（非法 JSON/非法 UTF-8/类型损坏）、`SETTINGS_SCHEMA_OLDER`（版本过旧，可迁移）、`SETTINGS_SCHEMA_NEWER`（版本过新）。处理规则见 §5。

### 2.3 解析与快照

- `SettingsResolver` 分别读取代码默认值、环境变量/`.env`、`settings.json` 显式覆盖值，产出**不可变 `SettingsSnapshot`**：有效 `Settings`、逐字段 `source`（`default` / `env` / `file`，在合并时记录，不从最终值反推——相同数值可能来自不同层级）、文件覆盖集合、诊断码、`config_revision`。
- **保存事务**：进程内锁覆盖"读取基准快照 → 全量校验 → 同目录临时文件写入 → `os.replace` → 替换进程内快照"全过程；保存响应必须来自锁内已提交的同一快照，不得锁外重新拼装。临时文件、备份、锁均只落用户配置目录，不写程序目录或项目目录。
- 启动期字段（`data_dir`/`draft_dir`，未界面化）只在进程启动时消费；运行期字段的生效边界见 §2.4。

### 2.4 跨进程传播：API 进程与 CAD Worker

桌面壳 = API 进程 + 独立 `worker` 子进程（`shell.py` `_spawn_worker`）；Worker 由 `cli worker` 启动时构造一次 `DstManagerService` 后永久循环认领任务。**进程内快照替换不跨进程**，因此：

1. **Worker 每次认领新任务前**检查 `settings.json` 的 `config_revision`（文件 stat/内容），发现变化即重新解析并替换自身快照——新任务用新配置。
2. **认领任务时冻结本任务的配置快照**，任务运行期间不再变化；快照的 `config_revision` 记入任务记录/日志，可追溯任务实际使用的配置。
3. 已运行任务继续用旧快照，不做中断。
4. **租约安全规则**：任务认领时把该任务使用的 `worker_lease_seconds` 随快照写入任务记录；API 过期恢复（`recover_stale_jobs`）按各任务记录的 lease 快照判断，不统一用 API 当前值——新旧 lease 并存的过渡期不会误回收仍在执行的任务。
5. 不采用"保存后受控重启 Worker"方案：生命周期干扰大，且与本节"新任务新配置、旧任务旧快照"的语义不匹配。

## 3. API 契约（版本化）

随现有 `interfaces/api` 单应用扁平路由新增 3 个端点；`/api/settings` 的请求/响应结构标注为版本化契约（`schema_version` 演进），使用显式 Pydantic 请求/响应模型并纳入 OpenAPI 契约测试（含字段稳定排序）：

- `GET /api/settings` → `{ schema_version, config_revision, items: [{ key, label, category, control, value, default, source, has_file_override, nullable?, file_filter?, min?, max?, options? }], diagnostics? }`。`value` 为当前有效值；`items` 为注册表序列化；前端**只认描述、不认具体配置项**。`source` 与 `has_file_override` 区分"当前生效值"与"是否存在用户覆盖"。
- `PUT /api/settings`：PATCH 风格**部分更新覆盖集合**。body `{ expected_revision, set: { key: value }, unset: [key] }`：
  - `set` 只写入显式覆盖；未提及字段不受影响（§2.2 的固化禁令）；
  - `unset` 逐字段删除覆盖，恢复 环境 → 默认 继承；
  - 未知 key → 422 逐字段错误（除非 Schema 迁移策略明确要求保留）；
  - 后端全量权威校验（Settings 语义为唯一权威），**要么全部生效要么全部拒绝**，失败返回 422 `{ errors: { key: message } }`；
  - `expected_revision` 与当前 `config_revision` 不符 → 409，不修改任何状态；
  - 通过后锁内原子落盘 + 热替换进程内快照，返回与 GET 同构的已提交快照。幂等。
  - （修订说明：`expected_revision/409` 本对单窗口桌面应用属过度设计，但 `config_revision` 是 §2.4 Worker 同步的必需品，API 侧搭车使用边际成本可忽略，故纳入契约。）
- `GET /api/about` → `{ app_name, version, license: { spdx, text }, homepage, feedback_url }`。版本号运行时读取 `importlib.metadata.version("dst-manager")`（唯一权威仍是 `pyproject.toml`，ARCH-DM-003 §2）；开发态包元数据不可用时回退读 `pyproject.toml`。MIT 全文来自仓库根 `LICENSE` 文件：开发态直接读取；frozen 态由 `packaging/dst-manager.spec` 将 `LICENSE` 加入 onedir 数据文件、经 `runtime.resource_dir()`（`sys._MEIPASS`/`_internal`）读取——不内嵌第二份协议文本，不另写 exe 目录定位规则，保持单一来源。

三端点均**不依赖已打开的工作区**，未加载 DST 时可用。服务继续只监听 `127.0.0.1`；`GET /api/settings` 会返回本机绝对路径，日志与诊断不得无差别复制完整路径。

## 4. UI：顶部齿轮入口 + 模态对话框

### 4.1 入口与形态

- 顶部栏右侧"小齿轮"图标按钮，**始终可见**（不依赖 DST 加载状态）。
- 点开为独立模态对话框 `web/src/components/settings/SettingsDialog.vue`；工作区标签栏保持纯业务视图，不增加"设置"标签。

### 4.2 对话框内部结构

- 左右布局：左侧窄条分区列表（本期"常规配置"/"关于"；未来"扩展中心"与扩展贡献分区在此追加，见 §6），右侧内容面板；内容超高在面板内滚动，不撑破对话框。
- **常规配置**：按注册表 `category` 分组动态渲染。控件映射：`path` → 文本框 + "浏览…"按钮 +（`nullable` 时）"清除"动作，文件过滤器按 `file_filter`；`bool` → 开关；`int` → 数字输入（min/max 来自派生约束）；`enum` → 单选。
- **关于**：应用名 + 版本号、MIT 协议全文（面板内滚动）、项目主页/反馈链接。
- **外链行为**：主页/反馈链接经系统默认浏览器打开，不经 WebView 导航离开应用；仅允许打开后端返回或代码登记的 `https` URL，不接受任意前端字符串。

### 4.3 原生路径选择器

`ShellBridge` 新增 `select_folder` 与 `select_file`（按注册表 `file_filter` 传 EXE/DLL 过滤器），基于 pywebview `create_file_dialog`，返回沿用桥的既有 `{ok, value} / {ok:false, code, message}` 模式。浏览器开发态（非桌面壳）"浏览…"按钮禁用、保留手输。

### 4.4 状态机与键盘（对齐 PRD-DM-001 UI-004/UI-005，为未来扩展对话框立标杆）

- 状态：未修改 / 编辑中 / 校验失败（逐字段行内错误）/ 保存中 / 已保存（短暂提示）。
- 未保存修改时关闭（Esc、✕、遮罩）先确认，不静默丢弃输入。
- Esc 关闭、焦点圈闭、关闭后焦点归还齿轮按钮、校验失败时焦点落到第一个错误字段。
- 实现约束：现有全局拖拽桥监听在 document 上，对话框遮罩与焦点管理须与其兼容——对话框打开时拖放事件不得穿透遮罩产生误操作。
- **配置变化 × 旧预览**：`enable_add_number_suffix`、`number_suffix_type`、`cad_max_parallel` 影响命名规划与执行估算；保存后相关旧预览按既有 preview digest 机制失效重算，并在界面明确提示，不以旧预览冒充新配置的结果。

## 5. 校验与错误处理

| 场景 | 行为 |
| --- | --- |
| 前端即时校验 | 类型、数字范围输入时反馈；不落盘 |
| 后端权威校验 | Settings/Pydantic 语义为唯一权威（注册表只派生展示元数据）；PUT 全量重验 |
| 路径输入为相对路径 | **保持现有兼容行为**：允许输入，进入有效配置与用户文件前统一规范化为绝对路径（沿用 `validate_cad_paths` 与 `test_cad_paths_resolve_relative_to_absolute` 守护的行为）；`.env` 行为不变 |
| 路径为空字符串/纯空白 | 统一按"未配置"（`null`）处理，绝不解析为当前工作目录 |
| 路径不存在 | **允许保存 + 黄色警告**（AutoCAD 可能装在网络盘/后接机器）；执行失败走现有任务错误链路 |
| settings.json 损坏（非法 JSON/非法 UTF-8/类型损坏，`SETTINGS_FILE_CORRUPT`） | 原样重命名为带时间戳的备份，回退默认值；由用户明确确认后重建；GET 附带诊断，对话框顶部提示"配置文件无法读取，已恢复默认" |
| `schema_version` 过新（`SETTINGS_SCHEMA_NEWER`） | **原文件保持不变**；设置页进入只读诊断状态，禁止普通 PUT——防止旧程序用旧 Schema 覆盖新版本配置、丢弃未知字段 |
| `schema_version` 过旧（`SETTINGS_SCHEMA_OLDER`） | 有明确迁移器则迁移（迁移前保留备份）；无迁移器按损坏类处理并提示 |
| 写入失败（磁盘/权限） | 保存报错；**进程内快照不替换**——文件是权威，避免界面值与重启后实际值错位 |
| 并发保存 | 进程内锁串行化"读基准→校验→落盘→换快照"全流程（§2.3）；`expected_revision` 过期返回 409 且无任何副作用（§3） |
| 配置变化 × 旧预览 | 见 §4.4 末条 |
| 并发写（跨进程） | 已有单实例守卫（PLAN-DM-018）保证桌面壳唯一；本期无第二写入进程 |

## 6. 与扩展平台（PRD-DM-001）的关系

本期**只留口、不实现**，三条预留：

1. **UI 分区式结构**：设置页 = 分区列表驱动。PRD-DM-001 UI-001 的"扩展中心"位于配置页、UI-002 把"设置分区"列为受控贡献点——未来作为新分区加入本对话框，导航模型天然支持，入口仍由宿主统一生成。
2. **存储隔离**：扩展设置将来使用独立命名空间（如 `extensions/<extension_id>.json`），满足 EXT-013 按 `extension_id` 隔离、带版本和校验规则的要求，**不复用**本文件 `values` 扁平映射；本期 store 的原子写、`schema_version`/`config_revision`、损坏回退写成可复用函数。
3. **契约版本化**：`GET /api/settings` 的"描述 + 值 + 修订"结构即 PRD 扩展贡献设置分区将来可复用的渲染契约（含 `nullable`/约束/来源标记语义）；扩展设置走各自端点，不混入本契约。

渲染层（描述 → 表单）与存储层（原子 JSON + 版本 + 修订）两个可复用件，正是扩展平台设置能力的对接点。

## 7. 测试策略

- **pytest 单元**：
  - 注册表完整性（P2-04）：`Settings` 每个 UI 字段有注册项；派生的默认值/min/max/枚举与 Schema 一致；依赖方向无反向导入。
  - 路径契约（P2-01）：`null` 往返保持 `None`；空字符串/空白绝不解析为当前工作目录；相对路径仍规范化为绝对路径（兼容现状）。
  - 层级与清除（P1-02）：默认/env/file 三层逐项 `source` 判定；文件覆盖值与 env 值相同时 `source` 仍为 `file`；`unset` 恢复 env 再恢复 default 的继承链；`set` 单字段不固化其他 env/default 有效值；未知 key、缺失 key、`null`、空字符串、类型错误行为明确。
  - 并发与一致性（P1-03）：两个并发 PUT 后内存与磁盘最终快照一致；过期 `expected_revision` 返回 409 且不修改任何状态；文件写入成功但内存提交前异常时，重启按文件权威恢复。
  - Worker 热更新（P1-01）：Worker 启动后修改 CAD 路径，下一任务用新路径；新任务新值、已认领任务保持旧值；租约过渡期 API 恢复判断与 Worker 心跳不产生误回收；任务日志可追溯实际使用的 `config_revision`。
  - Schema 与故障恢复（P2-02）：JSON 截断、非法 UTF-8、字段类型损坏分别产生稳定诊断；过新高版本 Schema 不被 GET 或失败 PUT 改写（字节不变）；用户明确重置前保留原文件、重置后保留可恢复备份。
- **API 集成测试**：GET 契约快照（OpenAPI 模型 + 稳定排序）；PUT 逐字段 422、全有或全无、409；落盘文件只含显式覆盖；`GET /api/about` 版本与 LICENSE 读取。
- **Playwright e2e**：未加载工作区时齿轮可见可开；修改 → 保存 → 重开对话框值保留；校验失败行内错误与焦点；未保存关闭确认；`npm run build` 生产构建。
- **手工验收**（e2e 无法覆盖，列入 rc 验证清单）：打包后桌面壳内路径选择器真实弹窗（EXE/DLL 过滤器各一）；保存后配置对真实 CAD 任务生效；移动绿色包后未覆盖的插件默认路径跟随新 exe 目录；frozen 包内版本元数据与 `LICENSE` 可从 `runtime.resource_dir()` 读取。
- 回归安全网：`config.py` 保持权威、validator 语义不变，既有测试（当前 642 passed 基线）必须保持通过。

## 8. 风险与实现注意点

- **frozen 态包元数据**：`importlib.metadata` 需要 PyInstaller 收集 `dst-manager-*.dist-info`；若默认未收集，在 `packaging/dst-manager.spec` 补 hook。连同 §3 的 `LICENSE` 数据文件，spec 共两处新增——这是本设计仅有的打包配置触点；两者统一经 `runtime.resource_dir()` 定位。
- **一致性核查项**：修订实施前核查 ARCH-DM-002、根 README、`setup.bat` 中 `.env` 用户路径的描述与新优先级（默认 < env < 用户覆盖）及恢复继承语义一致；不一致处以本文档为准并同步修订。
- **文档索引**：本文接受后同步维护 `docs/dst-manager/README.md` 索引与根 `changelog.md`。
