"""DST Builder 独立命令行入口，不复用 Manager 的应用工厂。"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

import typer

app = typer.Typer(help="DST Builder 最小生成闭环命令行")

_PROJECT_NAME = "autocad-sheetset"


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
