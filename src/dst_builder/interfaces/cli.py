"""DST Builder 独立命令行入口，不复用 Manager 的应用工厂。"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="DST Builder 最小生成闭环命令行")

_PROJECT_NAME = "autocad-sheetset"

# AGENTS.md：Web 服务只允许监听 127.0.0.1；Builder 使用与 Manager（8000）不同的端口。
_BUILDER_HOST = "127.0.0.1"
_BUILDER_PORT_DEFAULT = 8100


def _version_callback(value: bool) -> None:
    if value:
        try:
            typer.echo(_package_version(_PROJECT_NAME))
        except PackageNotFoundError:
            typer.echo("0.0.0.dev0")
        raise typer.Exit


@app.callback()
def main(
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="打印 DST Builder 版本号并退出。",
    ),
) -> None:
    """DST Builder 命令行。"""


@app.command("serve")
def serve(
    project: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Builder 项目根目录（project.dstb 所在目录）。",
        ),
    ],
    port: Annotated[int, typer.Option(help="HTTP 端口。")] = _BUILDER_PORT_DEFAULT,
) -> None:
    """启动仅监听 127.0.0.1 的 Builder Web API。"""
    import uvicorn

    from dst_builder.interfaces.api import create_builder_app

    uvicorn.run(
        create_builder_app(project_root=project),
        host=_BUILDER_HOST,
        port=port,
        log_level="info",
    )
