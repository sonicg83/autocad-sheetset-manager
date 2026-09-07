---
id: ARCH-DM-004
title: 设置中心（应用内配置 + 关于页）
status: draft
owners:
  - dst-manager
created: 2026-09-07
updated: 2026-09-07
related:
  - PRD-DM-001
  - ARCH-DM-001
  - ARCH-DM-002
  - ARCH-DM-003
document_kind: architecture
---

# 设置中心（应用内配置 + 关于页）

> 状态：草稿（2026-09-07 设计评审通过，待用户审阅后转 `accepted`）
> 定位：DST Manager 桌面软件形态下的应用内配置中心权威设计——以界面配置取代"编辑 .env"的用户路径，并提供关于/版本/开源协议页；同时为 [PRD-DM-001](../product/prds/PRD-DM-001-extensible-capability-platform.md) 扩展平台的设置分区预留接入结构。
> 原则：配置项元数据驱动（描述与渲染分离）、用户配置文件为最高优先级且原子写入、全部界面配置即时生效、不堵死扩展平台接入。

## 1. 目标与边界

### 1.1 背景

打包为 exe 后（ARCH-DM-002 绿色分发包），通过编辑 `.env` 修改配置不符合桌面软件习惯：`.env` 不随包分发给最终用户、编辑需要理解环境变量命名、且程序目录可能无写权限。需要应用内配置界面，同时保持开发态 `.env`/环境变量工作流不变。

### 1.2 目标

- 未加载 DST 工作区时即可查看和修改全部应用配置（顶部齿轮入口 + 模态对话框）。
- 配置保存后即时生效，无需重启应用。
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

### 2.1 注册表（元数据唯一来源）

新增 `src/dst_manager/settings/registry.py`：声明式注册表，每个界面配置项一条定义：

| 字段 | 说明 |
| --- | --- |
| `key` | 与 `Settings` 字段同名 |
| `label` | 中文显示名 |
| `category` | 分组（"AutoCAD 2016"、"AutoCAD 2020"、"任务执行"、"编号规则"） |
| `type` | `path` / `bool` / `int` / `enum` |
| `constraint` | 类型化约束：int 的 min/max、enum 的选项、path 的浏览器文件过滤器 |
| `default` | 代码默认值 |
| `validate` | 校验语义（收敛现有 `config.py` validator，避免两处维护） |

现有 9 个界面配置项全部登记：`autocad_2016_console`、`autocad_2016_plugin`、`autocad_2020_console`、`autocad_2020_plugin`、`cad_timeout_seconds`、`cad_max_parallel`、`worker_lease_seconds`、`enable_add_number_suffix`、`number_suffix_type`。

### 2.2 用户配置文件

- 路径：`%LOCALAPPDATA%\dst-manager\settings.json`（`LOCALAPPDATA` 缺失时回退 `~/AppData/Local`，与现有 `_default_data_dir` 同规则）。
- 新增 `src/dst_manager/settings/store.py`（infrastructure）：**原子写入**（临时文件 + `os.replace`），读取失败或 `schema_version` 不认识时回退默认值并产出诊断，**不阻止启动**。

```json
{
  "schema_version": 1,
  "values": { "cad_timeout_seconds": 900 }
}
```

### 2.3 合并优先级与热更新

- 优先级：**代码默认值 < `.env`/环境变量 < settings.json**。settings.json 的值在 `Settings` 实例化时作为 init kwargs 注入（pydantic init kwargs 天然覆盖 env）。
- 即时生效：引入运行时 Settings 持有者（单例，原子替换实例）。保存流程 = 全量校验 → 原子写文件 → 替换持有者实例。任务执行、CAD 调度等一律**执行时刻**经持有者读取；正在运行的旧任务继续用已取得的旧值跑完，不做中断。
- `src/dst_manager/config.py` 的 pydantic 结构保持不变（字段、validator 迁移/收敛进注册表时保持既有校验语义与错误信息）。

## 3. API 契约（版本化）

随现有 `interfaces/api` 单应用扁平路由新增 3 个端点；`/api/settings` 的请求/响应结构标注为版本化契约（`schema_version` 演进）：

- `GET /api/settings` → `{ schema_version, items: [{ key, label, category, type, value, default, source, ...类型化字段 }], diagnostics? }`。`items` 为注册表序列化；前端**只认描述、不认具体配置项**。`source` 标记当前生效值来源：`default` / `env` / `file`，用于排查"改了没生效"。
- `PUT /api/settings`，body `{ values: { key: value } }` → 后端全量权威校验，**要么全部生效要么全部拒绝**；失败返回 422 `{ errors: { key: message } }`（逐字段）；通过后原子写文件 + 热替换持有者实例，返回与 GET 同构的快照。幂等。
- `GET /api/about` → `{ app_name, version, license: { spdx, text }, homepage, feedback_url }`。版本号运行时读取 `importlib.metadata.version("dst-manager")`（唯一权威仍是 `pyproject.toml`，ARCH-DM-003 §2）；开发态包元数据不可用时回退读 `pyproject.toml`。MIT 全文来自仓库根 `LICENSE` 文件：开发态直接读取；frozen 态由 `packaging/dst-manager.spec` 将 `LICENSE` 加入 onedir 数据文件、运行时从 exe 目录读取——不内嵌第二份协议文本，保持单一来源。

三端点均**不依赖已打开的工作区**，未加载 DST 时可用。

## 4. UI：顶部齿轮入口 + 模态对话框

### 4.1 入口与形态

- 顶部栏右侧"小齿轮"图标按钮，**始终可见**（不依赖 DST 加载状态）。
- 点开为独立模态对话框 `web/src/components/settings/SettingsDialog.vue`；工作区标签栏保持纯业务视图，不增加"设置"标签。

### 4.2 对话框内部结构

- 左右布局：左侧窄条分区列表（本期"常规配置"/"关于"；未来"扩展中心"与扩展贡献分区在此追加，见 §6），右侧内容面板；内容超高在面板内滚动，不撑破对话框。
- **常规配置**：按注册表 `category` 分组动态渲染。控件映射：`path` → 文本框 + "浏览…"按钮（经 ShellBridge 原生选择器，见 §4.3）；`bool` → 开关；`int` → 数字输入（min/max 来自约束）；`enum` → 单选。
- **关于**：应用名 + 版本号、MIT 协议全文（面板内滚动）、项目主页/反馈链接。

### 4.3 原生路径选择器

`ShellBridge` 新增 `select_folder` 与 `select_file`（DLL 过滤器），基于 pywebview `create_file_dialog`，返回沿用桥的既有 `{ok, value} / {ok:false, code, message}` 模式。浏览器开发态（非桌面壳）"浏览…"按钮禁用、保留手输。

### 4.4 状态机与键盘（对齐 PRD-DM-001 UI-004/UI-005，为未来扩展对话框立标杆）

- 状态：未修改 / 编辑中 / 校验失败（逐字段行内错误）/ 保存中 / 已保存（短暂提示）。
- 未保存修改时关闭（Esc、✕、遮罩）先确认，不静默丢弃输入。
- Esc 关闭、焦点圈闭、关闭后焦点归还齿轮按钮、校验失败时焦点落到第一个错误字段。
- 实现约束：现有全局拖拽桥监听在 document 上，对话框遮罩与焦点管理须与其兼容——对话框打开时拖放事件不得穿透遮罩产生误操作。

## 5. 校验与错误处理

| 场景 | 行为 |
| --- | --- |
| 前端即时校验 | 类型、数字范围输入时反馈；不落盘 |
| 后端权威校验 | PUT 全量重验，注册表规则为唯一语义来源 |
| 路径格式非法（相对路径等） | 拒绝保存（沿用现有 validator 语义） |
| 路径不存在 | **允许保存 + 黄色警告**（AutoCAD 可能装在网络盘/后接机器）；执行失败走现有任务错误链路 |
| settings.json 损坏 / schema_version 不识别 | 回退默认值；GET 附带 `diagnostics`，对话框顶部提示"配置文件无法读取，已恢复默认"；不阻止启动 |
| 写入失败（磁盘/权限） | 保存报错；**内存 Settings 不替换**——文件是权威，避免界面值与重启后实际值错位 |
| 并发写 | 已有单实例守卫（PLAN-DM-018），无多进程写冲突 |

## 6. 与扩展平台（PRD-DM-001）的关系

本期**只留口、不实现**，三条预留：

1. **UI 分区式结构**：设置页 = 分区列表驱动。PRD-DM-001 UI-001 的"扩展中心"位于配置页、UI-002 把"设置分区"列为受控贡献点——未来作为新分区加入本对话框，导航模型天然支持，入口仍由宿主统一生成。
2. **存储隔离**：扩展设置将来使用独立命名空间（如 `extensions/<extension_id>.json`），满足 EXT-013 按 `extension_id` 隔离、带版本和校验规则的要求，**不复用**本文件 `values` 扁平映射；本期 store 的原子写、`schema_version`、损坏回退写成可复用函数。
3. **契约版本化**：`GET /api/settings` 的"描述 + 值"结构即 PRD 扩展贡献设置分区将来可复用的渲染契约；扩展设置走各自端点，不混入本契约。

渲染层（描述 → 表单）与存储层（原子 JSON + 版本）两个可复用件，正是扩展平台设置能力的对接点。

## 7. 测试策略

- **pytest 单元**：注册表完整性（`Settings` 每个 UI 字段有注册项、validator 语义与既有行为一致，含 `EnableAddNumberSuffix`/`NumberSuffixType` 字符串容错）；store 原子写、损坏回退、`schema_version` 处理；合并优先级（默认 < env < 文件）；热替换后持有者读到新值。
- **API 集成测试**：GET 契约快照；PUT 逐字段 422、全有或全无；落盘内容核对；`GET /api/about` 版本读取。
- **Playwright e2e**：未加载工作区时齿轮可见可开；修改 → 保存 → 重开对话框值保留；校验失败行内错误与焦点；未保存关闭确认；`npm run build` 生产构建。
- **手工验收**（e2e 无法覆盖，列入 rc 验证清单）：打包后桌面壳内路径选择器真实弹窗、保存后配置对真实 CAD 任务生效。
- 回归安全网：改动 `config.py` validator 收敛时，既有测试（当前 642 passed 基线）必须保持通过。

## 8. 风险与实现注意点

- **frozen 态包元数据**：`importlib.metadata` 需要 PyInstaller 收集 `dst-manager-*.dist-info`；若默认未收集，在 `packaging/dst-manager.spec` 补 hook。连同 §3 的 `LICENSE` 数据文件，spec 共两处新增——这是本设计仅有的打包配置触点。
- **validator 收敛**：`config.py` 现有 validator（绝对路径、CAD 路径规范化、布尔/枚举字符串容错）语义必须原样保留进注册表，`data_dir`/`draft_dir` 相关校验留在原处不动。
- **文档索引**：本文接受后同步维护 `docs/dst-manager/README.md` 索引与根 `changelog.md`。
