# PLAN-DM-048 提示消费者盘点与候选基准

> 执行备忘（2026-09-30）：只读盘点与 G3/G4 候选材料；用户已接受六项候选原则，SPEC-DM-006 仍为 `review`，G4 尚未冻结。本备忘不替代 [PLAN-DM-048](../../plans/dst-manager/PLAN-DM-048-hint-classification-and-feedback.md) 或 SPEC-DM-006。

## 1. 目的与范围

为 PLAN-DM-048 Task 1 建立可复核的现状清单、提示职责候选、设计取舍和技术映射，供 G0～G6 审核。盘点仅覆盖计划声明的 `web/src/views/`、`web/src/components/`、`web/src/layout/`、`web/src/composables/` 与 locale 源；不改生产组件、测试、API 或 SPEC。候选 HTML 只使用虚构数据和本地交互，不请求后端、不读写 DST/DWG，也不启动 AutoCAD。

## 2. 盘点口径与限制

在上述目标范围内扫描 153 个文件；其中 62 个 Vue 文件命中提示、状态、校验、ARIA 或通知信号。清单由字面 locale key 与源码标记的静态检索生成，初步归入 Lead/Help、Status、Error/Banner 和父级状态/props 提供四类。key 的词面类别和 CSS 类名都不能单独证明业务语义；动态 key、props/slot 透传、运行时状态所有者及显示/结束条件需要技术负责人结合调用方复核。未命中的文件也不代表运行时没有提示。

本表记录源文件、字面 key/静态信号、初步职责和计划批次，是迁移覆盖的入口清单，不把推断写成已验证契约。逐条用途、作用对象、显示条件、结束条件、主要播报者和保留/合并方案须在 G5 复核中依据源码与 SPEC-DM-006 补全；自动断言和 §7 追踪矩阵作为独立计划基线维护。

## 3. 五类提示的候选职责

| 类别 | 候选职责与放置 | 生命周期/播报原则 |
| --- | --- | --- |
| Lead | 在复杂区块入口解释整个区块目的；标题已自明时省略 | 持续显示；不重复字段规则 |
| Help | 解释单个字段或同一依赖上级共享的输入要求 | 与控件稳定关联；非阻断，修正前持续可查 |
| Status | 呈现 clean/dirty/pending/saving/saved 等持续业务状态 | 由状态所有者持有；关闭通知不改变任务或草稿状态 |
| Banner | 呈现当前范围的 notice/success/warning/error 及影响、目标、恢复动作 | 以文字、颜色和图标语义一致区分；独立风险分别可发现 |
| Error | 指出具体无效字段、错误原因及可执行修正 | 保留 `aria-invalid` 与描述关联；摘要定位后焦点进入首个错误 |

候选视觉复用 `web/src/assets/tokens.css` 的颜色、字体和间距变量；方向 A 为保留中性信息层级，以语义色只表达真实状态，并按标题自明程度决定 Lead。方向 B 为普遍增加区块解释/强调层。候选选择 A，理由是减少重复提示且不弱化错误；是否接受仍由业务负责人裁决。

## 4. G0～G5 候选证据状态

| 门禁 | 已准备的候选材料 | 尚需确认 |
| --- | --- | --- |
| G0 | 范围为 Web 提示分类、关联及异步反馈；不扩展后端/CAD/发布契约 | 业务与技术负责人确认 L 级范围和非目标 |
| G1 | 创建、标准/导入、属性编辑、设置/目录、全局壳层、异步任务六类用户路径 | 用户任务、成功结束条件和恢复职责 |
| G2 | Lead、Help、Status、Banner、Error 五类职责候选与关联原则 | 提示数量、位置、共享级联说明和主要播报者 |
| G3 | 方向 A/B 取舍和现有 token 复用方向 | 业务负责人选择视觉方向 |
| G4 | 27 种可复现情形、主题切换、重置、模拟创建；用户接受六项原则，采集 28 张正交截图，并于 2026-10-01 确认候选 HTML 可作为冻结基准 | 已冻结候选 Demo 和设计基准；生产实现同态对照及运行态键盘核验列入 G8 |
| G5 | 本表列出当前 Vue 消费者初筛及任务归属；§7 保留自动断言和跨任务追踪基线 | 逐消费者补充用途、作用对象、显示/结束条件、状态所有者、主要播报者、处置方案、断言、风险和回退；复核 ARIA/props 兼容 |

## 5. Demo 候选规格与差异边界

候选采用现有 token 和原语，覆盖提示职责、创建向导、图纸属性、标准管理、设置/目录、工作区外壳与任务反馈。控件标签使用约 13px 档位，Help/Status/Error 辅助文字使用约 12px 档位，正文约 14px；行距、圆角和间距取自既有 token。长文自然换行，不截断错误原因、目标路径、影响或恢复动作。用户已接受六项候选原则；这仍是设计候选，不代表生产实现已满足。

### 5.1 候选键盘与焦点规格

静态 DOM 顺序为：跳到主要内容链接；主题和重置按钮；页面区切换按钮；原生情形选择器、应用和回到初始按钮；当前可见页面内容中的表单控件与动作。页面区切换控件为原生按钮，不定义自制方向键模式；情形选择器保留原生 select 键盘行为。Tab/Shift+Tab 按文档顺序移动，Enter/Space 激活按钮，表单控件保留浏览器原生操作。不可用动作以原生 disabled 表示，不作为可操作目标。候选 :focus-visible 样式为 2px outline，并留 2px offset；跳过链接仅在获得焦点时出现。

上述内容是 G4 已冻结的候选交互规格，基于 DOM 与样式静态读取。本轮还在默认 Codex Browser 视口 596×764 做了有限键盘抽样：Tab 前 14 个焦点依次到达跳过链接、顶部按钮、页面区按钮、情形选择器、应用/重置和第一个内容字段，焦点样式均显示 2px 实线轮廓；Enter 激活“标准管理”，Space 激活“图纸属性”并切换到 dirty-pending 候选情形。该抽样不覆盖所有状态、反向遍历、真实读屏或 Windows WebView2；这些属于 G8/G9 对生产实现的验收证据，不是已执行的测试结果。

### 5.2 冻结 Demo 与生产的已知差异

| 页面/状态 | 候选原型 | 正式生产行为/保留约束 | 当前结论 |
| --- | --- | --- | --- |
| 创建与级联 | 展示虚构字段、共享/分离 Help 和多个错误 | 生产由创建草稿、属性身份与候选状态控制；既有级联清空、非法原值保留、切换影响和 XLSX 覆盖确认必须延续 | 候选只呈现状态，不含请求负载；逐消费者差异待 G5 对照 |
| 标准导入/发布 | 展示目标冲突、恢复动作及 warning 与 blocker 并存 | 生产仍以预览、基准修订校验和既有危险确认决定能否发布；目标路径、影响范围及恢复约束不得删减 | 静态候选不执行发布；生产控件/条件待复核 |
| 属性编辑 | 并列展示 dirty、pending、保存成功和失败 | 生产以编辑基准、比较结果和保存中状态为准；关闭 Toast 不得清除待写入或失败状态 | 候选状态均为预置数据；生命周期待 G5 映射 |
| 设置/图纸目录 | 展示已加载、dirty、冲突和导出失败 | 生产继续由现有设置 Provider、草稿与目录导出接口管理；冲突要保留目标和恢复信息 | 候选不读写 API 或本地文件；逐组件对照待完成 |
| 工作区外壳/任务 | 展示全局错误、修复状态、成功/失败/NEEDS_REVIEW | 生产的阻断由页面/后端状态持有，任务终态依赖 SSE/轮询代次与单次通知规则 | 候选不实现任务计时、重试、持久化或事件去重；待技术复核 |
| Banner tone | 展示 notice/info、success、warning、error 四类文字和语义边框 | 生产颜色须继续取用现有语义 token，并由 G8 计算实际对比度 | 候选没有冻结图标造型或计算对比度 |

上表记录冻结 Demo 与生产业务契约的已知边界；§9.1 将 27 种候选状态映射到生产状态所有者、保留契约和既有回归入口。它不替代 G5 对 62 个 Vue 消费者逐项补齐 props/ARIA 兼容、状态所有者、播报归属、准确测试断言、风险与回退。生产页面是否符合冻结基准由 G8 同状态证据验证。

候选原型链接、28 张不同状态/视口/主题的样本图、固定元数据及 SHA-256 见[资产索引](assets/PLAN-DM-048/README.md)。截图覆盖 1440×900、1024×768、1120×768 与 900×768，后者仅作韧性检查；全图记录实际图像像素尺寸，图像均为 JPEG 全页截图。

候选 DOM 中有跳过链接、原生按钮/选择器与可见焦点轮廓；静态预检确认 103 个唯一 id、11 个 aria-describedby 引用均指向现存目标。静态结果不等同于键盘遍历、屏幕阅读器播报或 WebView2 验收。原型以虚构数据运行，不含生产 API/持久化、完整页面数据和任务去重计时。

## 6. Vue 消费者初筛

下表由源码中的提示相关字面 key、ARIA、组件绑定和语义状态标记生成。它用于逐页复核，不是最终删除/保留清单；初步类别和任务归属均待技术负责人确认。

| 源文件 | 字面提示 key / 静态信号 | 初步类别 · 任务 |
| --- | --- | --- |
| `web/src/App.vue` | shell.workspace.recoveredBanner | Status · Task 8 / 按业务路径 |
| `web/src/components/creation/GroupBatchDialog.vue` | creation.groups.batchCurrentEmpty | Status · Task 3–4 |
| `web/src/components/creation/GroupsStep.vue` | creation.cascade.invalidSavedValue, creation.groups.addHint, creation.groups.derivedHint, creation.groups.empty, creation.project.emptyValue | Lead/Help, Status, Error/Banner · Task 3–4 |
| `web/src/components/creation/ProjectStep.vue` | creation.cascade.invalidSavedValue, creation.project.derivedPending, creation.project.derivedSheetPending, creation.project.emptyProperties, creation.project.emptyValue, creation.project.finalPathEmpty, creation.project.folderHint | Lead/Help, Status, Error/Banner · Task 3–4 |
| `web/src/components/creation/ReviewStep.vue` | creation.review.emptyValue, creation.review.errorsTitle, creation.review.executeHint, creation.review.jobFailedNote, creation.review.loading, creation.review.noticesTitle, creation.review.staleDesc, creation.review.stalePath, creation.review.staleTitle, creation.review.statusBlocked, creation.review.statusOk；含动态 key | Lead/Help, Status, Error/Banner · Task 3–4 |
| `web/src/components/creation/StandardStep.vue` | creation.standard.detailEmpty, creation.standard.empty, creation.standard.emptyAction, creation.standard.listError, creation.standard.loading | Status, Error/Banner · Task 3–4 |
| `web/src/components/creation/XlsxImportDialog.vue` | creation.xlsx.failed, creation.xlsx.success；含动态 key | Status, Error/Banner · Task 3–4 |
| `web/src/components/DraftActionsPanel.vue` | shell.draft.discardStale, shell.draft.pendingSummary, shell.draft.reloadConflict, shell.draft.staleMessage | Status, Error/Banner · Task 7 |
| `web/src/components/JobStatusPanel.vue` | jobs.files.error, jobs.files.status, jobs.job.errorDetail, jobs.job.retry；含动态 key | Status, Error/Banner · Task 7 |
| `web/src/components/PreviewPanel.vue` | shell.overlay.empty；含动态 key | Status · Task 7 |
| `web/src/components/properties/PropertyCsvPanel.vue` | properties.csv.noFileHint, properties.csv.notExecutableHint, properties.csv.statusExecutable, properties.csv.statusNoFile, properties.csv.statusNotExecutable, properties.csv.statusSelectedNoPreview | Lead/Help, Status · Task 5 |
| `web/src/components/properties/PropertyDefinitionPanel.vue` | properties.definitions.addDraftHint, properties.definitions.addHint, properties.definitions.addHintFiltered, properties.errors.propertyNameEmpty | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/properties/PropertyValueCompareDialog.vue` | properties.compare.dialogHint, properties.compare.emptyText | Lead/Help, Status · Task 5 |
| `web/src/components/properties/PropertyValuePanel.vue` | properties.values.dirtyCount, properties.values.errorCount, properties.values.expandHint, properties.values.flagDirty, properties.values.flagError, properties.values.flagPending, properties.values.hiddenDirtySuffix, properties.values.legendHint, properties.values.noValuesHint, properties.values.pendingCount, properties.values.submitHint；含动态 key | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/RepairStatusPanel.vue` | shell.repair.invalidError, shell.repair.repairedWarning；含动态 key | Error/Banner · Task 7 |
| `web/src/components/RevisionHistoryPanel.vue` | revisions.panel.fileConflict | Error/Banner · Task 8 / 按业务路径 |
| `web/src/components/settings/AboutSection.vue` | settings.about.loadFailed, settings.about.loading, settings.toast.linkOpened, settings.toast.linkRejected, settings.toast.linkTitle, settings.toast.linkUnsupported | Status, Error/Banner · Task 6 |
| `web/src/components/settings/ExtensionSettingsHost.vue` | errors.extension.schemaNewer, settings.extensionSettings.conflict.diagnostic, settings.extensionSettings.conflict.discard, settings.extensionSettings.conflict.message, settings.extensionSettings.conflict.retry, settings.extensionSettings.conflict.title, settings.extensionSettings.errors.summaryTitle, settings.extensionSettings.loadFailed, settings.extensionSettings.loading, settings.extensionSettings.readOnlyBadge, settings.extensionSettings.refreshFailed, settings.extensionSettings.sharedNotice, settings.retry；含动态 key | Status, Error/Banner · Task 6 |
| `web/src/components/settings/ExtensionsSection.vue` | settings.extensions.empty, settings.extensions.immediateNotice, settings.extensions.loadFailed, settings.extensions.loading, settings.retry | Status, Error/Banner · Task 6 |
| `web/src/components/settings/GeneratedExtensionSettingsForm.vue` | extensions.sheetCatalog.dirtyBadge；含动态 key | Status · Task 6 |
| `web/src/components/settings/SettingsDialog.vue` | settings.errors.conflict, settings.errors.saveFailed, settings.errors.summaryTitle, settings.extensionSettings.saved, settings.loadFailed, settings.loading, settings.retry, settings.saved, settings.toast.savedBody, settings.toast.savedRecalcBody, settings.toast.savedTitle；含动态 key | Status, Error/Banner · Task 6 |
| `web/src/components/settings/SettingsFormRow.vue` | settings.row.keywordHint；含动态 key | Lead/Help · Task 6 |
| `web/src/components/settings/SheetCatalogSettingsPanel.vue` | extensions.sheetCatalog.dirtyBadge, extensions.sheetCatalog.settingsFilterHint | Lead/Help, Status · Task 6 |
| `web/src/components/sheet-catalog/CatalogActions.vue` | extensions.sheetCatalog.exportConsistentHint, extensions.sheetCatalog.exportNotExecutableHint, extensions.sheetCatalog.exportRepreviewHint, extensions.sheetCatalog.exportRetry, extensions.sheetCatalog.exportStaleHint, extensions.sheetCatalog.exportSuccessTitle, extensions.sheetCatalog.noShellNotice, extensions.sheetCatalog.previewFailedTitle | Lead/Help, Status, Error/Banner · Task 6 |
| `web/src/components/sheet-catalog/CatalogPreview.vue` | extensions.sheetCatalog.previewEmptySheets, extensions.sheetCatalog.previewPending | Status · Task 6 |
| `web/src/components/sheet-catalog/ColumnEditor.vue` | extensions.sheetCatalog.columnStatusInvalid, extensions.sheetCatalog.columnStatusUnchecked, extensions.sheetCatalog.columnStatusValid, extensions.sheetCatalog.columnsHeadStatus, extensions.sheetCatalog.compatBadgeWarning, extensions.sheetCatalog.expressionSyntaxHint | Lead/Help, Status, Error/Banner · Task 6 |
| `web/src/components/sheet-catalog/FieldBrowser.vue` | extensions.sheetCatalog.fieldGroupEmpty, extensions.sheetCatalog.fieldHint, extensions.sheetCatalog.fieldSearchEmpty, extensions.sheetCatalog.fieldSyntaxHint；含动态 key | Lead/Help, Status · Task 6 |
| `web/src/components/sheet-catalog/TemplateBar.vue` | extensions.sheetCatalog.conflictMessage, extensions.sheetCatalog.conflictRetry, extensions.sheetCatalog.conflictSaveAs, extensions.sheetCatalog.conflictTitle, extensions.sheetCatalog.dirtyBadge, extensions.sheetCatalog.templateStateSaved | Status, Error/Banner · Task 6 |
| `web/src/components/sheets/ColumnSettings.vue` | sheets.columns.hint | Lead/Help · Task 5 |
| `web/src/components/sheets/SheetOperationForm.vue` | sheets.operation.emptyReferenceNotice, sheets.operation.existingSnapshotHint, sheets.operation.headHint, sheets.operation.layoutLoading, sheets.operation.statusDraft, sheets.operation.statusInvalid | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/sheets/SheetPropertyEditor.vue` | sheets.editor.headHint, sheets.editor.invalidTooltip, sheets.editor.statusClean, sheets.editor.statusDraft, sheets.editor.statusFailed, sheets.operation.statusInvalid | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/sheets/SheetToolbar.vue` | sheets.toolbar.bulkClearHint, sheets.toolbar.filterPending, sheets.toolbar.pendingFilterLabel | Lead/Help, Status · Task 5 |
| `web/src/components/SheetTable.vue` | sheets.table.statusBlocking, sheets.table.statusNormal, sheets.table.statusPending | Status · Task 8 / 按业务路径 |
| `web/src/components/standards/AssetInspectionPanel.vue` | standards.assets.failure, standards.assets.inspectPending | Status, Error/Banner · Task 5 |
| `web/src/components/standards/CascadePropertyEditor.vue` | standards.cascade.dialogHint, standards.cascade.empty, standards.cascade.emptyOptions, standards.cascade.hint | Lead/Help, Status · Task 5 |
| `web/src/components/standards/CompositionPropertyDialog.vue` | standards.composition.hint | Lead/Help · Task 5 |
| `web/src/components/standards/DerivedPropertyEditor.vue` | standards.derived.empty, standards.derived.hint, standards.derived.pendingSuffix | Lead/Help, Status · Task 5 |
| `web/src/components/standards/DwgNamingEditor.vue` | standards.naming.hint, standards.naming.invalidHint, standards.naming.templateHint, standards.naming.uniquenessWarning | Lead/Help, Error/Banner · Task 5 |
| `web/src/components/standards/EnumValuesDialog.vue` | standards.enumDialog.hint | Lead/Help · Task 5 |
| `web/src/components/standards/MappingPropertyDialog.vue` | standards.mapping.empty, standards.mapping.hint, standards.mapping.pending | Lead/Help, Status · Task 5 |
| `web/src/components/standards/OrdinaryPropertyEditor.vue` | standards.ordinary.csv.empty, standards.ordinary.csv.hint, standards.ordinary.empty, standards.ordinary.hint | Lead/Help, Status · Task 5 |
| `web/src/components/standards/StandardBasicEditor.vue` | standards.diagnostic.STANDARD_NUMBERING_INVALID, standards.editor.identityReadonlyHint | Lead/Help, Error/Banner · Task 5 |
| `web/src/components/standards/StandardDetailPane.vue` | standards.detail.empty, standards.detail.loading, standards.detail.retry, standards.detail.status | Status · Task 5 |
| `web/src/components/standards/StandardEditor.vue` | standards.editor.saveDraft, standards.editor.saveFailed, standards.editor.unsavedMessage, standards.editor.unsavedSummary；含动态 key | Status, Error/Banner · Task 5 |
| `web/src/components/standards/StandardImportDialog.vue` | errors.ui.unknownSummary, standards.import.renameHint, standards.import.success | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/standards/StandardLibraryPane.vue` | standards.library.empty, standards.library.loadFailed, standards.library.loading, standards.library.retry, standards.library.statusAll, standards.library.statusDraft, standards.library.statusLabel, standards.library.statusPublished | Status, Error/Banner · Task 5 |
| `web/src/components/standards/StandardPublishReview.vue` | standards.publish.countErrors, standards.publish.countFailures, standards.publish.countWarnings, standards.publish.descriptionHint, standards.publish.hint, standards.publish.inspectionFailedTitle, standards.publish.publishFailed, standards.publish.warningSummary | Lead/Help, Error/Banner · Task 5 |
| `web/src/components/standards/TemplateAssetsEditor.vue` | standards.assets.declarationHint, standards.assets.empty, standards.assets.emptyGroup, standards.assets.filePathHint, standards.assets.hint, standards.assets.layoutsReadFailed, standards.assets.officialReadOnly, standards.assets.paperLayoutsHint, standards.assets.sourcePathHint；含动态 key | Lead/Help, Status, Error/Banner · Task 5 |
| `web/src/components/standards/TokenExpressionEditor.vue` | standards.token.hint, standards.token.previewInvalid, standards.token.removeHint | Lead/Help, Error/Banner · Task 5 |
| `web/src/components/ui/FormField.vue` | 无字面 key；检查 props、slot 或动态解析 | 由父级状态/props 提供 · Task 2 |
| `web/src/components/ui/ToastHost.vue` | shell.toast.close, shell.toast.view | Status · Task 7 |
| `web/src/components/ui/UiInput.vue` | 无字面 key；检查 props、slot 或动态解析 | 由父级状态/props 提供 · Task 2 |
| `web/src/components/ui/UiSelect.vue` | 无字面 key；检查 props、slot 或动态解析 | 由父级状态/props 提供 · Task 2 |
| `web/src/layout/ActionDock.vue` | shell.dock.retry | Status · Task 7 |
| `web/src/layout/TopBar.vue` | 无字面 key；检查 props、slot 或动态解析 | 由父级状态/props 提供 · Task 7 |
| `web/src/layout/WorkspaceShell.vue` | errors.ui.diagnosticsDetails, shell.workspace.dismissError, shell.workspace.loading | Status, Error/Banner · Task 7 |
| `web/src/views/CreateSheetSetView.vue` | creation.wizard.resumeBanner | 由父级状态/props 提供 · Task 8 / 按业务路径 |
| `web/src/views/PropertiesView.vue` | properties.summary.fieldError | Error/Banner · Task 5 |
| `web/src/views/SheetCatalogView.vue` | errors.extension.schemaNewer, extensions.page.manageHint, extensions.sheetCatalog.loading, extensions.sheetCatalog.toastDeleted, extensions.sheetCatalog.toastSaved；含动态 key | Lead/Help, Status, Error/Banner · Task 6 |
| `web/src/views/SheetsView.vue` | sheets.view.emptyScope, sheets.view.emptySet | Status · Task 5 |
| `web/src/views/StandardsView.vue` | standards.delete.failed | Error/Banner · Task 8 / 按业务路径 |
| `web/src/views/WelcomeView.vue` | shell.welcome.dropHint, shell.welcome.recentEmptyNote | Lead/Help, Status · Task 8 / 按业务路径 |

## 7. 追踪矩阵与自动断言的实施责任

PLAN-DM-048 §7 是唯一权威的追踪矩阵，本节只说明消费路径，不复制整张矩阵。任务开始前需保持其状态“未覆盖”；只有通过自动回归、G8 同态 QA 和适用的 G9 实测后才更新。核心自动断言包括：

- 原语与关联：lead_help_use_fixed_semantic_color；description_error_first_and_unique；empty_required_fields_remain_individually_described_and_invalid。
- 级联身份：same_parent_one_shared_help；different_parent_separate_help；different_group_separate_help；shared_help_ids_do_not_collide。
- 持续状态与通知：success_feedback_dismissal_keeps_pending_write_status；duplicate_terminal_events_notify_once_per_attempt；polling_fallback_does_not_repeat_notification；failure_and_conflict_remain_visible_until_recovery；stale_subscription_has_no_effect。
- 关键业务路径：standard_import_conflict_preserves_target_and_recovery_action；creation_switch_and_xlsx_override_preserve_affected_inputs_and_target；independent_global_blocker_remains_visible_with_warning。
- 视觉/语义：static_banner_is_not_alert；hint_contrast_ratio_meets_wcag_threshold；跨页面视口/主题矩阵和错误定位读屏由计划 §7/§8 完整规定。

以上是待实施的断言清单，不是已运行结果。其覆盖率、退出码和失败/跳过原因必须由相应批次实际登记，不得从既有 PLAN-DM-034/047 的通过结果继承。

## 8. 用户裁决与本轮实际验证

业务裁决（用户于 2026-09-30 明确接受六项候选原则）：
1. 接受方向 A；标题自明时不加 Lead。
2. 接受候选 Help/Error 顺序、摘要定位和共享级联 Help 展示方式。
3. 接受成功反馈可关闭而持续草稿/任务状态保留，失败/冲突的目标、影响、恢复信息不折叠隐藏。
4. 接受 warning 与独立 blocker 并存，关闭通知不会解除阻断。
5. 接受四种 Banner tone 和 notice 的 info 色义；当前候选采用文字 tone 标签与语义边框，图标样式不纳入本轮冻结。
6. 接受 900×768 为韧性检查而非支持门槛，接受长文本不截断及正交截图采样方案。

G4 截图已完成：7 个页面/展示组各 4 张，共 28 张全页 JPEG，视口、主题、默认缩放、滚动位置、图像像素尺寸、采集日期、裁决记录与 SHA-256 已登记在资产索引。用户于 2026-10-01 确认候选 HTML 可作为 G4 设计冻结基准；完整冻结记录见 §9.3。截图与冻结 Demo 均不作为生产 G8 证据。

G5 技术复核待办：逐消费者核实源文件覆盖、用途与显示/结束条件、props/ARIA 兼容、状态所有者、双语 locale key 完整性、Toast 单一播报归属、任务失败保留策略、测试断言、风险和回退边界；技术负责人复核后才可记为通过。

本轮执行事实（2026-09-30）：在隔离工作区扫描 153 个计划目标目录文件，筛选并列出 62 个包含提示/关联语义标记的 Vue 消费者及字面 key；补全 27 种情形候选 HTML，采集并登记 28 张正交样本图，用户接受六项候选原则。HTML 结构预检为 103 个唯一 id、11 个有效 aria-describedby 引用、27 个已映射情形与完整页面/区块目标，唯一内嵌脚本通过 node --check；相对链接检查 7 份文档无缺失，git diff --check 通过。浏览器核对确认所设 CSS 视口、主题及滚动位置，目视检查了 900×768 warning/blocker、1120×768 深色任务复核和四种 Banner 样本；另在 596×764 默认 Codex Browser 视口抽样了 14 个 Tab 焦点、Enter/Space 激活与焦点轮廓。工作区未改生产组件、业务测试、API 或 Spec；未运行产品测试或构建，未做穷尽键盘遍历、屏幕阅读器或 Windows WebView2 验收。G4/G5/G6 尚无通过结论；SPEC-DM-006 仍为 review，计划保持 proposed。

## 9. 2026-10-01 状态与高风险源代码复核增补

SPEC-DM-006 已于 2026-10-01 修正 WCAG 2.1 SC 2.2.2/3.1.2 的适用范围并转为 `accepted`；这不代表完整 WCAG 实现验收通过。以下是本轮针对共享原语和异步高风险路径的静态复核样本，不替代第 6 节全部 62 个消费者的逐项映射，也不构成 G5 通过。

| 源文件 / 状态所有者 | 现状、显示与结束行为 | 关联 / 主要播报 | 对实施的约束、风险与验证落点 |
| --- | --- | --- | --- |
| `components/ui/FormField.vue` / 调用方 | 父级传入 label/hint/error；本组件只由 error 推导 invalid，不拥有校验状态或显示条件。hint/error 节点随 prop 是否有值挂载。 | 控件 ID 由调用方给定或 `nextInstanceId` 生成；插槽收到 `id`、`describedBy`、`invalid`。当前 `describedBy` 顺序为 hint 后 error，待按已接受的错误优先规范调整；组件当前不接收共享 Help。 | Task 2/3 扩展纯展示关联能力，不可复制校验规则。验证 Error 在 Help 前、IDREF 唯一有效、错误状态只来自调用方；回退为恢复旧 props/插槽契约，不改业务状态。 |
| `composables/useToast.ts` + `components/ui/ToastHost.vue` / Toast 列表由调用方持有 | `ok` 通知 5000ms 自动移除，`fail` 不自动移除；总量上限 4 条，当前入列会截去最旧通知，失败也可能被移除。关闭只删 Toast，不会清理工作区/任务状态。 | 宿主父级 `aria-live="polite"`，子项再设 `status` 或 `alert`；关闭和可选跳转动作在 Toast 内。父子播报语义可能重复，需 G5/G7 核实。 | Task 7 必须确保未处理失败不会因数量上限消失、每一事件仅一个主要动态播报来源；保留公开 `useToast`/Toast props。按 SPEC §7.3 评估 5 秒自动关闭与 0.18 秒入场动效的 SC 2.2.2 条件，`prefers-reduced-motion` 不作为替代。验证依托 fake timer、通知计数、读屏与真实桌面检查。 |
| `composables/useJobMonitor.ts` / 工作区任务状态 | 以 workspace ID 与订阅 generation 丢弃陈旧 SSE/轮询响应；断线回退每秒轮询；终态由共享状态码判定。成功后刷新/切换工作区；失败通知保留错误码和后端详情；`NEEDS_REVIEW` 禁止直接重试。 | 浮层停留在实施进度页时 `shouldSuppress` 阻止额外 Toast；其他终态通过 Toast 跳回进度页。SSE 与轮询分支都能触发终态处理，需以测试固定单次通知。 | Task 7 在原 generation/job 语义内增加每次尝试去重，不加 API/SSE 字段；验证重复终态、轮询回退、同 ID 新尝试、陈旧订阅和既有成功回调恰好一次。失败时回退通知代码，不回滚业务状态逻辑。 |
| `features/creation/useCreationJob.ts` / 创建向导草稿与创建任务 | 创建任务在普通工作区登记前独立监控；SSE 断开后回退轮询，generation 保护陈旧响应。成功必须取得 `workspace_id` 才切入工作区；非成功终态由调用方失效旧预览并保留草稿供修正重试。 | 共用 `isTerminalJobStatus` 与 `JobStatusPanel`，但独立于普通 `useJobMonitor` 的 workspace 身份匹配；没有普通工作区 Toast 通道。 | 不强行替换为普通任务监视器。Task 3/7 只在回归证明需要时改；验证成功切换、失败保留草稿/诊断、预览失效和轮询错误不抹除最后已知状态。 |
| `layout/WorkspaceShell.vue` / App 父级错误状态 | 错误以 prop 传入；关闭只记录当前错误文本为 dismissed 值，错误 prop 改变时重新显示。工作区加载/修订恢复中状态由 prop 控制。 | 全局错误 `role="alert"`；未知错误原始详情另由可展开 `details` 提供；加载/恢复使用 `role="status"`。 | 关闭不得清除父级错误或解除动作阻断；新错误及再次出现仍需展示。Task 7 核对 Banner 语义转换不移除可展开诊断或重新触发多重播报。 |
| `components/DraftActionsPanel.vue` / Draft props | `corrupted`、`stale` 分别控制持久问题提示；动作列表由父级 props 给出。stale 时撤销/重做/清空/预览/删除按钮禁用，冲突可重载，其他 stale 状态可丢弃；写入禁用、加载、游标共同约束预览。 | 当前 `.notice` / `.notice.error` 无显式 live role；恢复动作与提示同处一块。 | Task 7 要为 `corrupted`/`stale` 保留原因、后果、可执行恢复动作和现有禁用守卫，并显式定义提示类别及播报方式；不改 DraftAction 负载。用故障/冲突及禁用原因 E2E 验证。 |

本轮静态复核只覆盖上表 6 个共享或高风险源。G5 的其余消费者仍需逐项核实用途/对象、条件与终止、状态所有者、ARIA/props、主要播报者、处理方案、准确测试/断言及回退路径。任务 7 的 SC 2.2.2 适用性评估已补入 PLAN-DM-048 §7 与任务步骤；生产实现的完整键盘/逐状态对照列入 G8。

### 9.3 G4 冻结确认（2026-10-01）

用户确认 `docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html` 可作为 G4 设计冻结基准。冻结对象为 SHA-256 `b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d`、46101 bytes 的固定候选版本；关联资产索引中的 28 张截图、§9.1 的 27 种候选状态映射、§9.2 的键盘/焦点规格、六项业务裁决共同构成设计冻结包。G4 记为通过。

本确认冻结的是设计基准，不声明现有生产页面已与候选一致。生产同状态视觉、交互、完整键盘路径及 WebView2 行为按 PLAN-DM-048 的 G8/G9 验证；G5 逐消费者技术映射和矩阵交叉核对仍待完成，因此综合 G6 仍未通过。

### 9.1 G4：27 种候选状态的静态生产映射

下表把原型 27 个情形 ID 对应到生产状态所有者和既有回归入口。它证明候选与生产可以按同一业务边界逐项对照，但不证明生产运行态与原型一致；同组内具体消费者、条件、动态值与播报仍须按 G5 清单逐个完成。

| 候选情形 ID | 生产状态所有者/主要消费方 | 必须保留的生产契约 | 对照回归入口 |
| --- | --- | --- | --- |
| `initial`, `lead`, `help-error`, `cascade-same`, `cascade-split`, `multi-error` | 创建域的 `ProjectStep.vue`、`GroupsStep.vue`、`ReviewStep.vue`；级联候选来自标准/图纸组身份与创建输入状态 | 自明标题不增 Lead；Help/Error 并存且 Error 优先；Help 只按同一对象和上级身份共享；每个字段错误单独关联、无效值/清空规则和预览失效不变。原型没有真实标准数据或请求负载 | `create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts`；`cascadeHelp.test.ts` 为计划新增 |
| `dirty-pending`, `saving`, `saved`, `save-failed` | `SheetPropertyEditor.vue`、`PropertyValuePanel.vue`、`SettingsDialog.vue`、`StandardEditor.vue` 等实际编辑器；状态分别由编辑基准/草稿/请求所有者持有 | clean/dirty/pending/saving/saved/error 不相互替代；成功反馈结束后持续状态保留；失败保留输入和恢复入口；关闭反馈不能改变 dirty、请求守卫或正式发布状态。原型只演示状态，不执行保存 | `sheets-editing.spec.ts`、`properties-values.spec.ts`、`settings-dialog.spec.ts`、`standards-editor.spec.ts` |
| `standard-overview`, `standard-lead`, `conflict`, `warning-blocker` | `StandardLibraryPane.vue`、`StandardPublishReview.vue`、`StandardImportDialog.vue` 与相关发布/导入状态 | 标准标题/列表状态保留现有身份与发布语义；冲突显示目标、影响与安全恢复；warning 与独立 blocker 同时可见；所有正式写入仍经预览、基准修订、摘要与危险确认 | `standards-welcome.spec.ts`、`standards-editor.spec.ts`、`standards-assets-publish.spec.ts` |
| `settings-loaded`, `settings-dirty`, `settings-conflict`, `catalog-export-failed` | `SettingsDialog.vue`、`ExtensionSettingsHost.vue`、`CatalogActions.vue`；状态来自 settings/extension/catalog composables 与 Provider 基准 | dirty、409 冲突、只读原因、最终导出目标和“未覆盖”事实不因 Toast 关闭或切换视图丢失；不得在 UI 复制 Provider 校验 | `settings-dialog.spec.ts`、`extensions-settings.spec.ts`、`sheet-catalog.spec.ts` |
| `shell-ready`, `shell-global-error`, `shell-repair-warning`, `shell-repair-blocker`, `banners` | `App.vue` / `WorkspaceShell.vue`、`RepairStatusPanel.vue` 与全局 `.notice` 消费方 | 关闭全局反馈只改变呈现，不清除错误 prop、诊断、恢复约束或写入阻断；四种 tone 用文字和语义色表达，不以颜色单独传达。原型修复结果为模拟值 | `main.spec.ts`、`create-sheetset-review.spec.ts`、计划新增 `hint-contracts.spec.ts` |
| `job-success`, `job-failed`, `job-review`, `job-duplicate` | 工作区由 `useJobMonitor.ts` + `useToast.ts`/`ToastHost.vue` 管理；创建流程由独立 `useCreationJob.ts` 管理 | 成功通知关闭后任务终态仍在进度面板；失败/冲突保留错误码、详情与恢复动作；`NEEDS_REVIEW` 不直重试；重复 SSE/轮询只通知一次，但同 ID 新 attempt 可再通知。原型没有真实计时、网络、持久化或终态去重 | `main.spec.ts`、`create-sheetset-review.spec.ts`；`useToast.test.ts`、`useJobMonitor.test.ts` 为计划新增 |

### 9.2 G4：候选键盘与焦点静态核对

本轮从 HTML/脚本确认候选行为如下（不是穷尽键盘执行结果）：

- Skip link 指向 `#main`；主题/重置、页面选择、情形应用/重置均为原生按钮，情形选择为原生 `select`；页面切换以按钮 `aria-current="page"` 表示，不自定义方向键模式。
- 应用情形后候选页保留在应用按钮/选择器的当前焦点位置，通过唯一 polite announcer 报告切换结果；主题切换和重置也使用同一 announcer。
- 创建向导 Next/Back 将焦点移到新步骤标题（`tabindex="-1"`）；缺少必填值时聚焦首个错误控件并设置 `aria-invalid`/`aria-describedby`；错误摘要链接拦截默认跳转并显式聚焦目标。
- 原生 `disabled` 用于不可操作动作；截图抽样曾验证初始 Tab 的前 14 个停靠点和按钮 Enter/Space 激活，但没有覆盖全部 27 情形、Shift+Tab 反向序列、全部焦点恢复路径或屏幕阅读器。

上述规格已随候选 HTML 作为 G4 设计基准冻结。导航/错误定位的完整键盘遍历、动态状态切换后的焦点位置、关闭/恢复动作焦点归位、禁用控件跨浏览器可达性、真实读屏播报与 200% 缩放，仍须在 G8/G9 对生产实现验证；static DOM、axe 或既有 14 焦点抽样不能替代这些验收证据。

### 9.3 G4 冻结确认（2026-10-01）

用户确认 `docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html` 可作为 G4 设计冻结基准。冻结对象为 SHA-256 `b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d`、46101 bytes 的固定候选版本；关联资产索引中的 28 张截图、§9.1 的 27 种候选状态映射、§9.2 的键盘/焦点规格、六项业务裁决共同构成设计冻结包。G4 记为通过。

本确认冻结的是设计基准，不声明现有生产页面已与候选一致。生产同状态视觉、交互、完整键盘路径及 WebView2 行为按 PLAN-DM-048 的 G8/G9 验证。G5 逐消费者技术映射及追踪矩阵交叉核对按批次开始条件推进。

### 9.4 G5 批次映射：Task 2 提示原语

Task 2 的实现边界已按源码静态核实；本映射只覆盖本批次，不代表其余消费者已经完成 G5。

| 消费者/原语 | 状态所有者、用途与显示/结束条件 | 关联与播报 | 处置、验证、风险和回退 |
| --- | --- | --- | --- |
| `components/ui/FormField.vue` | 调用方持有 label/hint/error/required；组件不验证文案、不决定何时展示。hint/error prop 非空时挂载，变空时移除；`invalid` 派生自 error。 | 由 caller id 或 `nextInstanceId` 生成控件 id；slot 接收 `id/describedBy/invalid`；静态文案当前无 live role。现状 describedBy 顺序为 hint→error；无 shared Help prop。 | 保留既有 props/slot，新增 shared describedBy 并按 error→field Help→shared Help 去重。`uiPrimitives.test.ts` 的 `hint/error 的 id 按出现情况聚合进 aria-describedby`、`渲染可见 label，并把 id 与错误态下发给插槽控件` 覆盖现有契约；新增 `description_error_first_and_unique`、`hint_and_error_remain_visible`、`shared_description_updates_without_dangling_id`。风险是调用方 IDREF 失配；以 caller 条件同步和 ID 唯一/有效断言控制，回退时不改业务校验所有者。 |
| `components/ui/UiInput.vue` | 父级或 FormField 提供 label、id、描述与 invalid；组件只转发 input 值、disabled/readonly 与 `$attrs`，不持有业务校验状态。 | label 自有或由 FormField 提供，不能重复；`aria-describedby`/`aria-invalid` 落在原生 input；无 live role。 | 保留 props、v-model、透传及唯一 id。既有 `uiPrimitives.test.ts` 的 label/id、v-model/error/description、未声明 invalid 不输出 aria-invalid 用例作为契约；修改若影响现有控件即撤回包装变化，不能转移校验规则。 |
| `components/ui/UiSelect.vue` | 父级/FormField 持有选项、状态和显示条件；组件只转发原生 select 值与 disabled，选项由默认 slot 提供。 | label 自有或来自 FormField；描述/invalid 落在原生 select；无 live role。 | 保留 slot、v-model、原生选择键盘行为和既有 props。`uiPrimitives.test.ts` 的 option/v-model、唯一 id 和默认高度用例覆盖既有契约；本批不把业务状态搬入控件。 |
| `components/ui/UiHint.vue`（新增） | 调用方传 kind/live/id 并持有文本与更新时机；静态 Lead/Help/Error 默认无自动结束，动态 Status 容器须先挂载后更新。组件无 store、计时器或自动关闭。 | 默认 live off；polite/assertive 仅产生一个 status/alert owner；错误保留字段描述关联，不在组件内抢焦点。 | 新增 `static_banner_is_not_alert`、`dynamic_hint_has_one_live_owner`、`lead_help_use_fixed_semantic_color` 和类别 tone 类型断言；容器提前挂载由调用方保障。风险是重复播报或隐藏错误，回退时收回本批展示原语、不改调用方业务状态。 |
| `components/ui/UiBanner.vue`（新增） | 调用方持有 notice/success/warning/error 内容、影响、动作和结束条件；组件只呈现 tone、插槽内容及既有动作。 | 默认 live off；显式 live 时单一语义 role；notice 使用 info 语义色。文字标签与语义色承载 tone，图标造型未冻结。 | 用 `static_banner_is_not_alert` 验证静态不误报；tone 判别联合限制合法类别；不加入关闭业务、计时器或去重。若图标处理需回退，保留文字 tone 与语义 token，不隐藏正文/动作。 |
| `components/ui/descriptionIds.ts`（新增） | 纯函数，不拥有 UI 状态；接收 errorId、fieldHintId 和共享 ID 字符串，调用时生成当前描述链。 | 按错误→字段帮助→共享帮助顺序拆分空白、丢弃空值并稳定去重；空结果为 undefined。 | `description_error_first_and_unique` 覆盖顺序、重复和空输入；不访问 DOM、不修补不存在的共享节点。风险是悬空 IDREF，调用方须与元素显示条件同步，失败时回退旧单字段关联。 |

以上源码均已在 Task 2 前复核；`uiPrimitives.test.ts` 既有断言是基线而非本批新回归。Task 2 的错误优先顺序断言先失败，新增 `hints.test.ts` 在组件创建前无法收集，不计作行为 RED。2026-10-01 GREEN：定向 UI 单测 40 项通过，`check:ui` 与 Web 生产构建通过；主包 >500 kB 提示保留。G5 其余消费者须在各自批次开始前按同样字段映射并由技术负责人复核。

### 9.5 G5 批次映射：Task 3 创建向导与级联帮助

Task 3 的生产迁移已完成，技术负责人映射与 XLSX 失败诊断保留方案于 2026-10-01 获用户确认。级联共享 Help 仅覆盖「当前值为空且无可选项」的禁用控件；已有非法保存值继续显示原值并允许清空，不合并字段 Error。实现结果与验证记录见本节末。

| 消费者/状态所有者 | 用途、显示与结束条件 | 描述/播报及必须保留的行为 | 本批处置、验证、风险与回退 |
| --- | --- | --- | --- |
| `components/creation/ProjectStep.vue` / `CreationStore` 的固定标准、sheetsetValues、路径与派生值 | 级联控件由固定标准、同作用域父属性和当前值计算候选；仅当值为空且候选为空时禁用并显示 `creation.cascade.chooseParent`。非空但当前候选不含的保存值以单独 option 保留。`parentPath/folderName` 合成的最终路径始终可见；壳文件夹选择失败时保留手动路径输入并提供说明；派生计算无结果显示待计算。 | 级联共享 Help 已按表单实例、对象与来源属性分组，同一上级共用一个具名 Help 并关联所有相关控件；选择上级或候选恢复后同步撤下引用。保留动态 label、required/aria-required、目录 Help、最终完整路径及派生只读状态。 | 以表单实例 + `sheetset` 对象 + `source_property_id` 分组；ID 使用 `cascade-help-${domIdToken(JSON.stringify([instanceId, objectId, sourcePropertyId]))}`。验证同一上级共享、不同上级拆分、选择上级后帮助与 IDREF 同步消失、非法值仍可见、最终路径不变。若源属性名缺失，需在 G5 评审确认回退文案；不改变 store/API。 |
| `components/creation/GroupsStep.vue` / `CreationStore.groups`、标准与 `groupIssues` | 每个 group 独立持有 sheet_values；上级变化时 `updateGroup` 清空该对象中的直接级联字段。同一 group 内由同一上级控制且空值无候选的级联字段共用一个具名 Help；跨 group、上级或表单实例隔离。非空非法保存值保留原 option。图名/张数/模板/图幅错误由 `groupIssues` 驱动，行内列表仅在有错误时挂载；各控件的 `aria-invalid` 独立派生，均引用当前行错误列表。 | 一组中同上级的禁用级联字段应共享一份具名 Help，跨 group 或不同上级不能共用；上级变更或字段恢复可选后，引用与 Help 同步撤下。保留逐键错误不设 alert、每个控件自己的 invalid 判定、错误列表/焦点定位、同名组独立、非法级联值和显式清空。 | 按组件实例 + `group_id` + `source_property_id` 分组；删除当前 `replace(/[^a-zA-Z0-9_-]/gu, "-")` ID 拼接，复用闭合 URI token helper。验证特殊字符及元组边界不碰撞、不同 group/实例隔离、行错误仍关联、两个独立错误同时可见、保存值不被静默丢弃。失败回退到逐字段说明时仍保留 IDREF 目标。 |
| `components/creation/StandardStep.vue` / `CreationStore.loadCandidates` | 初次读取期间只显示 loading；候选请求失败显示带后端摘要的 Error；无可用标准显示原因列表和前往标准库动作；有候选显示选择项。三种状态按条件互斥，当前候选由 store 所有。 | Loading 与空结果当前为 status；请求错误为 alert。空原因列表与操作按钮属于空状态本体。保留固定标准选择入口、错误摘要和导航动作；不额外叠加相同 Lead/Status。 | 以现有 `creation-sheetset-input.spec.ts` 的候选加载/失败、无标准与标准固定入口测试验证；只有逐项比对确认重复的文案才在批次内删减。风险是把不可用原因或前往修复动作并入泛化提示后丢失；回退时恢复原三态模板。 |
| `components/creation/ReviewStep.vue` / 预览会话、preview diagnostics 与 `job` | 检查中显示 Status；无预览时展示过期原因与最终目标路径；权威预览展示计数、标准身份、最终路径与编号。错误和 notices 分别从后端诊断拆分，可同时存在；执行门禁由 `canExecute`、诊断、预览中与任务状态共同决定。 | 错误摘要现为 alert，并保留逐项跳转到字段/组；notice 区不设 live role。Warning 与 blocker 并列，blocker 不因 warning 呈现或通知结束而解除。任务终态错误说明保留在同一任务卡。 | 不合并 errors/notices，不删 target/path、受影响位置、诊断文本或定位动作；四种 Banner tone 仅用于相应语义且静态 notice 默认不创建 alert。验证错误+warning 同时可见、错误跳转/焦点不变、旧预览不可执行、失败任务保留草稿与重试路径。回退只恢复提示包装，不动 preview/session/API 状态机。 |
| `components/creation/GroupBatchDialog.vue` / 对话框本地 field/value/batchError 与 store 选中组 | 当前 field 决定输入控件；级联候选为所有选中组按各自父值计算的交集；交集为空显示“无共同候选”说明；应用错误单独显示，打开对话框时重置上次本地错误/输入。 | 共用候选说明当前是 status，批量错误为 alert；FormField 将输入和当前错误关联。它不是各组单独字段的级联共享范围，不得跨 group 用同一 Help 声称存在可选值。 | 保留“值不相同”、明确清空、整批校验、批量错误与关闭/应用动作。验证混合值和交集语义、无共同候选说明仍可见、应用非法值不部分提交；不改变选中组/批量输入所有者。 |
| `components/creation/SheetValuesDialog.vue` / 已完成权威预览 | 仅在打开时挂载只读模态，标题包含 group 与属性名，行数来自预览中的后端逐张值；关闭或 Esc 退出并归还焦点。 | 标题自明；当前 lead 显示图纸行数，增加明细范围信息，不是重复标题。无状态/Error/live region。 | 保留后端原值、图号顺序、空值呈现、表格横向滚动、对话框焦点进出；不为了分类新增 Lead/Status。现有键盘回归作为验证，回退只涉及提示包装。 |
| `components/creation/XlsxImportDialog.vue` 与 `CreationStore.importWorkbook` | 本地 `succeeded/file` 与 store 的 pending/message/diagnostics 分离；选新文件先清旧失败；覆盖前二次确认；成功替换全部输入并失效旧预览；失败不改草稿或预览且返回后端定位诊断。对话框关闭时 watcher 只清本地 file/succeeded；store 中最近一次导入诊断保留，选择新文件或开始新尝试时才清除。 | 当前 success 为 status、failure 为 alert；错误详情、工作表/行/列及全量覆盖边界均可见。按已接受的“失败/冲突保留目标、影响和恢复信息”，关闭对话框不应成为自动清除失败诊断的副作用；用户已批准保留失败摘要/诊断供重开查看，在选择新文件或开始新尝试时显式清除。成功关闭仍只结束提示，不回滚已导入草稿。 | 在 `creation_switch_and_xlsx_override_preserve_affected_inputs_and_target` 与既有 XLSX E2E 中断言取消不发请求、失败零变更、目标/诊断可恢复、成功全量替换与旧预览失效。主要风险为重开时把旧失败误认成新尝试；必须清晰标注它属于上次尝试并在新文件/新尝试时清除。回退须保留草稿与当前尝试诊断，不更改后端导入契约。 |
| `views/CreateSheetSetView.vue` / 向导编排及 `CreationStore` | 页面持有 resumeVisible 与 XLSX open 状态；store 持有 draft、步骤、pending/error。恢复草稿提示带继续/重新开始动作；draft save error 为全局 alert，保存中为 Status。切标准和重启前确认会放弃/清除兼容输入。 | 恢复 Banner、错误、pending 条件独立；最终路径在 ProjectStep/ReviewStep 当前可见。切换标准确认须明确旧字段、模板和预览被清除，不能由静态 Lead 替代。 | 保留路由退出阻断、草稿恢复/放弃确认、save error 及路径的显示和生命周期；检查全局 alert 不与步骤错误重复播报。对应输入/审查 E2E 验证草稿状态、请求数量、路径与预览失效。回退不更改向导/草稿状态机。 |

**Task 3 必须保持的既有验证入口：** `same_parent_one_shared_help`、`different_parent_separate_help`、`different_group_separate_help`、`shared_help_ids_do_not_collide`；E2E 至少覆盖级联过滤/清空、同组多错误、恢复的非法值、父值变更后的帮助撤下、切换标准确认、XLSX 覆盖取消/失败/成功和最终路径。`CreationStore` / `inputModel` 是状态与纯规则所有者，本批不得将候选校验、级联清空、预览失效或请求行为迁入 Vue 提示组件。


**Task 3 实施与验证（2026-10-01）**

- ProjectStep/GroupsStep 已实现级联 Help 共享及 ARIA IDREF 同步；同一上级共享、不同上级/group/表单实例隔离，非法旧值仍可见并可显式清空。StandardStep、ReviewStep、GroupBatchDialog、SheetValuesDialog、XlsxImportDialog 与 CreateSheetSetView 已按映射迁移提示原语，并保留错误定位、最终路径、草稿/预览与阻断行为。
- XLSX 导入失败后关闭并重开对话框会保留最近一次摘要和诊断；选新文件或开始新尝试时清除旧诊断。成功通知关闭不回滚已导入草稿。
- RED：实现前定向浏览器用例确认具名级联 Help/IDREF 缺失及 XLSX 关闭对话框后诊断被清除；修复后对应回归通过。
- GREEN：`rtk npm run test:unit -- src/features/creation/cascadeHelp.test.ts src/components/ui/hints.test.ts src/components/ui/uiPrimitives.test.ts`（3 个文件、44 项）；`rtk npm run test:e2e -- create-sheetset-input.spec.ts --workers=1 --retries=0`（55 项）；`rtk npm run test:e2e -- create-sheetset-review.spec.ts --workers=1 --retries=0`（46 项）；`rtk npm run check:ui`、`rtk npm run check:i18n`（1663 keys/11 domains）及 `rtk npm run build` 通过。构建仍报告主 JavaScript 包超过 500 kB。G8 生产浏览器视觉/运行态 QA 与 G9 Windows WebView2 验收未执行。


### 9.6 G5 批次映射：Task 4 欢迎页与标准管理/编辑

本映射根据 Task 4 涉及源码、现有 E2E、SPEC-DM-006 §6.7/§10.4、SPEC-DM-016 和现行身份/导入/删除契约 SPEC-DM-020 核对。此前用户已接受方向 A 与六项提示/响应式候选；标题自明时不增加重复 Lead，保留能说明边界、下一步或恢复办法的 Help。Task 4 只收口页面文案、提示关联和冲突呈现，不改标准 Schema、store/API、发布/导入/删除门禁或预检凭证流程。

| 消费者/状态所有者 | 用途、触发与结束条件 | 描述/播报和本批决定 | 必须保留的行为、验证与风险 |
| --- | --- | --- | --- |
| `views/WelcomeView.vue` / 页面静态文案与输入框本地路径 | 首屏说明打开既有 DST 与从标准准备新项目两条路径；shell 不可用时显示有可见标签的路径输入，最近打开记录为空时说明不造占位项目。 | 通用欢迎标题下的 `startDesc` 仅在仍补足下一步选择时保留；主卡/任务卡标题下不重复同义 Lead。拖放提示、无 shell 路径边界、标准驱动创建边界是不同信息，不能删成无说明入口。recent-empty 是静态说明，不包装为 Status。 | 保持「打开图纸集」唯一主操作、三个次级任务的顺序和去向、输入路径可见标签、空历史事实及 900×768 单列首任务优先；沿用 `standards-welcome.spec.ts` 的路由/布局回归。
| `StandardsView.vue` + `StandardLibraryPane.vue` / store 的 action/list 状态及本地 filters | 标准页标题与固定新建/导入/返回动作；列表加载、请求失败、全库为空、过滤无结果；错误由 retry 或新请求结束。 | 页面标题、筛选器 label 与清楚的空状态文本足够时不加重复 Lead。加载使用单一 Status；失败摘要用 Error 并保留重试；空库/无匹配保持普通内容，后者保留清除筛选操作；actionError 仍是当前操作 Error。 | 不将加载失败误报成空库，不清筛选/选择来隐藏失败，不新增重复播报；保留页面入口和列表筛选语义。验证浅/深主题和长文案。
| `StandardDetailPane.vue` / summary、detail、delete-impact 与 `StandardsView.vue` 删除流程 | 未选中时引导选择；详情加载/失败和重试；草稿/已发布/官方可执行动作不同；删除先取关联创建草稿数量，再确认和提交。 | 未选中为空态文本，不标 status；加载为 Status；详情失败为 Error 并保留重试。read-only 原因继续说明为何不可编辑。删除影响数持续显示；影响集合变化时保留目标标准与更新后的数量，说明旧确认失效并要求重新确认。 | 不因反馈关闭或冲突清掉所选目标、当前影响数、错误原因或安全恢复动作；不删除未关联草稿、项目快照或已创建图纸集。现有 `standards-library.spec.ts` 的 `STANDARD_DELETE_IMPACT_CHANGED` 回归是门禁，断言第二次确认使用新 token。
| `StandardEditor.vue` / 编辑缓冲、dirty/invalid、save/inspect/publish 请求及当前 draft ID | clean/dirty/saving/failed 状态；结构诊断跳转；发布检查、资源检查、发布失败及离开编辑器三选一门禁。 | 草稿标题/名称/ID已有身份信息时不加重复 Lead；`saveStateText` 是必须持续的编辑 Status，不随一次性通知结束而消失。保存/发布 Error 与阻断原因持续显示并保留重试；结构诊断摘要和逐项定位保持当前目标。 | 保存失败/修订冲突不丢缓冲或 dirty 状态；返回/切分区继续走既有保存、放弃、留在此处门禁；不将草稿保存误写成已发布。保持请求次数、基准与发布门禁。
| `StandardBasicEditor.vue` / numbering digits 和诊断 | 编号位数帮助常驻；合法性诊断出现时增加字段 Error，修复后撤下。标准 ID 为创建后不可变身份。 | `numberingDigitsHelp` 是解释补零规则的 Help；错误和 Help 并存，控件 `aria-invalid` 与描述 ID 同步，`aria-describedby` 顺序为 Error → Help。只读 ID 旁保留身份变更办法；自明分区标题下不再加重复 Lead。 | 保留空/零/负数/小数输入、不自动恢复默认值及既有发布/保存校验；E2E 同时断言 help/error 可见、invalid 与无悬空 IDREF。
| `StandardPublishReview.vue` / draft diagnostics、asset inspection、publish gate | 检查中 Status；问题/资产检查失败、warnings、errors、提交发布失败；各 issue 可跳回对应分区并聚焦。 | 「发布检查」标题下的说明若讲清 error 阻断、warning 不阻断和跳转行为则保留为有用 Help，不当重复 Lead。错误/警告数与检查失败分开；静态问题列表不设重复 live owner；发布失败用 Error；warning 与独立 blocker 同时可见，关闭可关闭的提示不解除 `gate.canPublish`。 | 保留 target section/字段、摘要、跳转和重新检查入口；旧/过期资产检查仍阻断；成功状态不替代持续草稿状态。沿用 `standards-editor.spec.ts` 与 `standards-assets-publish.spec.ts` 的警告、阻断和跳转回归。
| `StandardImportDialog.vue` / 当前 source path、preview result、diagnostics、expires_at、confirm phase | 选择 `.dststandard` → 服务端快照预检 → 用户确认；预检/导入中 Status；文件/凭证错误或确认竞态 Error；成功后本地列表定位新目标。 | 保留可见来源路径、候选 ID/名称、诊断目标与安全恢复方式。相同 UUID 已存在时不可改名绕过，清楚展示已有目标并禁用确认；不同 UUID 仅名称冲突时保留冲突名称、预填可编辑本机副本名，并说明原包 ID/发布时间/文件不变。确认阶段若 409，错误需保留源路径、候选/冲突目标及影响；旧 token 失效时给出重新预检动作，不允许直接重用。字段 Help/Error 并存时 Error 优先关联。 | 成功提示可随用户关闭，但导入库事实、刷新后的目标选择和已发布只读状态继续存在；关闭/取消仍取消临时快照。不得改写源 `.dststandard`、跳过预检或凭证、复用过期 token、改变 ID/name 冲突规则。新增冲突 E2E 放在现有标准库测试 `standards-library.spec.ts`（计划漏列，现修订）；断言 ID 冲突不可改名、名称冲突的局部改名、确认阶段竞态保留 target/path/recovery 且不产生部分导入。
| Task 4 涉及的属性/模板子组件标题与静态说明 | `OrdinaryPropertyEditor`、`CascadePropertyEditor`、`DerivedPropertyEditor`、`DwgNamingEditor`、`TemplateAssetsEditor` 等按区块标题和能力提示展示。 | Task 4 只删除与自明标题重复的 Lead；标题本身无法表达的来源范围、依赖、资产安全副本、字段规则或命名限制保留为一条有用 Help。字段错误、运行态 Status/Banner 和较深的控件关联继续留给计划中后续消费者批次，不趁本批合并。 | 不删除用户理解约束、命名风险或恢复办法所需内容；不更改验证门禁。对保留和删除的说明在 `standards-editor.spec.ts` 中用语义断言覆盖，避免仅以 CSS 类名证明视觉/语义。

**Task 4 开工前需复核的关键裁决：** 导入冲突区分“同 ID 不可绕过”与“仅名称冲突可改名”；确认竞态必须提示重新预检；删除影响变化需更新数量并再次确认；所有冲突反馈保留当前操作目标、影响和安全恢复路径。标准库 UI 现有 E2E 在 `standards-library.spec.ts`，因此本批测试范围需包含它。

**Task 4 实施与验证记录（2026-10-01）：** 用户已批准本节 G5 映射。自明标题下无重复 Lead；欢迎页和编辑器中说明范围、下一步、字段规则、资产安全或恢复办法的内容均保留。确认导入发生 409 时，保留来源路径和候选诊断、显示本地化错误摘要与服务端冲突目标、作废旧凭证并要求重新预检；编号位数的 `aria-describedby` 改为 Error → Help。warning + blocker 回归用例使用本地命名唯一性 warning 与无效编号 blocker，断言两者同时可见且发布仍禁用。

- 验证：`standards-welcome.spec.ts`、`standards-editor.spec.ts`、`standards-assets-publish.spec.ts`、`standards-library.spec.ts` 共 124/124 E2E 通过；`StandardImportDialog.test.ts` 15/15 通过。
- `check:i18n`（1663 键/11 域）、`check:ui` 和 `npm run build` 均通过。构建仍提示主 JS 包超过 500 kB；E2E 输出有既存 `NO_COLOR`/`FORCE_COLOR` 环境提示。现有 E2E 覆盖 900×768、200% 缩放、暗色英文与超长标准名；生产同态截图对照和 WebView2 运行态仍归 G8/G9。
- 本批没有删除有用说明，也未更改标准 Schema、导入/删除/发布契约或其他业务状态；移除/重排提示以外的视觉差异与完整截图证据留待 G8。
