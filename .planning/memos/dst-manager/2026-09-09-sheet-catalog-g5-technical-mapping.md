# 图纸目录内置扩展 G5 技术映射记录

日期：2026-09-09

范围：依据 `ARCH-DM-006` 与已接受的 `SPEC-DM-012`，把冻结 Demo 的数据、状态和交互映射到当前生产代码。本文是 G5 复核证据，不是实施代码。

## 已核对基线

- 领域投影：`domain/models.py` 已有 `Workspace.revision_id`、`Sheet.number`、`Sheet.title`、`Sheet.layout.file_name`、图纸集/图纸自定义属性。
- 字段定义：`domain/editing.py::property_definitions_from_document()` 已按 `casefold()` 合并声明定义与实际图纸属性，可作为规范名称唯一来源。
- 应用装配：`DstManagerService` 在启动时创建 `Database`，`create_app()` 直接在单文件注册 API；扩展域必须独立编排，不能把业务逻辑继续追加到服务和 API 大文件。
- 数据库：当前最新迁移为 `0005_dm019_job_lease_seconds`；`database.py` 已 782 行且没有扩展设置、偏好或 Artifact 表。
- 桌面壳：`ShellBridge` 已有文件/文件夹选择和可信工作区上下文；`run_desktop()` 在同一进程装配 API 与桥，可安全共享进程内一次性 `SaveGrantStore`。
- 前端：`TabBar.vue` 固定三标签，`App.vue` 已 683 行；已有主题令牌、toast、确认模态、未保存三选一对话框和键盘标签模型，可复用但不可继续把目录页状态堆入 `App.vue`。
- 多语言：`ARCH-DM-005` 已接受，但仓库尚无其 `vue-i18n` 运行时和语言资源实现。图纸目录必须提供稳定 `message_key` 及成对中英文资源，不能另建第二套翻译器；前端批次开始前先满足该已知集成前置条件。
- 契约生成：OpenAPI 通过 `scripts/export_openapi.py` 生成，`web/package.json` 的 `check:api` 会阻止 Python/TypeScript 契约漂移。
- 依赖与打包：已有 PyYAML，可读取随包 `manifest.yaml`；尚无 `openpyxl`。PyInstaller 使用 `packaging/dst-manager.spec` 显式声明资源，已有静态打包检查。

## 状态所有权

| 状态 | 权威所有者 | 生命周期与恢复 |
| --- | --- | --- |
| 扩展发现、兼容性、启停、活动调用数 | 后端 `ExtensionRegistry` | 应用启动发现；启停持久化；停用先拒绝新调用再排空同步调用 |
| 用户模板及修订 | SQLite 扩展设置仓储 | 跨工作区、跨重启；乐观并发冲突保留前端编辑 |
| 上次选中模板 | SQLite 工作区扩展偏好 | 只保存已保存模板 ID；失败为 best-effort 诊断，不阻断预览/导出 |
| 当前模板、未保存草稿、光标和字段浏览状态 | `useSheetCatalog` 前端会话 | 离开页面/切换模板/停用/关闭工作区前进入三选一保护；未命名草稿不跨重启 |
| 字段目录、兼容性、预览行、缺值统计、摘要 | 后端预览结果 | 绑定工作区修订、规范化模板、扩展版本和动作；任一变化要求重新预览 |
| 保存路径和目标基准 | 桌面壳 + 进程内 `SaveGrantStore` | 用户原生确认后创建短时、一次性授权；取消不创建授权 |
| 候选 XLSX | 应用数据目录临时文件 | 每次执行临时存在；成功或失败均清理，不成为长期副本 |
| 最终 XLSX | 用户选择位置 | 宿主校验并同卷原子替换；扩展永远不知道目标路径 |
| Artifact 元数据 | SQLite Artifact 仓储 | 仅最终保存成功后登记；普通目录页只显示路径，不显示哈希/来源修订 |

## 文件容量与拆分裁决

- `src/dst_manager/interfaces/api.py` 已超过约 500 行软上限：扩展端点新建 `interfaces/extension_api.py` 的 `APIRouter`，原文件只负责装配。
- `src/dst_manager/infrastructure/persistence/database.py` 已显著超限：新增扩展 ORM/仓储放入 `infrastructure/persistence/extensions.py`，共享 `Base` 和会话工厂；主文件只更新最新迁移常量及必要导出。
- `web/src/App.vue` 已超限：新页面状态集中在 `useSheetCatalog.ts`，页面结构放在 `SheetCatalogView.vue` 和专用组件；`App.vue` 只接收贡献列表并挂载编译期映射。
- `DstManagerService` 不新增表达式、XLSX、Artifact 或扩展生命周期方法；新建 `application/extensions/` 编排包，由 `create_app()` 组合。
- 现有 CAD job、发布器、ActionDock 和工程写锁不参与目录导出；若实现需要修改这些模块，应视为范围漂移并退回 G5/G6。

## 风险与处理结论

| 风险 | 处理结论 |
| --- | --- |
| 扩展借快照获得正式路径或可变对象 | 快照使用 frozen 值对象，`file_name` 同时处理 `\` 与 `/` 后只留 basename；能力上下文短生命周期且不暴露服务、数据库和工作区对象 |
| 自定义属性名称复杂或与固有字段重名 | parser 只接受点号标识符或 JSON 字符串方括号；固有字段保留，浏览器自动选择安全语法；绑定使用当前规范名称 |
| 模板能保存但换图纸集后字段不存在 | 保存只校验结构和语法；进入工作区后重新绑定，缺定义以可见阻断提示显示，缺值只警告且保留固定分隔符 |
| XLSX 公式注入与前导零丢失 | 所有单元格显式写字符串；候选回读检查单工作表、表头、行数、冻结/筛选和禁止特性 |
| 前端伪造任意输出路径 | API 不接受路径；只接受壳创建、绑定用途/工作区/目标基准的一次性授权 ID |
| 覆盖目标在选择后变化 | 授权记录存在性、身份和 SHA-256；最终替换前复核，不一致返回 `EXPORT_DESTINATION_CHANGED` |
| 生成或保存中途失败留下半文件 | 候选和目标同卷临时文件分别清理；只有原子替换成功后才登记 Artifact |
| 扩展失败影响核心宿主 | 清单逐项隔离加载；失败只改变该扩展状态；禁用全部扩展的核心 API 和三页面回归必须通过 |
| 目录页挤压现有外壳 | 独立页面占用主内容区，不使用 ActionDock；50 列仅在预览内容区横向滚动；900×700 与 200% 缩放纳入 E2E/G8 |
| 多语言基础尚未落地 | 后端从首批即使用稳定 key；前端批次只接入 ARCH-DM-005 的唯一 i18n 实例。若该实例届时仍不存在，在批次三检查点暂停，不以硬编码中文或局部翻译器绕过 |

## Spike 结论

没有必须在 Plan 前完成的 Spike：

- 清单读取已有 PyYAML 与显式 PyInstaller 资源机制；
- API 与桥在桌面进程内已有共同装配点，一次性授权不需要跨进程 IPC；
- pywebview 现有 `create_file_dialog()` 模式可扩展为固定 `SAVE_DIALOG`，其真实 Windows 行为不以单测代替，保留在 G9；
- XLSX 使用成熟的 `openpyxl` 生成和回读，依赖锁定、许可证和打包均能在实施任务内验证。

若实施时发现 pywebview 覆盖确认或 Windows `os.replace` 与冻结语义不一致，应暂停对应批次，写独立 Spike 记录并回到 G5 裁决，不得在生产代码中临场改变授权协议。

## G5 结论

设计中的数据、状态和交互均有现有来源或明确的新模块落点，没有需要先行验证的未知高风险点。多语言基础是已识别的批次四前置条件，不影响前三批后端纵向能力。G5 通过，可进入 `PLAN-DM-020` 的 G6 计划编制；pywebview 原生另存为、覆盖确认、目标漂移和 Excel 打开结果仍必须在 G9 真机验证。
