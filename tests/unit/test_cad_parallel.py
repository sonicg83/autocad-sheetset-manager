import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from dst_manager.application import cad_job
from dst_manager.application.cad_job import CadJobRunner, RebuildResult, RebuildWorkUnit
from dst_manager.config import Settings
from dst_manager.infrastructure.autocad.worker import CadCapability
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import RecoverablePublisher


class FakeDatabase:
    def update_job(self, *_args, **_kwargs):
        return None

    def heartbeat(self, *_args, **_kwargs):
        return True


def _unit(tmp_path: Path, index: int, cad_operation: str) -> RebuildWorkUnit:
    return RebuildWorkUnit(
        index,
        {"cad_operation": cad_operation},
        tmp_path / "source.dwg",
        tmp_path,
        tmp_path,
        tmp_path,
        10,
    )


def test_parallel_setting_defaults_to_four_and_rejects_out_of_range(tmp_path: Path):
    assert Settings(data_dir=tmp_path).cad_max_parallel == 4
    for value in (0, -1, 11):
        with pytest.raises(ValidationError):
            Settings(data_dir=tmp_path, cad_max_parallel=value)


@pytest.mark.parametrize("parallel", [1, 4, 10])
def test_runner_accepts_configured_parallel_range(tmp_path: Path, parallel: int):
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, parallel)

    assert runner.max_parallel == parallel


@pytest.mark.parametrize("parallel", [0, -1, 11])
def test_runner_rejects_out_of_range_parallelism(tmp_path: Path, parallel: int):
    with pytest.raises(ValueError, match="CAD_MAX_PARALLEL_OUT_OF_RANGE"):
        CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, parallel)


@pytest.mark.parametrize(("parallel", "expected"), [(1, 1), (4, 4), (10, 6)])
def test_mixed_group_scheduler_is_globally_bounded(tmp_path: Path, parallel: int, expected: int):
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, parallel)
    active = 0
    maximum = 0
    operations: list[str] = []
    lock = threading.Lock()

    def execute(_job, _workspace, _capability, unit):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            operations.append(unit.group["cad_operation"])
        time.sleep(0.005 * (6 - unit.index))
        with lock:
            active -= 1
        target = tmp_path / f"{unit.index}.dwg"
        return RebuildResult(unit.index, target, target, target, {}, 30, tmp_path / "x.log", 100, 200)

    runner._execute_group = execute
    units = [_unit(tmp_path, index, "rename_only" if index % 2 == 0 else "rebuild") for index in range(6)]
    results = runner._run_groups("job", "worker", object(), CadCapability("2020", None, None), units)
    assert [item.index for item in results] == list(range(6))
    assert maximum == expected
    assert set(operations) == {"rename_only", "rebuild"}


def test_failure_stops_submitting_new_groups(tmp_path: Path):
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, 2)
    started = []

    def execute(_job, _workspace, _capability, unit):
        started.append(unit.index)
        if unit.index == 0:
            raise RuntimeError("boom")
        time.sleep(0.05)
        target = tmp_path / f"{unit.index}.dwg"
        return RebuildResult(unit.index, target, target, target, {}, 50, tmp_path / "x.log", 100, 200)

    runner._execute_group = execute
    with pytest.raises(RuntimeError, match="boom"):
        runner._run_groups(
            "job",
            "worker",
            object(),
            CadCapability("2020", None, None),
            [_unit(tmp_path, index, "rename_only" if index % 2 == 0 else "rebuild") for index in range(5)],
        )
    assert set(started) <= {0, 1}


def test_failure_in_completed_batch_stops_before_replenishing_pool(tmp_path: Path, monkeypatch):
    submitted: list[int] = []

    class ControlledExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, function, *args):
            unit = args[-1]
            submitted.append(unit.index)
            future = cad_job.Future()
            try:
                future.set_result(function(*args))
            except BaseException as exc:  # noqa: BLE001 - 模拟 CAD 工作单元失败。
                future.set_exception(exc)
            return future

    def success_before_failure(futures, **_kwargs):
        return sorted(futures, key=lambda future: futures[future].index, reverse=True), set()

    def execute(_job, _workspace, _capability, unit):
        if unit.index == 0:
            raise RuntimeError("boom")
        target = tmp_path / f"{unit.index}.dwg"
        return RebuildResult(unit.index, target, target, target, {}, 10, tmp_path / "x.log", 100, 200)

    monkeypatch.setattr(cad_job, "ThreadPoolExecutor", ControlledExecutor)
    monkeypatch.setattr(cad_job, "wait", success_before_failure)
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, 2)
    runner._execute_group = execute

    with pytest.raises(RuntimeError, match="boom"):
        runner._run_groups(
            "job",
            "worker",
            object(),
            CadCapability("2020", None, None),
            [_unit(tmp_path, index, "rename_only" if index % 2 == 0 else "rebuild") for index in range(4)],
        )

    assert submitted == [0, 1]
