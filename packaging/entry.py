"""PyInstaller exe 入口（ARCH-DM-002 §3.2）。

frozen 态无参数 = 双击启动桌面壳（复用 cli 的 desktop 命令）；
`dst-manager.exe worker` / `doctor` 等子命令原样进入 Typer 解析。
开发态入口不受影响（pyproject.toml `[project.scripts]` 定义的 `dst-manager` script 启动 cli）。
"""

import sys

if getattr(sys, "frozen", False) and len(sys.argv) == 1:
    sys.argv.append("desktop")

from dst_manager.interfaces.cli import app

app()
