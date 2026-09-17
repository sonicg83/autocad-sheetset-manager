"""PyInstaller exe 入口：DST Builder 绿色分发包（PLAN-DB-001 Task 11）。

frozen 态无参数 = 双击启动桌面壳（run_desktop）；带参数时进入 Typer CLI
（`dst-builder.exe serve --project ...` 等子命令原样解析）。
console=False 后双击启动无终端：desktop 的 stdout/stderr 在进入业务代码
（含 uvicorn 的日志接管、webview 导入）之前重定向到
%LOCALAPPDATA%/dst-builder/logs/dst-builder.log；从控制台运行时输出保持原样可见。
开发态入口不受影响（pyproject.toml `[project.scripts]` 定义的 `dst-builder`
script 启动 cli）。
"""

import sys

if getattr(sys, "frozen", False):
    # 必须先于 shell/cli 导入：uvicorn 在导入期接管日志、pywebview 导入重量级
    # 依赖，之后重定向会丢失启动期输出。
    from dst_builder.runtime import redirect_frozen_stdio

    redirect_frozen_stdio("desktop")

if len(sys.argv) == 1:
    from dst_builder.interfaces.shell import run_desktop

    run_desktop()
else:
    from dst_builder.interfaces.cli import app

    app()
