---
id: SPEC-DM-002
title: DST Manager v0.21 CAD 单脚本布局重建需求调整规范
status: accepted
owners:
  - dst-manager
created: 2026-08-25
updated: 2026-08-25
related:
  - SPEC-DM-001
  - ARCH-DM-001
  - GUIDE-SH-001
  - ADR-DM-002
  - PLAN-DM-007
---

# DST Manager v0.21 CAD 单脚本布局重建需求调整规范

## 背景

当前 v0.21 的结构性图纸集编辑对每个受影响 DWG 分两次启动 Core Console：第一次执行布局删除、导入、重命名和保存；第二次重新打开暂存 DWG，加载插件并获取布局 Handle。该流程能够验证保存后的 DWG 可被新的 Core Console 进程打开，但会重复承担 Core Console 启动、DWG 打开、插件加载和退出开销。

Legacy 项目已经将布局重建和 `GetLayoutHandles` 放在同一个 `.scr` 中执行，并按每个 DWG 启动一次 Core Console。经本次需求确认，生产路径不要求保留“新进程重新打开”这一额外验证，因此 v0.21 采用单脚本执行策略。

本文只调整 CAD 执行粒度和对应验证边界，不改变图纸集编辑的业务规则、DST/XML 受控修改、Handle 契约、暂存发布、快照、锁和回滚语义。

## 范围

本规范适用于结构性编辑产生的每个 `RebuildWorkUnit`，包括既有 DWG 重建和模板创建的独立 DWG。

本规范不改变以下流程：

- 模板布局检查接口使用独立的只读 Handle 脚本；
- 非结构性属性修改不因本规范新增 CAD 调用；
- `cad_max_parallel` 的取值、并行调度和单工作区单写任务约束；
- DST/XML 编解码、路径解析、永久 before 快照和整批发布；
- AutoCAD 2016/2020 的版本选择、插件匹配和脚本参数安全校验。

## 行为要求

### 单脚本单次执行

每个重建工作单元必须生成并执行一个包含完整 CAD 操作的 SCR，并且对该工作单元只调用一次 `CoreConsoleExecutor.run()`。

脚本必须按以下逻辑顺序执行：

1. 设置批处理所需的 `FILEDIA`、`SECURELOAD` 和 `CMDECHO`；
2. 加载与所选 AutoCAD 版本匹配的固定 Worker 插件；
3. 执行 `DstDeleteLayouts`，只保留 `Model`；
4. 按执行计划从源 DWG/DWT 导入布局，并使用受控的临时名称和最终名称完成重命名；
5. 执行 `DstDeleteDefaultLayout`，清理不需要的默认布局；
6. 执行 `DstGetLayoutHandles`，在所有布局变更完成后生成暂存 DWG 对应的 `.dst-handles.txt`；
7. 恢复脚本运行环境并执行 `QSAVE`；
8. 执行 `QUIT`。

`DstGetLayoutHandles` 必须位于所有布局结构变更之后；不得在获取 Handle 后再执行会新增、删除或重命名布局的命令。脚本不得依赖第二个 Core Console 进程重新打开同一 DWG。

### Handle 回读与绑定

Core Console 退出后，Worker 继续从暂存 DWG 同目录读取 `.dst-handles.txt`，并沿用现有校验：

- 输出不能为空；
- 布局名集合必须与执行计划一一对应；
- Handle 必须符合现有格式、不可重复且不得为 `0`；
- 校验通过前不得生成最终 DST 绑定，也不得进入发布阶段。

`ScriptRenderer.render_handles()` 仍须保留，用于模板检查等只需要读取布局清单的场景；本规范只替换结构性重建路径中原有的重建脚本与 Handle 脚本拆分。

### 失败与事务

以下任一情况都必须使当前工作单元失败：

- Core Console 非零退出、超时或脚本命令失败；
- `.dst-handles.txt` 缺失、为空、无法解析或与计划不匹配；
- Handle 为零、重复或无法绑定到计划图纸；
- 暂存 DWG 在校验前无法读取或保存。

工作单元失败时，暂存成果不得进入正式目录；现有任务状态、失败日志、永久 before 快照、发布前校验和整批回滚语义保持不变。单脚本合并不得引入对正式 DST/DWG 的直接写入路径。

### 并行与调用次数

设本次任务实际重建 `G` 个 DWG：

- 调整前至少启动 `2G` 次 Core Console；
- 调整后结构性重建路径启动 `G` 次 Core Console；
- `G` 不包括模板检查等独立流程的调用。

本规范要求减少启动次数，但不承诺总耗时严格按比例下降。实际收益必须通过冷启动、热启动、不同布局数量和不同 `cad_max_parallel` 配置进行测量。

## 接口与日志

本次调整不改变 API、任务请求、任务状态枚举、DST 绑定结构或 `.dst-handles.txt` 文件格式。

Worker 的逐 DWG日志应把单次 Core Console 的 stdout/stderr 归档为一个完整阶段，明确标识其同时包含“重建布局”和“读取布局 Handle”。非零退出时仍须归档已取得的 stdout/stderr 以及对应错误阶段。

现有逐 DWG `duration_ms` 继续表示该工作单元从暂存复制到 Handle 校验完成的总耗时；行动方案应补充可用于前后对比的 Core Console 调用次数和分组耗时证据。

## 兼容性与安全边界

单脚本必须继续使用现有的 SCR 参数编码器，拒绝引号、控制字符、换行和其他危险输入；不得接受用户提供的任意 SCR 文本。

单脚本必须在 AutoCAD 2016 和 2020、单布局、多布局、模板创建、布局重命名和失败注入场景下保持相同的业务结果。布局名、顺序、Handle、DWG 路径及最终 DST 语义不得因执行次数减少而改变。

生产路径不再承诺“保存后由全新 Core Console 重新打开”的验证。该验证转为双版本真实 CAD 验收和诊断手段，不得被误写为正常任务成功的必要条件。实施时必须新增 ADR，记录这一验证边界变化，并同步修订 `ARCH-DM-001` 第 6.3 节中关于第二次 Core Console 的旧描述。

## 测试要求

### 单元与集成测试

- 验证合并脚本只加载一次插件，并按布局变更、Handle 回读、保存和退出的顺序渲染；
- 验证每个重建工作单元只调用一次执行器，并且首次调用即可产生 Handle 输出；
- 验证布局缺失、Core Console 失败、Handle 缺失、重复 Handle 和零 Handle 均不会产生绑定；
- 更新按 Core Console 调用序号注入第二个 DWG 失败的回归测试，确认正式文件和修订目录不产生半成品；
- 验证模板检查仍可使用独立 `render_handles()` 脚本；
- 验证单脚本与原有双脚本路径在模拟执行器下生成相同的布局绑定和最终 DST 语义。

### 真实 AutoCAD 测试

AutoCAD 2016 和 2020 均须在私有样本的临时副本上验证：

1. 单布局重建；
2. 多布局重建，至少包含最大 25 布局分组；
3. 模板创建独立 DWG；
4. 布局插入、删除、重命名和顺序派生；
5. Handle 清单与最终布局一一对应且非零；
6. 单脚本完成后，再由独立验证步骤重新打开最终 DWG，确认取消生产路径的重开验证不会掩盖 DWG 兼容性问题。

### 性能证据

至少对 1、2、25 布局的代表性工作单元，在 AutoCAD 2016/2020 和 `cad_max_parallel=1/2` 下分别记录：

- Core Console 启动次数；
- 单 DWG 和整批墙钟耗时；
- 插件加载次数；
- Handle 校验结果；
- 失败时正式文件哈希和发布状态。

性能结论以实际运行证据为准，不以单纯减少脚本文件数量代替测量。

## 验收标准

- 结构性重建每个 DWG 只执行一个 SCR 和一次 Core Console；
- 现有 Handle 绑定、DST/XML 校验和发布事务全部通过；
- AutoCAD 2016/2020 真实测试均通过，且生产路径不依赖全新进程重开；
- 调用次数相对原实现按受影响 DWG 数量减少一半；
- Core Console、插件、布局和 Handle 错误仍能被明确记录并阻断发布；
- 需求、架构、行动方案、测试和变更记录之间具有可追溯链接。

## 与既有文档的关系

本文补充 [SPEC-DM-001](SPEC-DM-001-v021-sheetset-editing-adjustment.md) 的 CAD 执行要求，并在实现完成后替代 [ARCH-DM-001](../architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 第 6.3 节中“第二次用 Core Console 重新打开并读取 Handle”的生产执行描述。DST/XML、Worker、路径、发布安全和双版本边界仍以 `ARCH-DM-001` 其余章节为准。
