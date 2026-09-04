"""PyInstaller exe 入口（ARCH-DM-002 §3.2）。

frozen 态无参数 = 双击启动桌面壳（复用 cli 的 desktop 命令）；
`dst-manager.exe worker` / `doctor` 等子命令原样进入 Typer 解析。
开发态不受影响（main.py 仍是 `dst-manager` script 入口）。
"""

import sys

if getattr(sys, "frozen", False) and len(sys.argv) == 1:
    sys.argv.append("desktop")

from dst_manager.interfaces.cli import app

app()
