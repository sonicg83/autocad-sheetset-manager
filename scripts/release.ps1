# DST Manager 一键 release：前置校验 -> 测试门禁 -> 构建 -> 本地 tag（ARCH-DM-002 §5）。
# tag 是最后一步，保证"有 tag 必有可用 zip"；push 与 zip 分发由人工执行。
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# 1. 前置校验（任一不过即中止，不产生半成品）
if (git status --porcelain) { throw "工作区存在未提交改动，先提交或暂存后再 release" }
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -ne "main") { throw "必须在 main 分支执行 release（当前：$branch）" }
if (git tag -l "v$Version") { throw "tag v$Version 已存在" }
$pyproject = Get-Content (Join-Path $projectRoot "pyproject.toml") -Raw
if ($pyproject -notmatch "(?m)^version\s*=\s*`"$Version`"") {
    throw "pyproject.toml version 与 -Version $Version 不一致：请人工更新版本号后重试（脚本不做自动 bump）"
}
$changelog = Get-Content (Join-Path $projectRoot "changelog.md") -Raw
# 按章节标题正则匹配：避免 v0.3.3 误命中 v0.3.30 记录，且对版本号做正则转义
if ($changelog -notmatch "(?m)^## .*v$([regex]::Escape($Version))\b") {
    throw "changelog.md 缺少 v$Version 章节标题：先按仓库约定补齐变更记录"
}

# 2. 测试门禁（真实 CAD 系统测试按约定另行显式启用，不在 release 门禁内）
$env:UV_LINK_MODE = "copy"
uv sync --dev
if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }
uv run ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff 未通过" }
uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest 未通过" }

# 3. 构建
& (Join-Path $PSScriptRoot "build_release.ps1") -Version $Version
if ($LASTEXITCODE -ne 0) { throw "构建失败" }

# 4. 收尾：本地 annotated tag（不 push）
$zip = Join-Path $projectRoot "dist\releases\dst-manager-v$Version-win64.zip"
if (-not (Test-Path -LiteralPath $zip)) { throw "未找到分发包：$zip" }
git tag -a "v$Version" -m "release v$Version"
Write-Host "release v$Version 完成：$zip"
Write-Host "tag v$Version 仅保存在本地；推送与 zip 分发由人工执行。"
