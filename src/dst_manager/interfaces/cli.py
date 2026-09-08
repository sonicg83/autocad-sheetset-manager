import json
import os
import time
from pathlib import Path
from typing import Annotated

import typer

from dst_manager.application.service import DstManagerService
from dst_manager.interfaces.serialization import workspace_json

app = typer.Typer(help="DST Manager MVP 命令行")


def _worker_summary(result: dict, elapsed_ms: int) -> dict:
    files = result.get("files") or []
    return {
        "job_id": result.get("id"),
        "status": result.get("status"),
        "attempt": result.get("attempt"),
        "dwg_succeeded": sum(item.get("status") == "SUCCEEDED" for item in files),
        "dwg_failed": sum(item.get("status") == "FAILED" for item in files),
        "duration_ms": elapsed_ms,
        "error_code": result.get("error_code"),
    }


@app.command("serve")
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    run_id: Annotated[str, typer.Option(hidden=True)] = "",
    project_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
):
    """启动仅监听本机的Web API。"""
    if host != "127.0.0.1":
        raise typer.BadParameter("MVP只允许监听127.0.0.1")
    if project_root is not None and project_root.resolve() != Path.cwd().resolve():
        raise typer.BadParameter("project_root与当前工作目录不一致")
    if run_id:
        os.environ["DST_MANAGER_RUN_ID"] = run_id
    import uvicorn
    uvicorn.run("dst_manager.interfaces.api:app", host=host, port=port)


@app.command("desktop")
def desktop() -> None:
    """启动桌面壳（WebView2）窗口。"""
    from .shell import run_desktop

    run_desktop()


@app.command("open")
def open_workspace(dst_path: Path):
    """只读打开并输出结构报告。"""
    result = DstManagerService().open_workspace(dst_path)
    typer.echo(json.dumps(workspace_json(result), ensure_ascii=False, indent=2, default=str))


@app.command("doctor")
def doctor():
    """检查AutoCAD 2016/2020显式配置。"""
    payload = json.dumps(DstManagerService().capabilities(), ensure_ascii=False, indent=2)
    from ..runtime import is_frozen, log_dir

    if is_frozen():
        # console=False 下双击/图形环境无终端可看：自检结果同时落盘，便于排障与反馈
        report = log_dir() / "doctor-last.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"自检结果已写入 {report}")
    typer.echo(payload)


@app.command("worker")
def worker(
    once: bool = typer.Option(False, help="没有任务时立即退出"),
    run_id: Annotated[str, typer.Option(hidden=True)] = "",
    project_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
):
    """运行同机CAD Worker；默认持续轮询SQLite任务队列。"""
    if project_root is not None and project_root.resolve() != Path.cwd().resolve():
        raise typer.BadParameter("project_root与当前工作目录不一致")
    if run_id:
        os.environ["DST_MANAGER_RUN_ID"] = run_id
    # ARCH-DM-004 §2.4：Worker 注入运行时设置，每任务认领前检测并应用配置变化
    from dst_manager.settings.runtime import RuntimeSettings, default_store

    service = DstManagerService(runtime_settings=RuntimeSettings(default_store()))
    while True:
        started = time.perf_counter()
        result = service.run_next_job()
        if result is not None:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            typer.echo(json.dumps(_worker_summary(result, elapsed_ms), ensure_ascii=False, separators=(",", ":")))
        elif once:
            return
        else:
            time.sleep(1)


if __name__ == "__main__":
    app()
