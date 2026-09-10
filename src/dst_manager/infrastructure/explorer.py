"""Windows 文件资源管理器适配（PLAN-DM-015 任务 2）。

以结构化 argv（``shell=False``，无 shell=True / cmd /c）调用 explorer，在目录中
尽量选中目标文件，或直接打开已验证目录；绝不把用户文本拼接成命令行——目标路径
一律由服务端可信上下文提供。非 Windows 平台抛 ``ExplorerUnsupportedError``
（壳桥映射为 SHELL_OPEN_FAILED）。

``/select`` 的引号位置是被实测钉住的契约（见 :func:`_select_command_line`）：
explorer 自行解析原始命令行，``/select`` 与路径被一起加引号时会退化为打开「文档」；
因此该分支显式给出原始命令行字符串，其余分支仍用 argv 列表。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class ExplorerError(Exception):
    """资源管理器调用失败（壳桥映射为 SHELL_OPEN_FAILED）。"""


class ExplorerUnsupportedError(ExplorerError):
    """当前平台无 Windows 文件资源管理器。"""


def _select_command_line(file: Path) -> str:
    r"""构造 ``explorer /select,"<path>"`` 原始命令行（shell=False，不经 shell）。

    explorer 不按 CRT 规则解析命令行，而是自行解析：``/select`` 开关必须留在引号
    外，只给路径部分加引号。若把 ``/select,<path>`` 整体加引号（Python
    ``subprocess.list2cmdline`` 在路径含空格时正是如此），explorer 会把它当作普通
    路径、解析失败后**回退打开用户的「文档」目录**。本机实测：
    ``explorer "/select,C:\...\project3 - 2\图纸集数据文件.dst"`` →
    ``file:///C:/Users/sonic/Documents``；改为 ``explorer /select,"..."`` 后正确
    打开所在目录并选中文件。路径无空格时同样走本函数，不按是否含空格分叉。

    路径来源只有服务端可信上下文（壳桥已校验存在），此处不引入 shell 解释；
    Windows 文件名不允许双引号，出现即拒绝而非转义，杜绝命令行逃逸。
    """
    target = str(file)
    if '"' in target:
        raise ExplorerError("路径包含无法安全传给文件资源管理器的字符（\"）")
    return f'explorer /select,"{target}"'


class Explorer:
    """真实资源管理器适配；测试可用仅记录参数的 fake 替换。"""

    def open_folder_and_select(self, file: Path) -> None:
        """在资源管理器中打开 file 所在目录并选中该文件。

        命令行由 :func:`_select_command_line` 按 explorer 的解析规则构造（开关在引号
        外、路径在引号内）；调用前由壳桥校验文件确实存在。
        """
        if sys.platform != "win32":
            raise ExplorerUnsupportedError("当前平台不支持打开文件资源管理器")
        command = _select_command_line(file)
        try:
            subprocess.Popen(command)
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
