"""DST Builder 运行期路径解析与应用身份：统一源码树与 PyInstaller frozen 态定位。

与 DST Manager 的对应实现（``dst_manager.runtime``）模式相同但完全独立：
Builder 使用 ``dst-builder`` 应用命名空间，不 import Manager 任何模块。
打包资源（builder-web/dist、builder_alembic.ini、builder_migrations/）在开发态
位于仓库根，frozen onedir 态位于 ``sys._MEIPASS``（PyInstaller ≥6 默认
contents_directory=``_internal``）。消费方：persistence/database.py 迁移定位、
interfaces/shell.py 前端静态挂载（PLAN-DB-001 Task 11）。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# 应用身份（Task 11）：与 DST Manager（dst-manager / "DST Manager"）互异的独立命名空间。
APP_ID = "dst-builder"
APP_TITLE = "DST Builder"
APP_DATA_DIR_NAME = "dst-builder"

# src/dst_builder/runtime.py -> parents[2] = 仓库根（builder_alembic.ini 所在层）
_DEV_ROOT = Path(__file__).resolve().parents[2]

# console=False 后无窗命令的日志文件名：Builder 壳进程无 Worker 子进程
# （CAD 由构建编排线程拉起 Core Console），只有 desktop 一个无窗入口。
_WINDOWLESS_LOG_NAMES = {"desktop": "dst-builder.log"}


def is_frozen() -> bool:
    """PyInstaller 冻结进程会设置 sys.frozen；开发态恒为 False。"""
    return getattr(sys, "frozen", False)


def resource_dir(base: Path | None = None) -> Path:
    """返回打包资源基准目录。base 仅供测试注入，生产代码不得传参。"""
    if base is not None:
        return base
    if is_frozen():
        return Path(sys._MEIPASS)
    return _DEV_ROOT


def app_data_dir(base: Path | None = None) -> Path:
    """应用数据目录：``%LOCALAPPDATA%/dst-builder``（与 Manager 的 dst-manager 同根不同名）。

    用户维度隔离；``base`` 仅供测试注入。
    """
    if base is not None:
        return base
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / APP_DATA_DIR_NAME


def log_dir(base: Path | None = None) -> Path:
    """返回日志目录（frozen 态 %LOCALAPPDATA%/dst-builder/logs，与数据目录同根）。

    开发态日志仍走终端，本函数仅 frozen 态被消费；base 仅供测试注入。
    """
    return app_data_dir(base) / "logs"


def _stdio_usable(stream: object) -> bool:
    """windowed 态 PyInstaller 注入 NullWriter（无 fileno）或 None；控制台与重定向句柄真实可用。"""
    if stream is None or type(stream).__name__ == "NullWriter":
        return False
    try:
        stream.fileno()  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        return False
    return True


def redirect_frozen_stdio(command: str, base: Path | None = None) -> bool:
    """console=False 的无窗命令（desktop）把 stdout/stderr 追加重定向到日志文件。

    仅在标准流不可用（双击启动无终端）时生效：从控制台手工运行 exe 时输出
    保持原样可见。写日志失败时静默放弃，不阻断启动。返回是否发生了重定向。
    """
    if not is_frozen():
        return False
    name = _WINDOWLESS_LOG_NAMES.get(command)
    if name is None:
        return False
    if _stdio_usable(sys.stdout) and _stdio_usable(sys.stderr):
        return False
    try:
        log_path = log_dir(base) / name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = log_path.open("a", encoding="utf-8", buffering=1)
        stream.write(
            f"\n===== {datetime.now().astimezone():%Y-%m-%d %H:%M:%S} "
            f"pid={os.getpid()} {command} =====\n"
        )
        if not _stdio_usable(sys.stdout):
            sys.stdout = stream
        if not _stdio_usable(sys.stderr):
            sys.stderr = stream
    except OSError:
        return False
    return True
