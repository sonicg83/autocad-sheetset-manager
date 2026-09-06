---
id: ARCH-DM-003
title: 版本管理与发布流程（SemVer + rc 预发布 + GitHub Releases）
status: accepted
owners:
  - dst-manager
created: 2026-09-06
updated: 2026-09-06
related:
  - ARCH-DM-001
  - ARCH-DM-002
document_kind: architecture
---

# 版本管理与发布流程（SemVer + rc 预发布 + GitHub Releases）

> 状态：已接受（2026-09-06 用户确认）
> 定位：DST Manager 脱离 MVP、进入对外公开发布阶段后的版本管理与发布流程权威设计；接手 ARCH-DM-002 §1.2 明确列为范围外的"CI 自动构建与远程 Release 发布"。
> 原则：版本号唯一权威、tag 驱动发布、发布前必经 rc 真实业务验证、任何发布产物可追溯到 commit。

## 1. 目标与边界

### 1.1 目标

- 对外公开（GitHub 公开仓库）后的版本号承诺：用户可以依据版本号判断兼容性与升级风险。
- 发布安全：DST/DWG 业务数据不可损，正式发布前必须经 rc 预发布版本在真实业务中验证。
- 发布可复现：产物由 CI 在干净环境构建，不依赖单人本机状态；每次发布与 commit 一一对应。

### 1.2 范围外（YAGNI）

代码签名、安装向导、自动更新、多平台构建、nightly 构建、依赖自动升级机器人（Dependabot/Renovate）、GitHub 环境保护规则与多维护者评审流程。后续需要时另行立项。

## 2. 版本号规则（SemVer）

- 格式 `主.次.修订`，权威来源为 `pyproject.toml` 的 `version` 字段，全仓库不允许出现第二处版本常量。
- 0.x 阶段：次版本号可包含破坏性变更（SemVer 0.x 惯例），修订号只承载缺陷修复。
- 升 `1.0.0` 的时机由维护者裁决：业务可用性稳定、对外承诺接口（CLI 命令、HTTP API、DST 产物兼容性）不再随意破坏时。本文档不做时间承诺。
- Git tag 格式 `v<版本>`（如 `v0.4.0`）；预发布 tag `v<版本>-rc.<n>`（如 `v1.0.0-rc.1`）。tag 去 `v` 后必须与 `pyproject.toml` 完全一致，CI 在发布流水线第一步校验，不一致即失败。
- 同一版本号的 rc 与正式版指向同一业务内容：正式 tag 发布时以正式产物覆盖 rc 产物；rc 之间以 rc 序号区分，不修改已发布 tag。

## 3. 分支策略

- 长期分支只有 `main`；功能开发走短生命周期 `feature/*` 分支（沿用现状，合入即删除）。
- 不设 `develop`、`release/*` 分支。rc 阶段的缺陷修复直接进 `main`，随后打下一个 rc 序号 tag。
- 发布后线上出现严重缺陷：从对应 tag 拉 `hotfix/vX.Y.Z` 分支修复，升修订号发布，修复合回 `main` 后删除分支。
- tag 是发布锚点，一经推送不删除、不移动；发布内容有问题就用新版本号重新发布。

## 4. changelog 与 Release notes

- 日常开发继续按日期章节追加变更记录（AGENTS.md 现行规则不变）；发布时把该版本覆盖的日期条目归纳为 `## <标题>（vX.Y.Z，YYYY-MM-DD）` 版本章节置于文件顶部。现有 `scripts/release.ps1` 已强制校验该章节存在。
- `release.yml` 从 changelog 提取当前版本章节作为 GitHub Release 正文，不维护第二份发布说明。
- 归纳入版本章节时执行一次"公开化"修订：剔除内部事项（PLAN/SPEC 编号、内部裁决细节、未公开计划的引用），只保留对用户有意义的变更。该修订只改版本章节，不改写历史日期章节。

## 5. 发布渠道与产物

- 发布渠道为 GitHub Releases（`sonicg83/autocad-sheetset`）。自建 origin（Gitea）只做同步备份，不承载发布。
- 产物沿用 ARCH-DM-002：`dst-manager-v<版本>-win64.zip`（PyInstaller onedir，内含 web/dist 与 alembic 迁移文件），随包携带 2016/2020 双版本 Worker 插件 DLL。
- 预发布 tag（含 `-rc`）创建的 GitHub Release 自动标记为 pre-release。

## 6. CI 流水线（GitHub Actions）

### 6.1 `ci.yml` — 合入门禁

触发：PR 与 push 到 `main`。运行环境：windows runner。

- Python：`uv sync --dev` → Ruff → pytest（私有样本缺失时 CAD 用例按既有约定自动跳过）→ `uv lock --check`。
- Web：`npm ci` → 生产构建（vue-tsc + vite）。
- Playwright e2e 不进门禁，仍在本地执行（避免开发服务器负载抖动类用例拖慢 CI）。

### 6.2 `release.yml` — tag 触发发布

触发：推送 `v*` tag。运行环境：windows runner，顺序执行：

1. 校验 tag 与 `pyproject.toml` 版本一致；
2. 全量验证（与 §6.1 门禁相同口径）；
3. 复用 `scripts/build_release.ps1` 完成：web 构建 → `build_plugins.ps1` 双版本插件 → PyInstaller 打包 → 组装 `dst-manager-v<版本>-win64.zip`；
4. 创建 GitHub Release：正文取 changelog 对应版本章节，附件为分发包 zip；含 `-rc` 后缀标 pre-release。

降级预案：若双版本插件在 CI 环境构建反复失败，`release.yml` 以 `-SkipPlugins` 跳过插件步骤，Release 正文注明"插件 DLL 请经 `scripts/build_plugins.ps1` 本地构建"，人工补传附件。该降级须在 Release 正文可见，不得静默。

## 7. 发布操作流程（checklist）

1. 确认 `main` 工作区干净、CI 门禁通过；
2. 更新 `pyproject.toml` 版本号（脚本不自动 bump，沿用 `release.ps1` 约定）；
3. 归纳 changelog 版本章节并做公开化修订（§4）；
4. 提交升版与 changelog；
5. 本地运行 `scripts/release.ps1 -Version <版本>`：门禁校验 + 本地构建 + 创建本地 tag（保留 ARCH-DM-002"有 tag 必有可用 zip"原则，本地先验证产物）；
6. 在真实业务中使用本地产物验证（即 rc 验证；首次发布可直接以 `-rc.1` 后缀走本流程）；
7. 有缺陷：修复进 `main`，升 rc 序号或修订号，回到第 2 步；
8. 推送 tag 到 GitHub → `release.yml` 自动构建并创建 GitHub Release；
9. 核对 Release：产物可下载、版本正确、正文与 changelog 一致、无降级注记遗漏；
10. 同步 tag 与 `main` 到自建 origin。

## 8. 首个演练版本

- 下一版本 `v0.4.0` 按本流程首发，作为流程演练；通过后再决定 `1.0.0` 时机（§2）。
- 演练期间发现的流程缺陷直接修订本文档，不改版本号。

## 9. 与既有文档的关系

- ARCH-DM-002：打包形态（onedir + zip）、`packaging/dst-manager.spec`、`scripts/release.ps1` 与 `scripts/build_release.ps1` 全部沿用；本文档只新增版本号承诺、rc 渠道、CI 门禁与远程发布，未取代其任何决策。
- AGENTS.md：changelog 日常追加规则、commit message 规则、私有目录禁令继续生效；本文档 §4 的版本章节归纳是其发布时的补充动作。
