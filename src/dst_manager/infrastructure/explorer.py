"""Windows 文件资源管理器适配（PLAN-DM-015 任务 2）。

以结构化 argv（``shell=False``，无 shell=True / cmd /c）调用 explorer，在目录中
尽量选中目标文件，或直接打开已验证目录；绝不把用户文本拼接成命令行——目标路径
一律由服务端可信上下文提供。非 Windows 平台抛 ``ExplorerUnsupportedError``
（壳桥映射为 SHELL_OPEN_FAILED）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class ExplorerError(Exception):
    """资源管理器调用失败（壳桥映射为 SHELL_OPEN_FAILED）。"""


class ExplorerUnsupportedError(ExplorerError):
    """当前平台无 Windows 文件资源管理器。"""


class Explorer:
    """真实资源管理器适配；测试可用仅记录参数的 fake 替换。"""

    def open_folder_and_select(self, file: Path) -> None:
        """在资源管理器中打开 file 所在目录并选中该文件。

        explorer 的 ``/select,<path>`` 须作为单个 argv 元素经 ``shell=False`` 传入，
        路径含空格/中文无需额外转义；调用前由壳桥校验文件确实存在。
        """
        if sys.platform != "win32":
            raise ExplorerUnsupportedError("当前平台不支持打开文件资源管理器")
        try:
            subprocess.Popen(["explorer", f"/select,{file}"])
        except OSError as exc:
            raise ExplorerError(f"无法启动文件资源管理器：{exc}") from exc

    def open_folder(self, folder: Path) -> None:
        """直接打开目录；调用前由壳桥校验目录确实存在。"""
        if sys.platform != "win32":
            raise ExplorerUnsupportedError("当前平台不支持打开文件资源管理器")
        try:
            subprocess.Popen(["explorer", str(folder)])
        except OSError as exc:
            raise ExplorerError(f"无法启动文件资源管理器：{exc}") from exc
