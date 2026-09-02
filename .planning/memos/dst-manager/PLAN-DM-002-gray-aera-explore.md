# PLAN-DM-002 灰区审查结论

## 日期

2026-09-01

## 背景

本备忘记录 `PLAN-DM-002` 实施前对契约、写入门禁、草稿、性能和范围灰区的审查结论。结论已经用户确认，并同步回写正式计划；本备忘只保留事实、决策依据和尚未完成的前置设计，不代替 accepted Spec、ADR 或正式 Plan。

## 事实

### 契约与写入门禁

- 当前变更 API 使用 `list[dict[str, Any]]`，`_normalize_commands` 只完成命令白名单、旧命令别名和部分派生字段拒绝；`insert_sheet` 的 `number`/`title` 拒绝发生在领域规划阶段。
- `execute_changes` 当前只对 `requires_cad=true` 的写入强制 `preview_digest`；CSV 导入没有摘要字段，修复确认已经强制摘要；修订恢复和 XML 导出有基准/文件哈希复核，但没有绑定用户确认的完整预览摘要。
- Python 响应主要由手工 `dict` 组成，Web 在 `App.vue` 手工维护 TypeScript 类型；后端已经输出 `sheet.layout.file_name`、`sheet.layout.layout_name`，前端 `Sheet` 类型却未包含 `layout`，字段漂移已经实际发生。
- accepted 的 `SPEC-DM-001` 和当前领域模型只定义 `sheetset`、`sheet` 两种自定义属性作用域，不定义子集自定义属性。

### 子集删除

- 当前 `delete_sheet` 删除最后一张图纸会触发 `EMPTY_SUBSET`；请求中的 `delete_empty_subset` 不能绕过领域不变量。
- 当前 AcSm 契约要求 `AcSmSubset` 直属 `AcSmSheetSet`、`AcSmSheet` 直属 `AcSmSubset`，不支持嵌套子集。
- 对私有 Project1 样本的只读扫描结果为：45 个 `AcSmSubset` 全部直属 `AcSmSheetSet`，嵌套子集为 0；待删除子集完整子树中的 ID 在子树外引用数为 0。
- 工程外部是否仍有软件、脚本或其他文件引用主 DWG 无法由 DST Manager 完整证明。

### 草稿、性能与回归

- `Settings.data_dir` 默认是相对路径 `.dst-manager-data`，不能直接等同于不依赖 CWD 的应用数据目录。
- 当前没有草稿动作历史、撤销/重做或过期草稿重放模型。
- 私有 `sample/project1` 已提供 298 张真实图纸的可选结构基线，但公开仓库不分发该样本；Web 的 300 行交互性能不需要构造完整 DST，可使用合成 Workspace JSON。
- `job_files` 已记录 `cad_operation` 和 `duration_ms`，可以为后续耗时估算提供历史数据；首次运行仍需保守 fallback。
- 当前 Playwright 套件有 19 条用例；用例数量会增长，完成门禁不应把 19 写成永久固定值。

## 临时结论

### A1：类型化命令契约

- API 边界改用 Pydantic 判别联合，保持现有 `{"type": ...}` JSON 形状；预览请求与执行请求拆分，执行请求的 `preview_digest` 必填。
- 请求模型拒绝未知字段；旧命令别名只在明确兼容层正规化，再转换为不依赖 FastAPI/Pydantic 的领域命令对象。
- 内部领域类型不能代替 API 字段级校验和 OpenAPI 契约。

### A2：统一预览摘要门禁

- 所有由用户发起、可能修改 DST、DWG 或其他正式工程文件的发布操作统一要求“预览 → 明确确认 → `base_revision_id + preview_digest` 执行”。范围包括普通编辑、CAD 结构编辑、CSV 导入、修复发布、修订恢复和 XML 导出/覆盖。
- 草稿、SQLite 应用状态、日志、只读导出、自动回滚和启动恢复不属于正式业务发布，不要求用户预览摘要。
- 任务重试只能复用数据库中冻结的原始计划和摘要；任一基准漂移必须返回重新预览，不能以重试绕过确认。
- 摘要使用版本化、确定性的规范序列化，至少绑定操作类型、工作区、基准修订、规范化输入、人类可读语义差异、目标文件基准及适用的 CAD/来源基准。

### A3：API/Web 单一契约来源

- Pydantic 请求与响应模型是权威契约；补齐 FastAPI `response_model`，导出 OpenAPI/JSON Schema，并生成 TypeScript 类型。
- CI 检查生成结果无未提交漂移；不再以两份手工字段清单互相证明一致。

### A4：派生字段输出与搜索

- 复用既有嵌套 `sheet.layout.file_name`、`relative_file_name`、`layout_name`，不平铺一组重复且可能漂移的 `sheet.dwg_file/layout_name`。
- 生成的前端类型、图纸表格和搜索必须消费上述只读字段；DWG 搜索按文件名及相对/解析路径进行不区分大小写匹配，字段只用于展示、搜索和定位。

### A5：独立删除子集命令

- 新增独立 `delete_subset` 命令；`delete_sheet` 继续拒绝删除子集最后一张图纸，Web 此时引导用户选择“删除整个子集”。
- `delete_subset` 必须删除整个 `AcSmSubset` 节点及其完整受控子树，同时删除其中全部图纸和对应主 DWG；不得清空后保留空 `AcSmSubset`。
- Web 必须列出子集、全部图纸、主 DWG、后续派生命名/CAD 影响和回滚边界，并要求用户明确确认删除全部图纸和主 DWG。
- 系统不证明 DST 工程外部对该 DWG 的引用，用户对外部影响负责；删除前仍执行轻量 XML ID 防御检查，若待删除子树 ID 出现在子树外未知节点中则以 `UNKNOWN_REFERENCE_BLOCKED` 阻断。
- 删除后若仍存活图纸引用待删除 DWG，最终文档必然断链，必须阻断；这属于当前 DST 完整性校验，不是工程外部所有权证明。

### B6～B8：草稿模型

- 增加可配置的绝对草稿目录，默认解析到 `%LOCALAPPDATA%/dst-manager/drafts`，不依赖 CWD；草稿按 `workspace_id` 保存，并具备 schema 版本、原子替换、损坏隔离和冲突检测。
- 草稿保存不可变动作历史，并由历史投影出按“对象 ID + 规范化字段/属性名”收敛的有效意图；撤销/重做以一次 UI 动作为单位，批量编辑是一个原子动作。
- 基准修订或修复状态变化后，草稿标记为过期且不可执行；v0.3 不自动 rebase。用户可查看旧意图、重新加载最新工作区后手工重做，或明确丢弃。

### C9～C10：规模与耗时估算

- Web 使用合成 300 行 Workspace JSON 覆盖搜索、过滤、选择、渲染和键盘操作；后端解析/规划继续复用可用的 298 张私有黄金样本，公开 CI 需要确定性合成夹具时再使用最小 AcSm XML builder。
- 功能性 300 行 E2E 在 CI 执行；性能预算使用固定 Chromium 环境多次采样，避免用单次跨机器墙钟作为硬门禁。
- Core Console 数量和并发度由执行计划确定；耗时范围优先按 AutoCAD 版本和 `cad_operation` 使用历史 `duration_ms`，无足够历史时使用有版本的保守静态区间，并明确标注“估算值”。

### D12：前端重构回归门禁

- E2-01 完成条件是完整既有 Playwright 行为覆盖及新增用例全部通过、生产构建通过；不得把当前 19 条写成永久数量。
- 删除或改写旧用例必须保留等价行为覆盖，组件拆分不得以选择器调整为理由取消主流程回归。

## 待跟进事项

- `delete_subset` 实施前必须新增或修订正式 Spec/ADR，定义 DWG 文件删除如何进入永久 before 快照、暂存清单、发布日志、多文件删除/替换事务、失败回滚和启动恢复；该决策未在本备忘中提前代定。
- 实施完成后按 `PLAN-DM-002` 的测试矩阵记录实际性能预算、估算 fallback 常量及可用 AutoCAD 2016/2020 验收结果。
