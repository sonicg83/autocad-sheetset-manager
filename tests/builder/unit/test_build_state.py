"""构建状态机与构建事件契约（PLAN-DB-001 Task 2，SPEC-DB-001 §6）。

状态迁移表逐字转录 §6：

* 主链：DRAFT → REVISION_READY → PLANNED → QUEUED → PREPARING → BUILDING_DWG
  → BUILDING_DST → VERIFYING → PUBLISHING → SUCCEEDED；
* QUEUED|PREPARING|BUILDING_DWG|BUILDING_DST|VERIFYING → CANCELLED；
* 任一非终止状态 → FAILED；
* PUBLISHING 不响应取消；终止状态（SUCCEEDED/CANCELLED/FAILED）不可迁出。
"""

import itertools

import pytest

from dst_builder.domain.build_state import (
    BuildStatus,
    IllegalTransitionError,
    transition,
)
from dst_builder.domain.models import BuildEventV1

MAIN_CHAIN = (
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

CANCEL_ELIGIBLE = (
    BuildStatus.QUEUED,
    BuildStatus.PREPARING,
    BuildStatus.BUILDING_DWG,
    BuildStatus.BUILDING_DST,
    BuildStatus.VERIFYING,
)

TERMINAL = (BuildStatus.SUCCEEDED, BuildStatus.CANCELLED, BuildStatus.FAILED)


def allowed_targets(current: BuildStatus) -> set[BuildStatus]:
    """按 §6 转录的合法目标集合（测试侧独立推导，不引用实现表）。"""
    if current in TERMINAL:
        return set()
    targets = {BuildStatus.FAILED}
    chain_index = MAIN_CHAIN.index(current)
    if chain_index + 1 < len(MAIN_CHAIN):
        targets.add(MAIN_CHAIN[chain_index + 1])
    if current in CANCEL_ELIGIBLE:
        targets.add(BuildStatus.CANCELLED)
    return targets


def test_main_chain_walks_to_succeeded() -> None:
    for current, target in itertools.pairwise(MAIN_CHAIN):
        assert transition(current, target) is target


@pytest.mark.parametrize("current", CANCEL_ELIGIBLE)
def test_cancel_eligible_states_can_cancel(current: BuildStatus) -> None:
    assert transition(current, BuildStatus.CANCELLED) is BuildStatus.CANCELLED


def test_publishing_does_not_respond_to_cancel() -> None:
    """PUBLISHING 不响应取消，避免原子发布与用户取消竞态（§6）。"""
    with pytest.raises(IllegalTransitionError):
        transition(BuildStatus.PUBLISHING, BuildStatus.CANCELLED)


@pytest.mark.parametrize("current", [status for status in BuildStatus if status not in TERMINAL])
def test_any_non_terminal_state_can_fail(current: BuildStatus) -> None:
    assert transition(current, BuildStatus.FAILED) is BuildStatus.FAILED


@pytest.mark.parametrize("current", TERMINAL)
@pytest.mark.parametrize("target", list(BuildStatus))
def test_terminal_states_cannot_transition(current: BuildStatus, target: BuildStatus) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BuildStatus.DRAFT, BuildStatus.PLANNED),
        (BuildStatus.DRAFT, BuildStatus.QUEUED),
        (BuildStatus.REVISION_READY, BuildStatus.QUEUED),
        (BuildStatus.PLANNED, BuildStatus.PREPARING),
        (BuildStatus.QUEUED, BuildStatus.BUILDING_DWG),
        (BuildStatus.PREPARING, BuildStatus.BUILDING_DST),
        (BuildStatus.BUILDING_DWG, BuildStatus.VERIFYING),
        (BuildStatus.BUILDING_DST, BuildStatus.PUBLISHING),
        (BuildStatus.VERIFYING, BuildStatus.SUCCEEDED),
        (BuildStatus.BUILDING_DWG, BuildStatus.PREPARING),
        (BuildStatus.SUCCEEDED, BuildStatus.QUEUED),
        (BuildStatus.CANCELLED, BuildStatus.PUBLISHING),
    ],
)
def test_skipping_and_backward_transitions_rejected(
    current: BuildStatus, target: BuildStatus
) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(current, target)


@pytest.mark.parametrize("current", list(BuildStatus))
@pytest.mark.parametrize("target", list(BuildStatus))
def test_every_transition_outside_spec_table_is_rejected(
    current: BuildStatus, target: BuildStatus
) -> None:
    """穷举：凡不在 §6 表内的迁移一律拒绝；表内迁移一律放行。"""
    if target in allowed_targets(current):
        assert transition(current, target) is target
    else:
        with pytest.raises(IllegalTransitionError):
            transition(current, target)


def test_illegal_transition_error_reports_states() -> None:
    with pytest.raises(IllegalTransitionError) as excinfo:
        transition(BuildStatus.PUBLISHING, BuildStatus.CANCELLED)
    assert "PUBLISHING" in str(excinfo.value)
    assert "CANCELLED" in str(excinfo.value)


# ---------------------------------------------------------------------------
# BuildEventV1（§6）
# ---------------------------------------------------------------------------


def test_build_event_example_round_trips() -> None:
    event = BuildEventV1(
        schema_version=1,
        sequence=1,
        status=BuildStatus.BUILDING_DWG,
        progress=40,
        message_key="build.dwg.started",
        artifact_path="drawings/A-001 首层平面图.dwg",
        error_code=None,
        created_at="2026-09-17T08:00:00Z",
    )
    assert event.schema_version == 1
    assert event.status is BuildStatus.BUILDING_DWG
    assert event.artifact_path == "drawings/A-001 首层平面图.dwg"


@pytest.mark.parametrize("sequence", [0, -1])
def test_build_event_sequence_must_be_positive(sequence: int) -> None:
    with pytest.raises(ValueError):
        BuildEventV1(
            schema_version=1,
            sequence=sequence,
            status=BuildStatus.QUEUED,
            progress=0,
            message_key="build.queued",
        )


@pytest.mark.parametrize("progress", [-1, 101])
def test_build_event_progress_must_be_within_0_100(progress: int) -> None:
    with pytest.raises(ValueError):
        BuildEventV1(
            schema_version=1,
            sequence=1,
            status=BuildStatus.BUILDING_DWG,
            progress=progress,
            message_key="build.dwg.started",
        )
