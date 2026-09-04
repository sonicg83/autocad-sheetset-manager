"""运行时路径解析：统一开发态（源码树）与 PyInstaller frozen 态（onedir）的资源定位。

打包资源（web/dist、alembic.ini、migrations/）在开发态位于仓库根，frozen onedir
态位于 `sys._MEIPASS`（PyInstaller ≥6 默认 contents_directory=`_internal`）。
三处消费方：api.py 静态挂载、database.py 迁移定位、shell.py Worker 拉起（ARCH-DM-002 §3.1）。
"""

import sys
from pathlib import Path

# src/dst_manager/runtime.py -> parents[2] = 仓库根（alembic.ini 所在层）
_DEV_ROOT = Path(__file__).resolve().parents[2]


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
