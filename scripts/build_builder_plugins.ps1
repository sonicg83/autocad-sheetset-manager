# Builder 插件双版本构建（PLAN-DB-001 Task 7；模式同 build_plugins.ps1）。
# 对 AutoCAD 2016 与 2020 分别构建 DstBuilder.AutoCAD.dll（x64、.NET Framework 4.8）。
# 缺少 AutoCAD 托管程序集时如实抛错退出，绝不产出占位 DLL。
[CmdletBinding()]
param(
    [string]$MSBuild = "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$project = Join-Path $projectRoot "plugins\src\DstBuilder.AutoCAD\DstBuilder.AutoCAD.csproj"
foreach ($version in @("2016", "2020")) {
    $autoCADDir = "C:\Program Files\Autodesk\AutoCAD $version"
    $output = Join-Path $projectRoot "plugins\builder\autocad$version"
    if (-not (Test-Path -LiteralPath (Join-Path $autoCADDir "AcCoreMgd.dll"))) {
        throw "缺少 AutoCAD $version 托管程序集：$autoCADDir"
    }
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    & $MSBuild $project /nologo /m /t:Rebuild /p:Configuration=Release "/p:AutoCADDir=$autoCADDir" "/p:OutputPath=$output\"
    if ($LASTEXITCODE -ne 0) { throw "AutoCAD $version Builder 插件构建失败" }
}
