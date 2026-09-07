"""PyInstaller exe 入口（ARCH-DM-002 §3.2）。

frozen 态无参数 = 双击启动桌面壳（复用 cli 的 desktop 命令）；
`dst-manager.exe worker` / `doctor` 等子命令原样进入 Typer 解析。
console=False 后双击启动无终端：desktop/worker 的 stdout/stderr 在进入业务
代码（含 uvicorn 的日志接管）之前重定向到 %LOCALAPPDATA%/dst-manager/logs/
下的日志文件（ARCH-DM-002 §3.3）；从控制台运行时输出保持原样可见。
开发态入口不受影响（pyproject.toml `[project.scripts]` 定义的 `dst-manager` script 启动 cli）。
"""

import sys

if getattr(sys, "frozen", False):
    if len(sys.argv) == 1:
        sys.argv.append("desktop")  # 双击 exe = 打开桌面壳
    from dst_manager.runtime import redirect_frozen_stdio

    redirect_frozen_stdio(sys.argv[1])

from dst_manager.interfaces.cli import app

app()
