# DST Builder 纯构建脚本：前端 -> Python 环境 -> 双版本插件 -> PyInstaller -> 分发 zip（PLAN-DB-001 Task 11）。
# 与 Manager 的 build_release.ps1 并列、互不影响：产物全部落在 dst-builder 命名空间。
# 不做任何 git 操作与门禁校验。
[CmdletBinding()]
param(
    # 分发 zip 的版本号；缺省从 pyproject.toml 读取
    [string]$Version = "",
    # 插件 DLL 已构建时跳过 MSBuild 重建
    [switch]$SkipPlugins
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

# 1. 前端构建（builder-web/dist 是 spec 的 datas 前置条件）
Push-Location (Join-Path $projectRoot "builder-web")
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
} finally {
    Pop-Location
}

# 2. Python 环境（pyinstaller 在 dev 组）
$env:UV_LINK_MODE = "copy"
uv sync --dev
if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }

# 3. 双版本 Builder 插件构建（plugins/builder/autocad{2016,2020}/DstBuilder.AutoCAD.dll）
if (-not $SkipPlugins) {
    & (Join-Path $PSScriptRoot "build_builder_plugins.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Builder 插件构建失败" }
}

# 4. PyInstaller onedir
uv run pyinstaller --noconfirm (Join-Path $projectRoot "packaging\dst-builder.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

# 5. 版本号
if (-not $Version) {
    $pyproject = Get-Content (Join-Path $projectRoot "pyproject.toml") -Raw
    if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw "无法从 pyproject.toml 读取版本号" }
    $Version = $Matches[1]
}

# 6. 组装：随包插件 DLL + zip
$appDir = Join-Path $projectRoot "dist\DSTBuilder"
foreach ($v in @("2016", "2020")) {
    $src = Join-Path $projectRoot "plugins\builder\autocad$v"
    if (-not (Test-Path -LiteralPath (Join-Path $src "DstBuilder.AutoCAD.dll"))) {
        throw "缺少 autocad$v Builder 插件 DLL：$src（先运行 build_builder_plugins.ps1）"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $appDir "autocad$v") -Recurse -Force
}
$releaseDir = Join-Path $projectRoot "dist\releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$zip = Join-Path $releaseDir "dst-builder-v$Version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $appDir "*") -DestinationPath $zip
Write-Host "分发包已生成：$zip"
