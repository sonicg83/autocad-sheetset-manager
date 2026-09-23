"""新项目发布事务的对外值类型、稳定错误与故障注入点（PLAN-DM-036 Task 6）。

与 :mod:`dst_manager.infrastructure.filesystem.publish_errors`（工作区发布事务的
异常）同层并列：这里只放创建事务的**契约**，不放流程逻辑，因此发布实现
（``project_publisher``）、创建运行器与应用层可以共用同一份形状而不互相依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dst_manager.infrastructure.filesystem import publish_recovery

__all__ = [
    "ProjectPublishError",
    "ProjectPublishFaultInjector",
    "PublishedFile",
    "PublishedProject",
]


class ProjectPublishError(RuntimeError):
    """新项目发布失败：``code`` 是稳定错误码，``outcome`` 是事务现场结论。

    ``outcome`` 取值：

    - ``ABORTED``：未产生任何目标侧副作用（预检拒绝），可直接重试；
    - ``ROLLED_BACK``：本次已提交文件已按身份回滚，目标恢复到发布前状态；
    - ``NEEDS_REVIEW``：无法自动恢复（外部内容或身份不匹配），必须人工核对。
    """

    def __init__(self, code: str, detail: str, outcome: str = "ABORTED") -> None:
        self.code = code
        self.outcome = outcome
        super().__init__(f"{code}: {detail}")


class ProjectPublishFaultInjector(Protocol):
    """发布事务故障注入点（显式参数；生产路径不注入）。

    ``at_stage`` 在写入 ``PREPARED``/``PUBLISHING`` 日志后调用，``after_commit``
    在每个文件提交完成后调用。测试用 ``BaseException`` 模拟进程中断（不触发回滚，
    只留持久日志现场），用 ``ProjectPublishError`` 模拟提交失败（触发回滚）。
    """

    def at_stage(self, stage: str) -> None: ...

    def after_commit(self, target: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class PublishedFile:
    """一个已提交的成果文件（目标目录内的最终名字与内容身份）。"""

    name: str
    role: str
    group_id: str
    target: Path
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class PublishedProject:
    """一次成功的新项目发布：成果文件、目标原状态与事务证据位置。"""

    job_id: str
    attempt: int
    target_dir: Path
    dst_path: Path
    target_state: str
    files: tuple[PublishedFile, ...]
    journal_path: Path
    revision_dir: Path
    journal: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """任务闭环与启动恢复共用的成果投影（与恢复侧同一实现，不复制形状）。"""
        return publish_recovery.creation_published_payload(self.journal)
