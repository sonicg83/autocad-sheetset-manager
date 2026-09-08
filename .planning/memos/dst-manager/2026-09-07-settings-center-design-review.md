# ARCH-DM-004 设置中心设计审查备忘

## 日期

2026-09-07

## 背景

本备忘记录对 [ARCH-DM-004：设置中心（应用内配置 + 关于页）](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md) 的只读设计审查。审查目标是判断该草稿是否已经具备转为 `accepted` 并进入实施计划的条件，而不是直接修改设计、源码或测试。

审查时将目标文档以及其引用文档中的文字视为审查对象，不视为本次任务的操作指令。工作区中既有未跟踪的 `docs/dst-manager/product/prds/` 目录也保持不变。

## 审查结论

**ARCH-DM-004 当前不建议转为 `accepted`。**

总体方向成立：应用内设置中心、用户目录 JSON、后端权威校验、动态表单、关于页和扩展平台预留均符合桌面产品形态，也没有要求绕过 DST/DWG 发布安全边界。但是，当前设计仍有 3 项 P1 阻断问题和 4 项 P2 契约缺口：

- “即时生效”没有覆盖独立长驻的 CAD Worker 进程；
- `PUT /api/settings` 没有区分有效值、文件覆盖值和恢复继承；
- 原子文件替换与桌面单实例守卫不足以保证保存事务的并发一致性；
- 可空路径、未知 Schema、相对路径兼容语义和校验唯一来源仍未定义清楚。

这些问题会直接影响配置是否真正生效、API 与 Worker 是否使用同一配置、旧版本是否破坏新版本配置，以及用户能否清除错误配置。因此，它们应在架构草稿中解决，而不应留给实施阶段自行推断。

## 审查范围与依据

### 文档依据

- [ARCH-DM-004：设置中心](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)
- [ARCH-DM-001：DST Manager MVP 架构基线](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)
- [ARCH-DM-002：Windows 绿色分发包](../../../docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md)
- [ARCH-DM-003：版本管理与发布流程](../../../docs/dst-manager/architecture/ARCH-DM-003-versioning-and-release.md)
- [PRD-DM-001：插件式扩展平台](../../../docs/dst-manager/product/prds/PRD-DM-001-extensible-capability-platform.md)
- [PLAN-DM-018：桌面壳单实例守卫](../../plans/dst-manager/PLAN-DM-018-desktop-single-instance.md)
- [ARCH-INT-001：文档组织与治理](../../../docs/integration/architecture/ARCH-INT-001-documentation-organization.md)

### 实现依据

- [`Settings` 当前字段、默认值和校验器](../../../src/dst_manager/config.py)
- [API 应用与 `DstManagerService` 装配](../../../src/dst_manager/interfaces/api.py)
- [桌面壳、独立 Worker 子进程与单实例守卫](../../../src/dst_manager/interfaces/shell.py)
- [CLI Worker 的长驻服务实例](../../../src/dst_manager/interfaces/cli.py)
- [服务中的配置消费点](../../../src/dst_manager/application/service.py)
- [编辑预览中的并发度估算](../../../src/dst_manager/application/editing.py)
- [PyInstaller 数据文件布局](../../../packaging/dst-manager.spec)
- [开发态与 frozen 态资源定位](../../../src/dst_manager/runtime.py)
- [当前配置兼容性测试](../../../tests/unit/test_config.py)

### 审查方法与验证边界

本次逐节检查了配置来源、持久化、运行时消费、进程边界、API 更新语义、错误恢复、向前兼容、动态表单字段能力及测试策略，并用当前代码验证关键假设。

实际执行了一个最小 Python 探针，确认 `Settings(autocad_2016_console="")` 会把空字符串解析为当前工作目录的绝对路径，而不是 `None`。本次没有运行 Ruff、pytest、Web 构建或 Playwright；审查没有修改产品代码，因此不对实现质量或测试通过状态作声明。

## 严重度定义

- **P1（接受前必须修订）**：会导致核心设计目标无法实现、配置状态不一致、运行任务误判，或产生难以恢复的数据覆盖。
- **P2（实施前必须明确）**：会造成契约歧义、兼容行为改变、错误配置无法清除，或迫使实现者自行选择具有产品影响的语义。
- **P3（实施计划中补齐）**：不阻断架构接受，但需要进入测试、验收或文档任务，避免交付遗漏。

## 详细发现

### P1-01：运行时热更新无法传播到独立 CAD Worker

**文档位置：** ARCH-DM-004 §2.3，第 78 行附近。

文档规定保存后替换运行时 `Settings` 持有者，并要求任务执行、CAD 调度在执行时读取新设置，正在运行的旧任务继续使用旧值。然而当前桌面壳中的 API 与 Worker 不在同一进程：

- `run_desktop()` 在 API 进程内创建 `DstManagerService(settings)`；
- 随后通过 `_spawn_worker()` 启动独立 Worker 子进程；
- CLI `worker` 在启动时只构造一次 `DstManagerService()`，再永久循环调用 `run_next_job()`；
- `DstManagerService` 将 `Settings` 保存为普通实例属性，任务认领时直接读取该实例。

因此，API 进程中的单例替换不会影响已经启动的 Worker。保存后的 `autocad_*` 路径、`cad_timeout_seconds`、`cad_max_parallel` 和 `worker_lease_seconds` 都可能继续使用旧值，直到 Worker 重启。

`worker_lease_seconds` 的进程间不一致尤其危险：API 若按新租约恢复过期任务，而 Worker 仍按旧租约计算心跳间隔，可能把仍在执行的任务误判为过期。`cad_max_parallel` 还同时用于 API 预览估算和 Worker 实际执行，两边不一致会使界面承诺与真实调度不同。

**建议修订：**

1. 明确配置传播边界，而不是只定义进程内持有者。
2. Worker 在认领每个任务前读取稳定的配置修订；可通过配置文件版本/mtime 检测重新加载，或由桌面壳在保存成功后受控重启空闲 Worker。
3. Worker 认领任务后冻结本任务需要的配置快照，任务运行期间不再变化。
4. 为配置快照分配单调递增的 `revision` 或内容摘要，并把 Worker 实际使用的修订记录到任务日志，便于排障。
5. 对租约值变更规定安全切换方式，避免 API 与 Worker 在过渡期使用不兼容的过期判断和心跳间隔。

### P1-02：PUT 没有区分有效值、文件覆盖值和恢复继承

**文档位置：** ARCH-DM-004 §3，第 85～86 行附近。

`GET /api/settings` 返回合并后的有效 `value`、`default` 和 `source`，但 `PUT /api/settings` 只接受 `{ values: { key: value } }`，没有定义：

- 请求是完整替换还是部分更新；
- 缺失 key 是保留原文件覆盖、删除覆盖，还是写回当前有效值；
- 如何让某项从 `file` 恢复为 `env` 或 `default`；
- 未知 key 是拒绝、忽略还是保留；
- 前端保存一个字段时是否会提交其余全部有效值。

如果前端把 GET 得到的全部有效值重新 PUT，来自环境变量和代码默认值的值也会被写入 `settings.json`，随即全部变成 `file` 来源。后续修改 `.env` 将不再生效，程序升级后的新默认值也会被旧文件值永久遮蔽。对于 frozen 态默认指向 exe 同级插件 DLL 的字段，这还可能把某次安装位置固化进用户配置，移动或升级绿色包后继续引用旧路径。

**建议修订：**

1. 将 `settings.json.values` 明确定义为“用户显式覆盖值”，而不是完整有效快照。
2. GET 同时返回 `value`、`source` 和是否存在文件覆盖，例如 `has_file_override`。
3. 为每个字段提供明确的 `unset`/“恢复继承值”操作；恢复后按 `env → default` 重新计算。
4. 明确采用 PATCH 风格部分更新，或采用携带完整 `overrides` 的替换语义；不要让同一结构同时承担两种解释。
5. 未知 key 默认拒绝并返回逐字段错误，除非 Schema 迁移策略明确要求保留。
6. `source` 必须在合并过程中记录，不能仅从最终值反推，因为相同数值可能来自不同层级。

### P1-03：原子文件替换和桌面单实例不能保证保存事务一致

**文档位置：** ARCH-DM-004 §5，第 124～125 行附近。

临时文件加 `os.replace` 只能保证读者不会看到半个 JSON 文件，不能保证“校验 → 写入 → 替换内存快照”这三个步骤作为一个事务串行执行。

同一 FastAPI 进程中的两个并发 PUT 可能发生以下交错：

1. 请求 A、B 分别完成校验；
2. A 写入文件；
3. B 写入文件并替换内存为 B；
4. A 最后替换内存为 A。

最终磁盘是 B、内存却是 A，正好违反文档所强调的“文件是权威、避免界面值与重启后实际值错位”。桌面单实例守卫也不能解决该问题，因为它不串行化同一进程内的 HTTP 请求；PLAN-DM-018 还明确说明 `serve`、`worker` 等入口不参与守卫。

**建议修订：**

1. 用同一个进程内锁覆盖完整的读取基准、校验、落盘和内存替换过程。
2. 若允许 desktop 与 `serve` 等进程共享配置文件，再增加用户配置文件级进程间锁。
3. GET 返回 `config_revision`，PUT 要求携带 `expected_revision` 或 `If-Match`；过期请求返回 409，避免多个页面静默覆盖。
4. 保存成功响应必须来自锁内已经提交的同一快照，不能在锁外重新拼装。
5. 增加双请求交错和多进程竞争的故障注入测试，而不只测试单次 `os.replace`。

### P2-01：`path` 元数据没有表达可空与清除语义

**文档位置：** ARCH-DM-004 §2.1、§4.2，第 56、61、101 行附近。

四个 CAD 路径字段在现有 `Settings` 中均允许 `None`，但注册表只声明通用 `path` 类型，没有 `nullable`、`required`、`allow_clear` 或空值序列化规则。

这不是单纯的 UI 细节。当前 Pydantic 会把路径空字符串解析成当前工作目录，并由现有 validator 进一步解析为绝对路径。因此，如果前端用 `""` 表示用户清空输入，后端可能保存一个完全错误的目录，而不是“未配置”。

**建议修订：**

- 注册表增加可空/可清除元数据；
- JSON 契约统一使用 `null` 表示未配置，禁止用空字符串代替；
- 路径控件提供“清除”动作；
- GET/PUT、文件存储与 Pydantic 三层都覆盖 `null` 往返测试；
- 文件过滤器按字段分别声明：Core Console 使用 EXE 过滤器，Worker Plugin 使用 DLL 过滤器。

### P2-02：未知 Schema 不能与损坏 JSON 使用相同恢复策略

**文档位置：** ARCH-DM-004 §2.2、§5，第 66、123 行附近。

文档把 JSON 损坏和 `schema_version` 不认识统一处理为“回退默认值且不阻止启动”。启动降级本身合理，但两类情况的后续写入风险不同：

- 损坏 JSON 无法可靠解释，可隔离后重建；
- 未知 Schema 很可能来自更新版本，其中的数据仍然有效，只是旧程序不理解。

如果旧版本回退后允许普通保存，它会用旧 Schema 覆盖新版本配置并丢弃未知字段，形成降级运行导致的数据破坏。

**建议修订：**

- 损坏文件先原样重命名为带时间戳的备份，再由用户明确确认重建；
- 未知 Schema 保持原文件不变，设置页进入只读诊断状态，禁止普通 PUT；
- 只有存在明确迁移器或用户执行“备份并重置”时才写入当前 Schema；
- 区分“缺少文件”“损坏文件”“版本过旧可迁移”“版本过新不可写”四类诊断码；
- 测试旧程序读取更高版本配置后不会改变原文件字节。

### P2-03：相对路径规则与当前兼容契约相反

**文档位置：** ARCH-DM-004 §5，第 121 行附近。

文档称“相对路径等”会按现有 validator 语义拒绝。但当前 `validate_cad_paths` 的实际语义是把相对 CAD 路径按当前工作目录解析为绝对路径，`test_cad_paths_resolve_relative_to_absolute` 也明确守护该行为。

因此，当前文字把一项行为变更误写成了兼容性沿用。实施者可能据此改坏既有 `.env`，或者继续规范化却违反新设计。

**建议修订：**

- 首选保持现有兼容行为：输入可为相对路径，但进入有效配置和用户文件前统一规范化为绝对路径；或
- 若产品决定 UI/API 必须拒绝相对路径，明确标为有意的兼容性变更，说明 `.env` 是否仍允许相对路径，并补充迁移、错误文案和回归测试。

两种方案必须择一写入权威设计，不能继续使用“沿用现有语义”的模糊表述。

### P2-04：注册表“元数据唯一来源”与保留 Pydantic 结构互相矛盾

**文档位置：** ARCH-DM-004 §2.1、§2.3、§5、§8，第 58～59、79、120、148 行附近。

注册表计划同时声明 `default`、`constraint` 和 `validate`，文档又要求 `Settings` 的字段、Field 约束和 validator 结构保持不变。以当前字段为例：

- `cad_max_parallel` 的默认值和 1～10 约束已经在 Pydantic `Field` 中；
- `worker_lease_seconds` 的默认值和 30～3600 约束也在 `Field` 中；
- `number_suffix_type` 的枚举范围由 `Literal[1, 2]` 定义；
- 字符串兼容和路径规范化由 `field_validator` 定义。

若注册表再保存一份对应内容，就有两套默认值和校验规则，无法保证所谓“唯一语义来源”。若把 validator 全部移出 `Settings`，直接构造 `Settings()`、读取 `.env` 和现有测试又可能绕过新规则。

**建议修订：**

选择并写清一种依赖方向：

1. **推荐方案：Pydantic 保持权威。** `Settings` 负责默认值、类型转换和最终校验；注册表只保存标签、分类、控件类型、文件过滤器和帮助文案，并从 Pydantic Schema 派生可派生的默认值、范围与枚举。
2. **共享定义方案：** 把字段约束和规范化函数放入不依赖 `Settings` 的底层定义模块，`Settings` 与注册表共同引用；通过完整性测试保证每个 UI 字段只有一份共享定义。

不建议让 `registry.py` 依赖 `Settings`，同时又让 `config.py` 反向导入注册表，这会形成循环依赖和不清楚的分层归属。

## 其他实现与产品注意点

以下事项不单独升级为 P1/P2，但应在修订或实施计划中明确：

1. **关于页外部链接：** 明确主页和反馈链接由系统默认浏览器打开，不应把当前 WebView 导航离开应用。若新增 ShellBridge 外链能力，只允许打开后端返回或代码登记的 `https` URL，不接受任意前端字符串。
2. **设置变化与旧预览：** `enable_add_number_suffix`、`number_suffix_type` 和 `cad_max_parallel` 会影响命名规划或执行估算。保存后应使相关旧预览失效，或依靠既有 preview digest 重新计算并明确向用户提示。
3. **关于页资源定位：** PyInstaller `datas` 实际位于 `sys._MEIPASS`/`_internal`。实现应复用 `runtime.resource_dir()` 读取 `LICENSE`，避免另写“exe 目录”定位规则。
4. **接口模型：** 三个端点应使用明确的请求/响应 Pydantic 模型，并为 `diagnostics`、约束字段、错误码、稳定排序和 Schema 修订建立 OpenAPI 契约测试。
5. **敏感信息边界：** 当前 9 项不属于凭据，但 GET 会返回本机绝对路径。设计应重申服务继续只监听 `127.0.0.1`，日志和诊断不得无差别复制完整路径。

## 建议的目标配置流程

修订后的最小可执行流程可以是：

1. `SettingsResolver` 分别读取代码默认值、环境变量和 `settings.json` 中的显式覆盖值。
2. 解析结果形成不可变 `SettingsSnapshot`：包含有效 `Settings`、逐字段来源、文件覆盖集合、诊断和 `config_revision`。
3. API 与 Worker 都通过同一 Resolver 获取快照；启动期字段只在进程启动时消费，运行期字段按明确边界刷新。
4. GET 返回当前快照及可编辑元数据。
5. PUT/PATCH 携带 `expected_revision`，在锁内完成基准校验、全量解析验证、同目录临时文件写入、`os.replace` 和内存快照替换。
6. Worker 在认领新任务前同步到已提交修订，并为任务冻结快照；旧任务继续使用旧快照。
7. 用户可以逐字段删除文件覆盖，恢复到环境变量或代码默认值。
8. 未知高版本 Schema 只读降级，不自动覆盖；损坏文件保留备份后才允许重建。

该流程不要求引入数据库或远程配置，也不扩大 ARCH-DM-004 当前范围。

## 建议补充的测试矩阵

除原文 §7 已列测试外，至少增加：

### 配置层级与清除

- 默认、env、file 三层逐项来源判定；
- 文件覆盖值与 env 值相同，`source` 仍正确为 `file`；
- 删除文件覆盖后恢复 env，再删除 env 后恢复 default；
- 只修改一个字段不会把其他 env/default 有效值写入文件；
- 未知 key、缺失 key、`null`、空字符串和类型错误的明确行为。

### 并发与一致性

- 两个并发 PUT 的内存与磁盘最终快照一致；
- 过期 `expected_revision` 返回 409 且不修改任何状态；
- desktop 与额外 `serve` 进程竞争时，进程间锁按设计工作；
- 文件写入成功但内存提交前发生异常时，启动重读能恢复到文件权威状态。

### Worker 热更新

- Worker 启动后修改 CAD 路径，下一个任务使用新路径；
- 修改并发度或超时后，新任务使用新值，已认领任务保持旧值；
- 修改租约时 API 恢复判断与 Worker 心跳不产生误回收；
- 任务详情或日志能追溯实际使用的配置修订。

### Schema 与故障恢复

- JSON 截断、非法 UTF-8、字段类型损坏分别产生稳定诊断；
- 未知高版本 Schema 不被 GET 或失败 PUT 改写；
- 用户明确重置前保留原文件，重置后保留可恢复备份；
- 临时文件、目标文件和锁文件均位于预期用户目录，不写入程序目录或项目目录。

### 路径与打包

- `null` 路径往返保持 `None`；
- 空字符串被拒绝或显式转换为 `null`，绝不解析为当前工作目录；
- EXE/DLL 文件过滤器分别通过 pywebview 真实格式校验；
- frozen 包内版本元数据和 `LICENSE` 均可从统一资源定位器读取；
- 移动绿色包后，未设置文件覆盖的插件默认路径跟随新 exe 目录。

## 转为 accepted 的复审清单

ARCH-DM-004 至少完成以下修订后再复审：

- [ ] 定义 API 与 Worker 跨进程热更新机制和任务级配置快照。
- [ ] 定义文件只保存显式覆盖值，并提供逐字段恢复继承语义。
- [ ] 定义保存事务锁、配置修订和冲突响应。
- [ ] 为可空路径增加 `null`、清除及字段过滤器契约。
- [ ] 区分损坏文件和未知高版本 Schema 的恢复策略。
- [ ] 解决相对路径兼容行为与现有实现的冲突。
- [ ] 明确 Pydantic 与注册表之间唯一、无循环的校验来源。
- [ ] 把新增并发、Worker、Schema 和路径测试纳入测试策略。
- [ ] 修订后检查 ARCH-DM-002、README 中 `.env`/setup.bat 用户路径是否仍与新的优先级和恢复继承语义一致。

## 临时结论

设置中心适合作为 DST Manager 下一阶段能力继续推进，但当前草稿只能作为方向性设计，尚不能作为无歧义的实施权威。完成上述 P1/P2 修订后，可进行一次聚焦复审；若复审关闭全部 P1、P2，并且测试矩阵进入实施计划，即可考虑转为 `accepted`。

## 待跟进事项

1. 由 ARCH-DM-004 作者选择并写入跨进程配置传播方案。
2. 固化 `PUT/PATCH + unset + config_revision` API 契约。
3. 固化 Pydantic 与注册表的依赖方向。
4. 修订目标文档测试策略并建立后续实施 Plan。
5. 修订完成后按“转为 accepted 的复审清单”重新审查。
