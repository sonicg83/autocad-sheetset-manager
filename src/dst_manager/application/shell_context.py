"""可信桌面当前工作区登记（PLAN-DM-015 任务 2）。

壳桥的“打开所在文件夹/列偏好”方法只允许针对当前有效上下文操作：前端传入的
workspace_id 必须与这里登记的一致，路径一律从服务端 Workspace 取得，绝不接受
前端提供的任意路径或命令。同一时间仅一个有效上下文；关闭成功（clear）后
登记清空，迟到的旧 workspace_id 请求一律按 SHELL_WORKSPACE_UNAVAILABLE 拒绝。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceContext:
    """服务端登记的可信工作区上下文；路径来源唯一且由服务端持有。"""

    workspace_id: str
    root: Path
    dst_path: Path


class ShellContext:
    """线程安全的当前工作区登记表。

    - ``set_workspace(workspace)``：打开成功后以服务端 Workspace 登记当前上下文
      （workspace 需具备 ``id``/``root``/``dst_path`` 属性，即领域 Workspace）。
    - ``clear(expected_workspace_id)``：关闭时清除；期望 ID 不匹配或本无上下文
      时返回 False，防止迟到的旧关闭请求清掉新工作区上下文。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: WorkspaceContext | None = None

    def set_workspace(self, workspace) -> None:
        context = WorkspaceContext(
            workspace_id=workspace.id,
            root=Path(workspace.root),
            dst_path=Path(workspace.dst_path),
        )
        with self._lock:
            self._current = context

    def clear(self, expected_workspace_id: str | None = None) -> bool:
        with self._lock:
            if self._current is None:
                return False
            if expected_workspace_id is not None and self._current.workspace_id != expected_workspace_id:
                return False
            self._current = None
            return True

    @property
    def current(self) -> WorkspaceContext | None:
        with self._lock:
            return self._current
