# DST 转 XML 脚本
# 复用仓库内 DstCodec（固定 256 项查找表）把 AutoCAD 图纸集 .dst 解码为 XML。
# 输出是解码后的原始 XML 字节（与 DST 字节一一置换），不经格式化或 DOM 重写。
#
# 用法示例：
#   .\scripts\dst-to-xml.ps1 -Path C:\data\图纸集.dst
#   .\scripts\dst-to-xml.ps1 -Path C:\data\*.dst -OutputDir C:\data\xml
#   .\scripts\dst-to-xml.ps1 -Path C:\data\project -OutputDir C:\data\xml

[CmdletBinding()]
param(
    # 一个或多个 DST 文件；传入目录时递归收集其中的 *.dst。
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$Path,

    # 可选输出目录；缺省时 XML 与源 DST 同目录、同名（仅扩展名不同）。
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

# OneDrive 目录建议使用 copy 链接模式，避免 uv 同步冲突。
if (-not $env:UV_LINK_MODE) { $env:UV_LINK_MODE = "copy" }

# 收集待转换文件；目录输入时记录相对路径，便于在 OutputDir 下保留原目录结构。
$jobs = @()
foreach ($p in $Path) {
    if (Test-Path -LiteralPath $p -PathType Container) {
        $root = (Resolve-Path -LiteralPath $p).Path
        if ($root.EndsWith("\")) { $root = $root.TrimEnd("\") }
        Get-ChildItem -LiteralPath $p -Recurse -Filter *.dst -File | ForEach-Object {
            $jobs += @{
                Dst = $_.FullName
                Rel = $_.FullName.Substring($root.Length).TrimStart("\")
            }
        }
    } elseif (Test-Path -LiteralPath $p -PathType Leaf) {
        $jobs += @{
            Dst = (Resolve-Path -LiteralPath $p).Path
            Rel = Split-Path -Leaf $p
        }
    } else {
        throw "输入路径不存在：$p"
    }
}

if (-not $jobs) {
    Write-Host "未找到任何 .dst 文件。"
    return
}

# 内联 Python：读取 DST，用 DstCodec 解码为原始 XML 字节后写出。
$code = "import sys;from pathlib import Path;from dst_manager.infrastructure.dst_codec import DstCodec;Path(sys.argv[2]).write_bytes(DstCodec().decode_file(Path(sys.argv[1])))"

Push-Location $projectRoot
try {
    foreach ($job in $jobs) {
        $xmlPath = if ($OutputDir) {
            Join-Path $OutputDir ([IO.Path]::ChangeExtension($job.Rel, ".xml"))
        } else {
            [IO.Path]::ChangeExtension($job.Dst, ".xml")
        }
        $outParent = Split-Path -Parent $xmlPath
        if ($outParent) { New-Item -ItemType Directory -Force -Path $outParent | Out-Null }

        Write-Host "转换：$($job.Dst) -> $xmlPath"
        & uv run python -c $code $job.Dst $xmlPath
        if ($LASTEXITCODE -ne 0) { throw "转换失败：$($job.Dst)" }
    }
} finally {
    Pop-Location
}
Write-Host "完成：共转换 $($jobs.Count) 个 DST 文件。"