---
id: SPEC-DM-019
title: 图纸标准版本身份与标准包预检导入规范
status: accepted
owners:
  - dst-manager
created: 2026-09-25
updated: 2026-09-25
related:
  - RFC-INT-003
  - ARCH-DM-001
  - ARCH-DM-007
  - SPEC-DM-016
  - SPEC-DM-017
  - SPEC-DM-018
  - PLAN-DM-035
  - PLAN-DM-038
  - PLAN-DM-040
  - PLAN-DM-041
---

# 图纸标准版本身份与标准包预检导入规范

## 1. 目的与权威范围

本文是 DST Manager 图纸标准**版本身份**、**名称唯一性**、**本机发布版本分配**与
**`.dststandard` 标准包两步导入（限时快照预检 + 凭证确认）**的唯一长期权威。

- 标准文档与标准包的数据格式、`version` 的类型与取值范围、草稿与发布版本的差异、名称比较口径、
  标准库目录形态、工程绑定字符串、导出包文件名与导入凭证语义，均以本文为准。
- 页面行为（欢迎页入口、标准库列表与详情、导入弹窗状态与焦点）见
  [SPEC-DM-016](SPEC-DM-016-drawing-standard-management-ui.md)；属性语义、DWG 命名与规则求值见
  [SPEC-DM-017](SPEC-DM-017-standard-properties-and-dwg-naming.md)；创建向导的版本展示见
  [SPEC-DM-018](SPEC-DM-018-standard-driven-sheetset-creation-ui.md)。三者在涉及版本身份处只描述页面行为，
  并链接本文，不重复本文规则。
- 官方标准的编制、双重审核、晋升与随 Manager 分发流程见
  [GUIDE-DM-007](../guides/GUIDE-DM-007-official-standard-package-release.md)。
- 本文不定义 DST/DWG 发布器、CAD SCR 渲染器或 AutoCAD Worker 插件行为；不改动
  [ARCH-DM-001](../architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 的发布事务、锁与快照契约。
- Web 服务继续只监听 `127.0.0.1`；本文所有“本机路径”语义都建立在这一前提下。

### 1.1 本轮变更摘要

| 变更 | 替换的旧契约 |
| --- | --- |
| 标准发布 `version` 从三段字符串（`2.1.0`）改为正整数（`1`、`2`…），文档格式升为 `schema_version: 2` | `standard_schema` 的三段版本 pattern 与 `Schema v1` 文档 |
| 草稿不携带 `version`；发布时由服务端在受控写入边界内分配 | 草稿可填写版本、前端预分配版本 |
| 导入从“直接接收本机路径”改为“预检 + 凭证确认”的两步流程 | `POST /api/standards/import {path}` 单步导入 |
| 标准库列表按 `standard_id` 归集并以整数降序排序 | 列表以 `<standard_id>@<version>` 字符串身份平铺、字符串比较排序 |

## 2. 版本与身份契约

### 2.1 `schema_version` 与标准发布版本是两件事

- `schema_version` 是**文档格式版本**，表示标准 JSON 的结构世代；
- `version` 是**标准发布版本**，表示同一 `standard_id` 下第几次对外发布。

两者互不推导、互不换算。本轮之后文档格式版本为 `2`，因此任何新写入的发布文档与
包内 `manifest.json` 都必须是 `schema_version: 2`；`version` 是整数。

### 2.2 正式标准文档与标准包

已发布标准文档（库内 `document.json` 与包内 `manifest.json`）必须满足：

| 字段 | 类型与取值 | 说明 |
| --- | --- | --- |
| `schema_version` | JSON 整数 `2` | 只接受 `2`；其他值以稳定码拒绝 |
| `standard_id` | 非空字符串，符合 `^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*$` | 大小写差异不产生两个标准 |
| `version` | JSON 整数，范围 `1..2147483647` | 见下表拒绝清单 |

`version` 的拒绝清单（一律稳定拒绝，不做隐式转换）：

- `0` 与任何负数；
- JSON 布尔值 `true`/`false`（Python 的 `bool` 是 `int` 子类，必须显式排除）；
- 小数（`1.5`、`1.0`）；
- 字符串（`"1"`、`"1.0.0"`，包括旧三段字符串）；
- 超过 `2147483647` 的整数；
- 缺失 `version` 字段的发布文档。

`0`、负数、布尔、小数、字符串与旧三段版本一律拒绝，不提供兼容层、不静默升级。

### 2.3 草稿文档

草稿文档同样使用 `schema_version: 2`，但**不包含 `version` 字段**：

- 草稿不持有正式版本，也不预占版本号；空白草稿、复制发布版本得到的草稿、
  从 DST 提取的草稿一律不写 `version`；
- 派生草稿（复制一个已发布版本）不继承源版本的 `version`；
- 草稿文档若携带 `version` 字段，保存与发布前解析都必须以稳定码拒绝；
- 标准库列表响应以 `version: null` 表示草稿条目，已发布条目为整数。

版本只在服务端发布时分配（见 §3）。界面上不允许用户输入或预留版本。

### 2.4 依赖版本 `dependencies[*].min_version`

`dependencies[*].min_version` 描述的是**受信扩展能力的语义化版本**，与标准发布版本无关：

- 保留三段语义化字符串格式 `X.Y.Z`（如 `1.2.0`）；
- `schema_version: 2` 不改变其格式与校验；
- 继续接受 `"1.2.0"`，继续拒绝整数 `1` 与 `"1"`；
- 实现上，标准发布版本与依赖版本**必须使用两个独立的解析器**
  （`_parse_standard_version` 与 `_parse_dependency_version`），不得共用同一 pattern，
  以免一侧放宽或收紧时静默污染另一侧。

### 2.5 路径、路由、绑定与导出文件名

| 对象 | 形式 | 说明 |
| --- | --- | --- |
| 发布目录 | `<standard_id>/<n>/` | 官方根与用户发布根同构；`<n>` 是十进制正整数目录名 |
| 正式版本身份 | `<standard_id>@<n>` | 用于工程绑定、日志与审核记录 |
| HTTP 版本路径段 | 规范十进制正整数 | 只接受 `1`、`10` 这类规范形式；`01`、`1.0`、`0`、`-1`、含分隔符或前缀的输入一律拒绝。位数先于整数转换校验（超过 `2147483647` 的位数直接拒绝），不得让超长数字串导致 500 |
| 工程保留属性 | `DSTManager.Standard = <standard_id>@<n>` | 沿用既有保留属性，仅值形态改变 |
| UI 展示 | `v<n>` | 界面加 `v` 前缀，文档与 API 字段保持裸整数 |
| 导出包文件名 | `<standard_id>-v<n>.dststandard` | 见 §5.4 |

路径段的边界校验继续执行 [PLAN-DM-040](../../../.planning/plans/dst-manager/PLAN-DM-040-standard-platform-review-remediation.md)
Task 1 的越界与非法名拒绝（分隔符、相对分量、盘符、控制字符、尾随点、Windows 保留设备名、超长）。

### 2.6 残留 `schema_version: 1` 数据

不自动迁移历史 `schema_version: 1` 草稿或发布目录：

- `list()` **跳过**这些条目（与 PLAN-DM-040 Task 1 非法草稿目录同口径：不删除、不阻断其余条目）；
- `get`、`get_document`、`read_package` 对 `schema_version: 1` 内容返回稳定
  `STANDARD_SCHEMA_VERSION_UNSUPPORTED`（HTTP 422），不降级、不猜测、不部分解析；
- 若实施前发现真实历史数据（已分发标准包或已绑定工程），必须**先暂停并修订兼容与迁移规则**，
  不得在本规则之上直接进行不兼容变更。当前确认无已分发真实标准包与绑定工程，仓库测试夹具与
  Demo 一并更新为 v2。

## 3. 本机发布的版本分配与名称唯一

### 3.1 版本分配

- 发布时服务端在**同一锁内**读取官方库与用户库中该 `standard_id` 的全部已发布整数版本，
  取最高值 `max`，分配 `max + 1`；
- 该 ID 无任何历史版本时分配 `1`；
- 并发发布同一 `standard_id` 不得得到相同版本：读取最高版本到原子发布必须在同一互斥区内完成；
- 发布失败不消耗版本、不预留空目录、不留半成品；失败后原草稿、草稿资产与已发布版本完整；
- 最高版本已是 `2147483647` 时以 `STANDARD_VERSION_LIMIT_REACHED` 稳定拒绝，不回绕、不复用。
- 分配得到的版本在暂存区写入文档后仍须过完整发布解析与门禁；只有全部通过才原子提交。
- **唯一性覆盖范围**：版本唯一性与「预检→确认」之间的门禁复核由**进程内互斥**保证——接口层标准端点都是同步 `def`，
  在线程池中真正并行执行，同一进程内的多个请求可以交错（单实例约束只排除第二个**进程**，不排除第二个**请求**）。
  此外按用户库根加一道跨进程文件锁：按 [PLAN-DM-018](../../../.planning/plans/dst-manager/PLAN-DM-018-desktop-single-instance.md)
  的裁决，桌面壳为唯一交付入口且单实例，故跨进程维度属**纵深防御**而非承诺；当 `serve` 升为受支持的并行入口、
  或 `data_dir` 指向共享/漫游位置时，该维度转为必需并需补真实双进程证据。

### 3.2 名称唯一门禁

名称比较对**官方库与用户库中已发布版本**的 `name` 执行：

1. Unicode NFKC 归一；
2. 去除首尾空白；
3. 连续空白归一为单个空格；
4. `str.casefold()` 大小写折叠。

不得使用 `lower()`：德语 `ẞ`、土耳其 `İ` 等字符在 `lower()` 下与 `casefold()` 结果不一致。

规则：

- 同一 `standard_id` 的多个版本可以沿用同一名称，也允许跨版本改名（改名不改变身份）；
- 不同 `standard_id` 的已发布标准，归一化后名称相同即冲突；
- 草稿**不占用**名称：草稿之间的同名不阻断保存，也不阻断其他标准发布；
- 冲突检查在**预检**与**最终写入**两处都执行（见 §4）；
- 冲突码为 `STANDARD_NAME_CONFLICT`（HTTP 409）；同一 `standard_id + version` 冲突仍为
  `STANDARD_VERSION_EXISTS`（HTTP 409）；
- 列表与组标题口径：组标题取当前筛选结果中**最高整数版本**的名称；仅有草稿时显示标准 ID；
  历史版本仍按其原名称显示。

## 4. 标准包两步导入

### 4.1 两步流程

导入固定为两步，不允许合并为一步：

1. **预检**：`POST /api/standards/import-previews`，请求体 `{path}`。服务端把选定的包
   复制到限时快照并校验，返回候选身份、同 ID 已有版本、稳定诊断、`can_import` 与
   可用的不透明凭证。预检**不写标准库**。
2. **确认**：`POST /api/standards/import`，请求体 `{preview_id}`。服务端在仓储写入锁下
   复核库状态与包门禁，然后从**预检快照**导入。

服务端不得继续接受 `{path}` 形式的直接导入：HTTP 层只有凭证入口，
应用内部的路径导入（若保留）只允许凭证流程调用。

### 4.2 限时快照

- 快照根固定为 `settings.data_dir/tmp/standard-import-previews`；
- 只复制所选源文件，复制前校验扩展名白名单（`.dststandard`）与压缩源文件字节数上限 **256 MiB**；
- 复制采用流式写入随机文件名，完成后原子定稿；复制中断不留半成品；
- 临时文件不得进入任何工程目录、标准库目录或包内；
- 凭证有效期为 **15 分钟**；
- 过期、取消与服务重启后，快照与凭证一并失效；重启后一律要求重新预检；服务启动时**清空快照根**（残留快照已无凭证指向，按定义不可达）；
- 过期与取消的快照必须被清理，不在快照根无限累积。

### 4.3 预检结果

预检响应包含：

| 字段 | 含义 |
| --- | --- |
| `preview_id` | 不透明、随机、不可猜测的凭证；冲突时可以为空 |
| `expires_at` | 凭证到期时间 |
| `standard` | 候选身份：`standard_id`、整数 `version`、`name` 与能力摘要 |
| `existing_versions` | 官方库与用户库中该 `standard_id` 的已有整数版本及来源 |
| `diagnostics` | 稳定错误码 + 严重级 + 可定位信息 |
| `can_import` | 是否可确认导入 |

- 身份冲突（同 ID + 同版本）或名称冲突（不同 ID、规范化同名）返回 **HTTP 200 且
  `can_import=false`**，并给出对应稳定诊断，不抛异常；
- 包损坏、路径非法、源不存在、扩展名不符、超限等包或路径问题返回 **HTTP 422**；
- 预检不得在标准库中新增任何条目或目录。

### 4.4 确认导入

- 确认只消费预检快照字节，不重新读取源路径：源文件在预检后被替换、删除或改动都不影响结果；
- 确认在仓储写入锁下**重新检查**身份与名称冲突。预检之后库状态发生变化（新增同身份或同名）时
  以 409 拒绝，要求重新预检；
- 保留包内整数版本，**不重编号、不覆盖旧版**，也不要求导入版本高于库内最高版本：
  相同 `standard_id + version` 拒绝，尚不存在的较早版本允许导入；
- 该 ID 的名称沿用包内名称；导入不改写包内名称，冲突时提示修改原始标准并重新生成包；
- 同一凭证重复确认返回**相同成功结果**，不二次写入（短期幂等回执）；
- 过期凭证返回 410，未知/伪造/重启后失效的凭证返回 404，一律要求重新预检；
- 取消（`DELETE /api/standards/import-previews/{preview_id}`）后要求重新预检；
- 复制中断或发布故障不得留下半个已发布版本。

### 4.5 导入与预检共用的门禁

预检与确认都必须执行：包安全读取、资产存在性与路径门禁（复用既有
`validate_package_asset_files` 与 PLAN-DM-040 Task 3 的受控资产门禁）、完整发布解析与
派生/命名发布门禁。预检通过不等于确认免检：确认阶段必须在锁内重跑。

## 5. 接口

### 5.1 标准库列表

`GET /api/standards` 返回条目，其中 `version` 为整数（已发布）或 `null`（草稿）。
排序与归集由前端按 §3.2 口径完成，接口本身只保证字段类型稳定。

### 5.2 预检

```http
POST /api/standards/import-previews
Content-Type: application/json

{ "path": "<本机 .dststandard 绝对路径>" }
```

### 5.3 确认与取消

```http
POST /api/standards/import
Content-Type: application/json

{ "preview_id": "<不透明凭证>" }
```

```http
DELETE /api/standards/import-previews/{preview_id}
```

### 5.4 导出

导出文件名固定为 `<standard_id>-v<n>.dststandard`。包内 `manifest.json` 的
`version` 仍是裸整数；`v` 前缀只出现在文件名与界面展示中。

## 6. 错误码与 HTTP 状态

| 错误码 | 状态 | 触发 |
| --- | --- | --- |
| `STANDARD_SCHEMA_VERSION_UNSUPPORTED` | 422 | 文档或包的 `schema_version` 不是 `2`（含残留 v1） |
| `STANDARD_VERSION_INVALID` | 422 | `version` 不是 `1..2147483647` 的 JSON 整数，或版本路径段非法 |
| `STANDARD_VERSION_EXISTS` | 409 | 同一 `standard_id + version` 已存在于官方或用户库 |
| `STANDARD_NAME_CONFLICT` | 409 | 不同 ID 的已发布标准归一化同名 |
| `STANDARD_VERSION_LIMIT_REACHED` | 409 | 该 ID 已占用 `2147483647`，无法再分配 |
| `STANDARD_PACKAGE_INVALID` / `STANDARD_ASSET_*` | 422 | 包结构、路径、资产或路径逃逸问题 |
| `STANDARD_IMPORT_SOURCE_INVALID` | 422 | 预检来源不是 `.dststandard` 文件 |
| `STANDARD_IMPORT_SOURCE_NOT_FOUND` | 422 | 预检来源不存在、不是文件或不可读（属§4.3 的“包或路径问题”） |
| `STANDARD_IMPORT_SOURCE_TOO_LARGE` | 422 | 压缩源文件超过 256 MiB |
| `STANDARD_IMPORT_COPY_FAILED` | 422 | 复制到限时快照失败（中断不留半成品） |
| `STANDARD_IMPORT_PREVIEW_NOT_FOUND` | 404 | 未知、伪造或重启后失效的凭证 |
| `STANDARD_IMPORT_PREVIEW_EXPIRED` | 410 | 凭证已超过 15 分钟有效期 |
| `STANDARD_LIBRARY_BUSY` | 409 | 标准库写入互斥锁等待超时（可重试；不得冒泡成 500） |
| `STANDARD_PUBLISH_FAILED` | 422 | 发布写入失败（身份目录非冲突类 IO 错误），草稿与资产已回滚 |
| `STANDARD_JSON_INVALID` | 422 | 已发布文档损坏（截断/非 UTF-8）而无法解析 |
| `STANDARD_VERSION_INVALID` | 422 | 同时用于：版本路径段/绑定身份非法（含位数超限）与草稿携带 `version` |

预检的冲突（`STANDARD_VERSION_EXISTS`、`STANDARD_NAME_CONFLICT`）在预检响应中以
`can_import=false` 与 `diagnostics` 呈现，状态为 200；同码在**确认**阶段以 409 返回。

上述新码随实施任务登记进 `interfaces/message_catalog.py`，并补齐中英文
`errors.*` 文案；文案键与占位符由既有交叉守护测试约束。

## 7. 安全边界与信任模型

### 7.1 预检的信任模型

预检端点与 PLAN-DM-040 已交付的 `POST /api/standards/drafts/{draft_id}/asset-files`
及 `from-dst` 同级：服务只监听 `127.0.0.1` 且**无鉴权**，因此任意本机进程都可以请求把
一个 `.dststandard` 文件复制进快照根。这不是新的信任边界缺口，但也**不是可以随意放大**的能力。

缓解措施（全部为强制项）：

- 扩展名白名单只允许 `.dststandard`；
- 单个压缩源文件不超过 256 MiB；
- 快照根与标准库、工程目录、工作区目录相互隔离，且不参与任何自动扫描；
- 凭证随机、不可猜测、15 分钟限时；
- 服务重启即失效；
- 过期与取消立即清理；
- 快照内容在导入前仍须过完整包安全读取与资产门禁。

### 7.2 其他不变式

- 只读打开工作区不得创建 `.dstmanager/`、修改 DST/DWG 或更新文件时间戳；
- DST 修改继续走 `DST -> XML DOM -> DST` 受控流程；
- 正式写入保留永久 before 快照并走既有锁、暂存、校验、发布日志与可回滚事务；
- 用户提供的任意文本不得直接拼接成 SCR、Shell 命令或文件路径操作。

## 8. 兼容性

- 旧 `schema_version: 1` 文档与包不进入新的导入与发布路径；按 §2.6 处置；
- 现存测试夹具、Demo 与本地开发数据（`.dst-manager-data/`）一并更新为 v2；本地数据不是
  分发数据，删除重建即可；
- 工程绑定字符串形态由 `<standard_id>@<三段版本>` 变为 `<standard_id>@<整数>`；已绑定工程
  若出现，必须按 §2.6 先暂停并修订迁移规则。

## 9. 验收

1. 无版本草稿可保存；携带 `version` 的草稿被拒；发布文档接受 `1`/`10`，拒绝 `0`、`-1`、
   `true`、`1.5`、`"1"`、`"1.0.0"`、超上限与 `schema_version: 1`。
2. 依赖 `min_version` 仍接受 `"1.2.0"`、拒绝 `1` 与 `"1"`，证明两个解析器已拆分。
3. 同一 ID 的多个整数版本并存；本机发布依次得到 `1`、`2`；已有官方 `3` 时下一版本为 `4`；
   并发发布得到不同版本；故障后草稿与资产完整。
4. 不同 ID 的规范化同名（全角、空白、大小写差异）在发布、预检与确认时均被阻止；
   草稿同名不阻断。
5. 先导入 `v3` 再导入缺失的 `v2` 可行；同 ID 同版本即使包文件名不同也被拒。
6. 预检在标准库零新增；损坏包、非法资产、源消失、超限文件给出稳定诊断。
7. 预检后源文件被替换或删除仍只导入快照字节；凭证重放返回原成功结果；伪造、过期、
   重启后失效的凭证按要求拒绝；取消、复制中断或发布故障不留半包。
8. 服务端不接受绕过预检的 `{path}` 导入。
9. 残留 `schema_version: 1` 目录在 `list()` 中被跳过，`get`/`get_document`/`read_package`
   返回 `STANDARD_SCHEMA_VERSION_UNSUPPORTED`（422）。

## 10. 非目标

- 在线标准仓库、自动下载或脱离 Manager 版本的更新通道；
- 包级数字签名与证书吊销；
- 旧三段版本与新整数版本之间的自动换算或双向兼容层；
- 导入时改写包内名称、重编号或自动挑选可用版本号；
- 在预检阶段写入标准库。

## 11. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-09-25 | 首次建立：整数版本身份、无版本草稿、按 ID 名称唯一门禁、服务端版本分配、`.dststandard` 限时快照预检与凭证确认导入，以及预检信任模型与缓解措施。 |
| 2026-09-25 | 随 PLAN-DM-041 Task 1–8 落地并转为 `accepted`：补充 §12 实施验证证据映射；真实桌面 G9 仍待执行。 |
| 2026-09-25 | 澄清 §3.1 的并发覆盖范围：进程内互斥保证请求级交错下的版本唯一与门禁复核，跨进程文件锁按 PLAN-DM-018 的单实例约束属纵深防御并写明升级条件。 |
| 2026-09-25 | 固定复核后修订：§2.5 明确版本路径段位数先于整数转换校验（超长数字串不得导致 500）；§4.2 明确服务启动时清空快照根；§6 登记导入来源/复制/凭证过期之外的 `STANDARD_LIBRARY_BUSY`、`STANDARD_PUBLISH_FAILED`、`STANDARD_JSON_INVALID` 与 `STANDARD_VERSION_INVALID`，并确认“源不存在”按 §4.3 返回 422。 |

## 12. 实施验证（PLAN-DM-041 Task 1–8）

| 契约点 | 承接与实测证据 |
| --- | --- |
| v2 文档格式与整数版本 | `tests/unit/test_drawing_standards.py`（接受 `1`/`10`；拒绝 `0`、`-1`、`True`、`1.5`、`"1"`、`"1.0.0"`、超上限、缺失与 `schema_version: 1`） |
| 无版本草稿 | 同上（草稿携带 `version` 即 422）；`tests/unit/test_standard_service.py`、`tests/integration/test_standard_api.py` 的草稿级保存用例 |
| 依赖三段版本与两个解析器 | `test_dependency_min_version_keeps_three_segment_string`（保留 `1.2.0`，拒绝 `1` 与 `"1"`） |
| 版本分配 `max+1` 与上限 | `tests/unit/test_standard_store.py`：递增版本、官方更高版延续为 4、`STANDARD_VERSION_LIMIT_REACHED`、并发两发布得到 `[1, 2]`、注入移动失败后草稿与资产不丢 |
| 名称唯一（NFKC + casefold） | 同文件：全角、首尾/连续空白、大小写与 `ẞ/ß` 四组归一冲突均 409；草稿不占名称；同 ID 跨版本改名允许 |
| 两步导入与限时快照 | `tests/unit/test_standard_import_previews.py`（扩展名白名单、256 MiB、复制失败不留半成品、凭证随机、过期/取消/重启失效、快照清理、幂等回执） |
| 预检与确认的 HTTP 契约 | `tests/integration/test_standard_api.py`：预检零新增、已有版本列表、`can_import=false` 冲突、源被替换/删除仍只消费快照、伪造凭证 404、取消后 404、确认前新增冲突 409、`{path}` 直接导入 422 |
| 端到端闭环 | 同文件 `test_standard_package_full_loop_from_draft_asset_to_next_version`：受控草稿资产 → 自动 `v1` → 导出 → 预检 → 另一数据根确认导入 → 按 ID 定位 → 较早空缺版本 2/3 可导入 → 同名不同 ID 阻断 → 再发布得到 `v4` |
| 发布失败回滚 | 同文件 `test_publish_failure_keeps_draft_and_does_not_reserve_version`：422 `STANDARD_PUBLISH_FAILED`，草稿与受控资产保留、无空版本目录 |

真实桌面（WebView2）的 G9 检查项见
[SPEC-DM-016 证据目录 §五](assets/SPEC-DM-016/README.md)；截至本规范接受时**尚未执行**，
执行前不得声明 G9 通过。
