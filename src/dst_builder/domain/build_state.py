"""构建状态机（SPEC-DB-001 §6）：唯一允许的状态迁移表与纯函数迁移入口。

状态只允许下列迁移（任何其他组合都是编程错误，抛出
:class:`IllegalTransitionError`）：

* 主链 ``DRAFT → REVISION_READY → PLANNED → QUEUED → PREPARING
  → BUILDING_DWG → BUILDING_DST → VERIFYING → PUBLISHING → SUCCEEDED``；
* ``QUEUED|PREPARING|BUILDING_DWG|BUILDING_DST|VERIFYING → CANCELLED``；
* 任一非终止构建状态 ``→ FAILED``；
* ``PUBLISHING`` 不响应取消，避免原子发布与用户取消竞态。
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["BuildStatus", "IllegalTransitionError", "transition"]


class BuildStatus(StrEnum):
    DRAFT = "DRAFT"
    REVISION_READY = "REVISION_READY"
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    BUILDING_DWG = "BUILDING_DWG"
    BUILDING_DST = "BUILDING_DST"
    VERIFYING = "VERIFYING"
    PUBLISHING = "PUBLISHING"
    SUCCEEDED = "SUCCEEDED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


_TERMINAL_STATUSES = frozenset(
    {BuildStatus.SUCCEEDED, BuildStatus.CANCELLED, BuildStatus.FAILED}
)

_CANCEL_ELIGIBLE = frozenset(
    {
        BuildStatus.QUEUED,
        BuildStatus.PREPARING,
        BuildStatus.BUILDING_DWG,
        BuildStatus.BUILDING_DST,
        BuildStatus.VERIFYING,
    }
)

_MAIN_CHAIN = (
    BuildStatus.DRAFT,
    BuildStatus.REVISION_READY,
    BuildStatus.PLANNED,
    BuildStatus.QUEUED,
    BuildStatus.PREPARING,
    BuildStatus.BUILDING_DWG,
    BuildStatus.BUILDING_DST,
    BuildStatus.VERIFYING,
    BuildStatus.PUBLISHING,
    BuildStatus.SUCCEEDED,
)

_ALLOWED_TRANSITIONS: dict[BuildStatus, frozenset[BuildStatus]] = {}
for _index, _current in enumerate(_MAIN_CHAIN[:-1]):
    _targets = {_MAIN_CHAIN[_index + 1], BuildStatus.FAILED}
    if _current in _CANCEL_ELIGIBLE:
        _targets.add(BuildStatus.CANCELLED)
    _ALLOWED_TRANSITIONS[_current] = frozenset(_targets)
for _terminal in _TERMINAL_STATUSES:
    _ALLOWED_TRANSITIONS[_terminal] = frozenset()


class IllegalTransitionError(ValueError):
    """不在 §6 迁移表内的状态迁移。"""


def transition(current: BuildStatus, target: BuildStatus) -> BuildStatus:
    """按 §6 迁移表校验并返回目标状态；非法组合抛出 :class:`IllegalTransitionError`。"""
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise IllegalTransitionError(
            f"非法构建状态迁移：{current.value} → {target.value}"
        )
    return target
