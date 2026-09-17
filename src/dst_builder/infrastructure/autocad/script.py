"""固定结构 SCR 生成器（SPEC-DB-001 §7）。

SCR 只含固定命令行与两条基础设施路径占位（Builder 插件 DLL、请求 JSON）；
用户文本、布局名和工程路径没有任何进入 SCR 的通道——插件从 attempt 目录中
的版本化 JSON 请求读取结构化数据。路径参数含控制字符、引号或为空时拒绝
渲染（``SCR_ARGUMENT_UNSAFE``），杜绝经路径注入 SCR 指令。
"""

from __future__ import annotations

from dst_builder.domain.models import WORKER_COMMAND_NAME

__all__ = ["render_worker_scr"]


def _scr_path_argument(value: str) -> str:
    if not value or any(ord(character) < 32 or ord(character) == 127 or character == '"' for character in value):
        raise ValueError("SCR_ARGUMENT_UNSAFE")
    return f'"{value}"'


def render_worker_scr(plugin: str, request_json: str) -> str:
    """渲染加载 Builder 插件并执行唯一命令 ``DSTBUILDER_CREATE_DRAWING`` 的 SCR。

    命令提示输入请求 JSON 路径（下一行占位）；``QSAVE``/``QUIT`` 固定收尾。
    """
    lines = [
        "FILEDIA",
        "0",
        "SECURELOAD",
        "0",
        "CMDECHO",
        "0",
        "_.NETLOAD",
        _scr_path_argument(plugin),
        WORKER_COMMAND_NAME,
        _scr_path_argument(request_json),
        "_.QSAVE",
        "_.QUIT",
    ]
    return "\n".join(lines) + "\n"
