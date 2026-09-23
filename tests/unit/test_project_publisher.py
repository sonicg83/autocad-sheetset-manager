"""新项目发布事务：目标原状态、显式候选清单、回滚与启动恢复（PLAN-DM-036 Task 6）。

覆盖 brief Step 1 的三个逐字用例（目标不存在/已存在空目录的失败回滚、非空目标零
改动）以及本任务的核心安全不变量：

- 只按**显式候选清单**发布：暂存区里出现清单之外的文件一律不发布（Task 5 复核
  发现候选 DST 先写盘后校验，因此绝不按目录扫描 attempt 暂存区）；
- 失败只回滚本次已创建且身份匹配的文件，随后精确恢复「目录不存在」或「目录存在
  且为空」；空目录不误删、外来内容不误删，全程无宽泛递归删除；
- 进程在 `PREPARED`/`PUBLISHING` 中断时保留持久日志，由启动恢复幂等处理；目标
  出现不属于本次清单的外部内容时停止自动清理并标记 `NEEDS_REVIEW`；
- 发布日志先落在 Manager 应用数据目录（attempt 命名空间），记录目标原状态、目标
  身份、候选清单/哈希、`job_id`/`attempt` 与每个已提交文件；
- 一条**损坏日志**（截断/非 JSON/不是 JSON 对象/非法 UTF-8 字节/非字符串 `status`/
  缺键或类型错误）绝不阻断启动恢复，也不阻断其它任务的恢复：跳过该日志、保留现场
  与日志，或走既有隔离分支落 `NEEDS_REVIEW`。

测试只用 `tmp_path`，不依赖用户本地数据库、真实工程目录或上次运行残留。
"""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from dst_manager.application.creation_candidate import (
    CreationCandidate,
    CreationValidationReport,
    StagedDrawing,
)
from dst_manager.application.creation_job import CREATION_JOBS_DIR_NAME
from dst_manager.infrastructure.acsm_xml.creation import CREATION_DST_NAME
from dst_manager.infrastructure.filesystem.locking import WorkspaceTransactionLock
from dst_manager.infrastructure.filesystem.project_publish_types import (
    ProjectPublishError,
)
from dst_manager.infrastructure.filesystem.project_publisher import (
    CREATION_PUBLISH_JOURNAL_NAME,
    CREATION_PUBLISH_REVISION_DIR_NAME,
    ProjectPublisher,
)
from dst_manager.infrastructure.filesystem.publish_errors import PublishRecoveryError
from dst_manager.infrastructure.filesystem.publish_primitives import file_sha256

#: 候选清单：一个 DST + 两个图纸组主 DWG（顺序即提交顺序）。
DWG_NAMES = ("RQ-01-02 平面图.dwg", "RQ-03 剖面图.dwg")


class ProcessInterrupted(BaseException):
    """模拟进程在发布中途被终止（代码不执行回滚，只留持久日志现场）。"""


class FaultInjector:
    """显式故障注入：提交第 N 个文件后失败/中断，或在指定阶段前终止进程。"""

    def __init__(self) -> None:
        self.commits = 0
        self._fail_after: int | None = None
        self._interrupt_after: int | None = None
        self._stage: str | None = None

    def fail_after_replace(self, count: int) -> None:
        self._fail_after = count

    def interrupt_after_replace(self, count: int) -> None:
        self._interrupt_after = count

    def fail_at_stage(self, stage: str) -> None:
        self._stage = stage

    def at_stage(self, stage: str) -> None:
        if self._stage == stage:
            raise ProcessInterrupted(f"注入进程中断：{stage}")

    def after_commit(self, target: Path) -> None:
        self.commits += 1
        if self._interrupt_after == self.commits:
            raise ProcessInterrupted(f"注入进程中断：第 {self.commits} 个文件提交后")
        if self._fail_after == self.commits:
            raise ProjectPublishError(
                "CREATION_PUBLISH_FAILED", f"注入第 {self.commits} 个文件提交失败"
            )


@pytest.fixture
def fault_injector() -> FaultInjector:
    return FaultInjector()


@pytest.fixture
def publisher(fault_injector: FaultInjector) -> ProjectPublisher:
    return ProjectPublisher(fault_injector=fault_injector)


def creation_jobs_root(tmp_path: Path) -> Path:
    return tmp_path / "data" / CREATION_JOBS_DIR_NAME


def make_candidate(
    tmp_path: Path,
    *,
    job_id: str = "job-1",
    attempt: int = 1,
    dwg_names: tuple[str, ...] = DWG_NAMES,
) -> CreationCandidate:
    """在 Manager 应用数据目录的隔离 attempt 中构造显式候选清单。"""
    attempt_dir = creation_jobs_root(tmp_path) / job_id / f"attempt-{attempt:03d}"
    dst_path = attempt_dir / "staging" / "final-dst" / CREATION_DST_NAME
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(b"candidate-dst")
    dwgs = []
    for index, name in enumerate(dwg_names):
        staged = attempt_dir / "staging" / f"group-{index:03d}" / name
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(f"candidate-dwg-{index}".encode())
        dwgs.append(StagedDrawing(f"group-{index + 1}", staged, name))
    return CreationCandidate(
        job_id=job_id,
        attempt=attempt,
        attempt_dir=attempt_dir,
        target_path=str(tmp_path / "new-project"),
        dst_name=CREATION_DST_NAME,
        dst_path=dst_path,
        dwgs=tuple(dwgs),
        layouts={},
        handles={},
        report=CreationValidationReport(
            repair_status="VALID",
            semantic_issue_codes=(),
            encoded_sha256=file_sha256(dst_path),
            dwg_count=len(dwgs),
            sheet_count=0,
        ),
    )


@pytest.fixture
def candidate(tmp_path: Path) -> CreationCandidate:
    return make_candidate(tmp_path)


def journal_path(candidate: CreationCandidate) -> Path:
    return candidate.attempt_dir / CREATION_PUBLISH_JOURNAL_NAME


def read_journal(candidate: CreationCandidate) -> dict:
    return json.loads(journal_path(candidate).read_text(encoding="utf-8"))


def published_names(target: Path) -> list[str]:
    return sorted(item.name for item in target.iterdir())


def _identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


def _write_journal(path: Path, journal: dict) -> None:
    path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- Step 1：目标原状态与故障注入 ------------------------------------------


@pytest.mark.parametrize("target_existed", [False, True])
def test_publish_failure_restores_original_target(
    tmp_path: Path, candidate, fault_injector, publisher, target_existed
) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.fail_after_replace(1)
    with pytest.raises(ProjectPublishError):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []


def test_nonempty_target_is_not_touched(tmp_path: Path, candidate, publisher) -> None:
    target = tmp_path / "new-project"
    target.mkdir()
    marker = target / "existing.txt"
    marker.write_text("保留", encoding="utf-8")
    with pytest.raises(ProjectPublishError, match="CREATION_TARGET_NOT_EMPTY"):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    assert marker.read_text(encoding="utf-8") == "保留"
    assert published_names(target) == ["existing.txt"]


# ---- 成功发布：显式清单、日志与成果 ----------------------------------------


def test_publish_commits_only_the_explicit_candidate_manifest(
    tmp_path: Path, candidate, publisher
) -> None:
    # 暂存区里的清单外文件（Task 5「先写盘后校验」的残留形态）绝不能被发布
    stray = candidate.attempt_dir / "staging" / "final-dst" / "残留候选.dst"
    stray.write_bytes(b"stray")
    target = tmp_path / "new-project"

    published = publisher.publish_new_project(candidate, target, "job-1", 1)

    assert published.job_id == "job-1"
    assert published.attempt == 1
    assert published.target_dir == target
    assert published.dst_path == target / CREATION_DST_NAME
    assert published.target_state == "missing"
    assert published.journal_path == journal_path(candidate)
    assert published_names(target) == sorted([CREATION_DST_NAME, *DWG_NAMES])
    assert published.dst_path.read_bytes() == b"candidate-dst"
    for staged in (candidate.dst_path, *(item.staged_path for item in candidate.dwgs)):
        assert staged.is_file(), "发布不得移动或删除候选暂存文件"
    assert [item.name for item in published.files] == [CREATION_DST_NAME, *DWG_NAMES]
    assert [item.role for item in published.files] == ["dst", "dwg", "dwg"]
    assert [item.group_id for item in published.files] == ["", "group-1", "group-2"]
    assert [item.sha256 for item in published.files] == [
        file_sha256(item.target) for item in published.files
    ]
    assert [item.size for item in published.files] == [
        item.target.stat().st_size for item in published.files
    ]


def test_publish_journal_records_target_state_identity_and_committed_files(
    tmp_path: Path, candidate, publisher
) -> None:
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)

    journal = read_journal(candidate)
    assert journal["operation_id"] == "job-1"
    assert journal["attempt"] == 1
    assert journal["kind"] == "creation"
    assert journal["status"] == "COMMITTED"
    assert journal["target"]["path"] == str(target)
    assert journal["target"]["state"] == "missing"
    assert journal["target"]["identity"] is None
    assert [item["name"] for item in journal["files"]] == [CREATION_DST_NAME, *DWG_NAMES]
    for item in journal["files"]:
        assert item["staged_hash"] == file_sha256(Path(item["staged"]))
        assert item["committed"] is True
        assert item["result_hash"] == file_sha256(Path(item["target"]))
        assert item["result_identity"] == _identity(Path(item["target"]))
    assert journal["created_directories"][-1]["path"] == str(target)
    assert journal["cleanup_status"] == "COMPLETE"
    # 提交清单归档到 attempt 命名空间的修订证据目录
    manifest = candidate.attempt_dir / CREATION_PUBLISH_REVISION_DIR_NAME / "manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["operation_id"] == "job-1"
    assert published_names(candidate.attempt_dir / CREATION_PUBLISH_REVISION_DIR_NAME) == [
        "manifest.json",
        "publish-journal.json",
    ]


def test_publish_reuses_existing_empty_directory(tmp_path: Path, candidate, publisher) -> None:
    target = tmp_path / "new-project"
    target.mkdir()
    identity = _identity(target)

    published = publisher.publish_new_project(candidate, target, "job-1", 1)

    assert published.target_state == "empty-directory"
    journal = read_journal(candidate)
    assert journal["target"]["state"] == "empty-directory"
    assert journal["target"]["identity"] == identity
    assert journal["created_directories"] == []
    assert published_names(target) == sorted([CREATION_DST_NAME, *DWG_NAMES])


def test_publish_creates_missing_parent_directories(tmp_path: Path, candidate, publisher) -> None:
    target = tmp_path / "projects" / "nested" / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    assert target.is_dir()
    journal = read_journal(candidate)
    assert [Path(item["path"]).name for item in journal["created_directories"]] == [
        "projects",
        "nested",
        "new-project",
    ]


# ---- 失败回滚：第一个/中间/最后一个文件 ------------------------------------


@pytest.mark.parametrize("target_existed", [False, True])
@pytest.mark.parametrize("fail_after", [1, 2, 3])
def test_publish_failure_at_every_file_restores_exact_original_state(
    tmp_path: Path, candidate, fault_injector, publisher, target_existed, fail_after
) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.fail_after_replace(fail_after)

    with pytest.raises(ProjectPublishError) as excinfo:
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert excinfo.value.outcome == "ROLLED_BACK"
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []
    journal = read_journal(candidate)
    assert journal["status"] == "ROLLED_BACK"
    assert [item["committed"] for item in journal["files"]] == [
        True
    ] * fail_after + [False] * (3 - fail_after)


def test_publish_failure_removes_only_created_parent_directories(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    existing = tmp_path / "projects"
    existing.mkdir()
    (existing / "保留.txt").write_text("外部内容", encoding="utf-8")
    target = existing / "nested" / "new-project"
    fault_injector.fail_after_replace(2)

    with pytest.raises(ProjectPublishError):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert not target.exists()
    assert not (existing / "nested").exists()
    assert published_names(existing) == ["保留.txt"]


def test_missing_staged_file_aborts_before_touching_the_target(
    tmp_path: Path, candidate, publisher
) -> None:
    candidate.dwgs[1].staged_path.unlink()
    target = tmp_path / "new-project"

    with pytest.raises(ProjectPublishError) as excinfo:
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert excinfo.value.outcome == "ABORTED"
    assert not target.exists()
    assert not journal_path(candidate).exists()


@pytest.mark.parametrize(
    ("job_id", "attempt", "file_name"),
    [
        ("other-job", 1, "ok.dwg"),
        ("job-1", 2, "ok.dwg"),
        ("job-1", 1, "../越界.dwg"),
        ("job-1", 1, "子目录/越界.dwg"),
        ("job-1", 1, ""),
    ],
)
def test_candidate_identity_and_target_names_are_gated(
    tmp_path: Path, candidate, publisher, job_id, attempt, file_name
) -> None:
    candidate = replace(
        candidate,
        job_id=job_id,
        attempt=attempt,
        dwgs=(
            StagedDrawing("group-1", candidate.dwgs[0].staged_path, file_name),
            *candidate.dwgs[1:],
        ),
    )
    target = tmp_path / "new-project"

    with pytest.raises(ProjectPublishError) as excinfo:
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert excinfo.value.outcome == "ABORTED"
    assert not target.exists()
    assert not journal_path(candidate).exists()


def test_attempt_namespace_cannot_be_reused(tmp_path: Path, candidate, publisher) -> None:
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)

    with pytest.raises(ProjectPublishError, match="CREATION_PUBLISH_CONFLICT"):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert published_names(target) == sorted([CREATION_DST_NAME, *DWG_NAMES])


# ---- 启动恢复：PREPARED / PUBLISHING 中断 ----------------------------------


@pytest.mark.parametrize("target_existed", [False, True])
def test_interrupted_prepared_publish_is_recovered_without_side_effects(
    tmp_path: Path, candidate, fault_injector, publisher, target_existed
) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.fail_at_stage("PREPARED")

    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert read_journal(candidate)["status"] == "PREPARED"
    assert target.exists() is target_existed
    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))
    assert [(item.job_id, item.attempt, item.conclusion) for item in outcomes] == [
        ("job-1", 1, "ROLLED_BACK")
    ]
    assert read_journal(candidate)["status"] == "ROLLED_BACK"
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []


@pytest.mark.parametrize("target_existed", [False, True])
def test_interrupted_publishing_before_first_file_is_recovered(
    tmp_path: Path, candidate, fault_injector, publisher, target_existed
) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.fail_at_stage("PUBLISHING")

    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert read_journal(candidate)["status"] == "PUBLISHING"
    assert [item.conclusion for item in publisher.recover_creation_publishes(
        creation_jobs_root(tmp_path)
    )] == ["ROLLED_BACK"]
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []


@pytest.mark.parametrize("target_existed", [False, True])
@pytest.mark.parametrize("interrupted_after", [1, 2, 3])
def test_interrupted_publishing_after_committed_files_restores_original_state(
    tmp_path: Path, candidate, fault_injector, publisher, target_existed, interrupted_after
) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.interrupt_after_replace(interrupted_after)

    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    assert [item.conclusion for item in publisher.recover_creation_publishes(
        creation_jobs_root(tmp_path)
    )] == ["ROLLED_BACK"]
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []
    journal = read_journal(candidate)
    assert journal["status"] == "ROLLED_BACK"
    assert [item["committed"] for item in journal["files"]] == [
        True
    ] * interrupted_after + [False] * (3 - interrupted_after)


def test_recovery_stops_cleanup_when_external_content_appears(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    external = target / "外部.dwg"
    external.write_bytes(b"external")
    journal = read_journal(candidate)
    journal["status"] = "PUBLISHING"
    _write_journal(journal_path(candidate), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [item.conclusion for item in outcomes] == ["NEEDS_REVIEW"]
    assert external.read_bytes() == b"external"
    assert published_names(target) == ["外部.dwg"]
    assert read_journal(candidate)["status"] == "NEEDS_REVIEW"


def test_recovery_never_deletes_an_externally_replaced_file(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    # 中断后同名目标路径被外部内容占用：绝不按名字删除
    (target / CREATION_DST_NAME).write_bytes(b"external-replacement")

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [item.conclusion for item in outcomes] == ["NEEDS_REVIEW"]
    assert (target / CREATION_DST_NAME).read_bytes() == b"external-replacement"
    assert published_names(target) == [CREATION_DST_NAME]


def test_recovery_is_idempotent_and_keeps_the_journal(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)

    first = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))
    second = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [item.conclusion for item in first] == ["ROLLED_BACK"]
    assert second == []
    assert journal_path(candidate).is_file()


def test_recovery_ignores_absent_creation_jobs_root(tmp_path: Path, publisher) -> None:
    assert publisher.recover_creation_publishes(tmp_path / "absent") == []


def test_recovery_reports_committed_publish_without_touching_files(
    tmp_path: Path, candidate, publisher
) -> None:
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-1", "COMMITTED")]
    assert outcomes[0].published["target_dir"] == str(target)
    assert published_names(target) == sorted([CREATION_DST_NAME, *DWG_NAMES])


def test_recovery_repairs_missing_committed_manifest(
    tmp_path: Path, candidate, publisher
) -> None:
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    manifest = candidate.attempt_dir / CREATION_PUBLISH_REVISION_DIR_NAME / "manifest.json"
    manifest.unlink()
    journal = read_journal(candidate)
    journal["cleanup_status"] = "PENDING"
    _write_journal(journal_path(candidate), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [item.conclusion for item in outcomes] == ["COMMITTED"]
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "COMMITTED"
    assert read_journal(candidate)["cleanup_status"] == "COMPLETE"


def test_recovery_rejects_journal_identity_mismatch(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    journal = read_journal(candidate)
    journal["attempt"] = 7
    _write_journal(journal_path(candidate), journal)

    with pytest.raises(PublishRecoveryError, match="PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"):
        publisher.recover_creation_publishes(creation_jobs_root(tmp_path))


def test_recovery_skips_a_publish_that_still_holds_the_target_lock(
    tmp_path: Path, candidate, fault_injector, publisher
) -> None:
    """同一目标上仍有进程持锁（发布或恢复进行中）：启动恢复不介入现场。"""
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    lock_path = Path(read_journal(candidate)["lock_path"])

    with WorkspaceTransactionLock(lock_path):
        outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert outcomes == []
    assert read_journal(candidate)["status"] == "PUBLISHING"
    assert target.is_dir() and list(target.iterdir()) == []


# ---- 启动恢复：损坏日志容错 ------------------------------------------------


#: 日志被截断/改写后的形态：截断的 JSON、非 JSON 内容、JSON 但不是对象。
CORRUPT_JOURNAL_TEXTS = {
    "truncated-json": '{"identity_version": 1, "kind": "creation", "operation_id": "job-1"',
    "not-json": "这不是 JSON 日志",
    "json-array": "[1, 2, 3]",
    "json-string": '"日志被改写"',
}


@pytest.mark.parametrize("corruption", sorted(CORRUPT_JOURNAL_TEXTS))
def test_recovery_skips_a_corrupt_journal_and_still_recovers_others(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """损坏日志既不阻断恢复，也不阻断其它任务：跳过该日志并原样保留现场。"""
    broken = make_candidate(tmp_path, job_id="job-1")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    for item, target in (
        (broken, tmp_path / "new-project"),
        (healthy, tmp_path / "other-project"),
    ):
        with pytest.raises(ProcessInterrupted):
            publisher.publish_new_project(item, target, item.job_id, item.attempt)
    corrupt_text = CORRUPT_JOURNAL_TEXTS[corruption]
    journal_path(broken).write_text(corrupt_text, encoding="utf-8")

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    # 损坏日志被跳过，同一批里的健康日志照常回滚
    assert [(item.job_id, item.attempt, item.conclusion) for item in outcomes] == [
        ("job-2", 1, "ROLLED_BACK")
    ]
    assert journal_path(broken).read_text(encoding="utf-8") == corrupt_text
    assert published_names(tmp_path / "new-project") == []
    assert not (tmp_path / "other-project").exists()


def test_recovery_skips_a_journal_path_that_is_not_a_file(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher
) -> None:
    """日志路径不可读取（OSError）同样只跳过该日志，不阻断启动恢复。"""
    candidate = make_candidate(tmp_path, job_id="job-1")
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, tmp_path / "new-project", "job-1", 1)
    path = journal_path(candidate)
    path.unlink()
    path.mkdir()

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert outcomes == []
    assert path.is_dir()


#: 已提交日志的结构损坏形态：成果投影所需的键缺失或类型错误。
COMMITTED_JOURNAL_CORRUPTIONS: dict[str, Callable[[dict], None]] = {
    "files-missing": lambda journal: journal.pop("files"),
    "files-not-a-list": lambda journal: journal.update(files="已提交文件清单被改写"),
    "files-entry-missing-keys": lambda journal: journal.update(files=[{"name": "a.dwg"}]),
    "files-without-dst-role": lambda journal: journal.update(
        files=[{**journal["files"][1], "role": "dwg"}]
    ),
    "target-missing": lambda journal: journal.pop("target"),
    "target-not-an-object": lambda journal: journal.update(target="目标路径被改写"),
    "revision-dir-missing": lambda journal: journal.pop("revision_dir"),
}


@pytest.mark.parametrize("corruption", sorted(COMMITTED_JOURNAL_CORRUPTIONS))
def test_recovery_skips_a_committed_journal_with_untrusted_structure(
    tmp_path: Path, candidate, publisher: ProjectPublisher, corruption: str
) -> None:
    """已提交日志缺键/类型错误：既不闭环成功，也不清理或覆盖任何成果文件。"""
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    published = published_names(target)
    journal = read_journal(candidate)
    COMMITTED_JOURNAL_CORRUPTIONS[corruption](journal)
    _write_journal(journal_path(candidate), journal)
    corrupted = journal_path(candidate).read_text(encoding="utf-8")

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert outcomes == []
    assert journal_path(candidate).read_text(encoding="utf-8") == corrupted
    assert published_names(target) == published


@pytest.mark.parametrize("files", [None, "清单被改写"])
def test_recovery_isolates_a_rollback_journal_without_a_trusted_manifest(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, files: str | None
) -> None:
    """回滚阶段的日志缺键/类型错误：既有隔离分支接管，绝不逃出启动路径。"""
    candidate = make_candidate(tmp_path, job_id="job-1")
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    journal = read_journal(candidate)
    if files is None:
        journal.pop("files")
    else:
        journal["files"] = files
    _write_journal(journal_path(candidate), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-1", "NEEDS_REVIEW")]
    assert read_journal(candidate)["status"] == "ROLLBACK_FAILED"
    assert published_names(target) == []


#: 日志的**字节级**损坏形态：手工按 ANSI/GBK 保存含中文的日志、二进制垃圾覆写。
#: 这两种输入在 ``read_text(encoding="utf-8")`` 上抛 ``UnicodeDecodeError``（它是
#: ``ValueError`` 子类，不是 ``JSONDecodeError`` 子类）。
CORRUPT_JOURNAL_BYTES = {
    "gbk-saved-journal": (
        '{"identity_version": 1, "kind": "creation", "operation_id": "job-1", '
        '"attempt": 1, "status": "PUBLISHING", "detail": "手工用 ANSI 保存的日志"}'
    ).encode("gbk"),
    "binary-garbage": b"\x00\xff\xfe\x00\x01binary garbage",
}


@pytest.mark.parametrize("corruption", sorted(CORRUPT_JOURNAL_BYTES))
def test_recovery_skips_a_journal_with_undecodable_bytes(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """日志字节不是合法 UTF-8：与其它损坏日志一样只跳过，绝不阻断启动恢复。"""
    broken = make_candidate(tmp_path, job_id="job-1")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    for item, target in (
        (broken, tmp_path / "new-project"),
        (healthy, tmp_path / "other-project"),
    ):
        with pytest.raises(ProcessInterrupted):
            publisher.publish_new_project(item, target, item.job_id, item.attempt)
    corrupt_bytes = CORRUPT_JOURNAL_BYTES[corruption]
    journal_path(broken).write_bytes(corrupt_bytes)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    assert journal_path(broken).read_bytes() == corrupt_bytes
    assert published_names(tmp_path / "new-project") == []
    assert not (tmp_path / "other-project").exists()


#: ``status`` 不是字符串（JSON 数组/对象）：直接入 ``frozenset`` 会抛 ``TypeError``。
NON_STRING_STATUSES: dict[str, object] = {
    "status-array": ["PUBLISHING"],
    "status-object": {"state": "PUBLISHING"},
}


@pytest.mark.parametrize("corruption", sorted(NON_STRING_STATUSES))
def test_recovery_skips_a_journal_with_a_non_string_status(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """``status`` 不可哈希：按不可信日志跳过，绝不逃出启动恢复。"""
    broken = make_candidate(tmp_path, job_id="job-1")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    for item, target in (
        (broken, tmp_path / "new-project"),
        (healthy, tmp_path / "other-project"),
    ):
        with pytest.raises(ProcessInterrupted):
            publisher.publish_new_project(item, target, item.job_id, item.attempt)
    status = NON_STRING_STATUSES[corruption]
    journal = read_journal(broken)
    journal["status"] = status
    _write_journal(journal_path(broken), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    # 不可信日志原样保留（只跳过，不做猜测性清理）
    assert read_journal(broken)["status"] == status
    assert published_names(tmp_path / "new-project") == []
    assert not (tmp_path / "other-project").exists()


@pytest.mark.parametrize(
    "target_value",
    ["目标路径被改写", [], 7, {"state": "missing"}],
    ids=["target-string", "target-array", "target-number", "target-without-path"],
)
def test_recovery_isolates_a_rollback_journal_with_an_untrusted_target(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, target_value: object
) -> None:
    """回滚阶段的 ``target`` 非对象或缺 ``path``：既有隔离分支接管，不逃出启动路径。"""
    candidate = make_candidate(tmp_path, job_id="job-1")
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    journal = read_journal(candidate)
    journal["target"] = target_value
    _write_journal(journal_path(candidate), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-1", "NEEDS_REVIEW")]
    assert read_journal(candidate)["status"] == "ROLLBACK_FAILED"
    assert published_names(target) == []


#: 已提交日志的锁路径不可用形态：恢复无法与进行中的发布互斥。
COMMITTED_JOURNAL_UNTRUSTED_LOCKS: dict[str, Callable[[dict], None]] = {
    "lock-path-missing": lambda journal: journal.pop("lock_path"),
    "lock-path-not-a-string": lambda journal: journal.update(lock_path=["锁路径被改写"]),
    "lock-path-empty": lambda journal: journal.update(lock_path=""),
}


@pytest.mark.parametrize("corruption", sorted(COMMITTED_JOURNAL_UNTRUSTED_LOCKS))
def test_recovery_skips_a_committed_journal_without_a_usable_recovery_lock(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """已提交日志缺锁路径：只跳过这一条，绝不因此隔离同批其它任务。"""
    committed = make_candidate(tmp_path, job_id="job-1")
    committed_target = tmp_path / "new-project"
    ProjectPublisher().publish_new_project(committed, committed_target, "job-1", 1)
    published = published_names(committed_target)
    journal = read_journal(committed)
    COMMITTED_JOURNAL_UNTRUSTED_LOCKS[corruption](journal)
    _write_journal(journal_path(committed), journal)
    corrupted = journal_path(committed).read_text(encoding="utf-8")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(healthy, tmp_path / "other-project", "job-2", 1)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    assert journal_path(committed).read_text(encoding="utf-8") == corrupted
    assert published_names(committed_target) == published
    assert not (tmp_path / "other-project").exists()


#: 日志内容驱动的**递归**损坏形态：``json.loads`` 对病态深嵌套 JSON 抛 ``RecursionError``
#: （``RuntimeError`` 子类，既不是 ``JSONDecodeError`` 也不是 ``ValueError``）。
def _journal_with_pathologically_nested_json(journal_path: Path) -> bytes:
    depth = 100_000
    raw = (
        '{"identity_version": 1, "kind": "creation", "operation_id": "job-1", '
        '"attempt": 1, "status": "PUBLISHING", "files": '
        + "[" * depth
        + "]" * depth
        + "}"
    ).encode("utf-8")
    journal_path.write_bytes(raw)
    return raw


def test_recovery_skips_a_journal_with_pathologically_nested_json(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher
) -> None:
    """病态深嵌套 JSON：与其它损坏日志一样只跳过，绝不阻断启动恢复。"""
    broken = make_candidate(tmp_path, job_id="job-1")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    for item, target in (
        (broken, tmp_path / "new-project"),
        (healthy, tmp_path / "other-project"),
    ):
        with pytest.raises(ProcessInterrupted):
            publisher.publish_new_project(item, target, item.job_id, item.attempt)
    corrupt_bytes = _journal_with_pathologically_nested_json(journal_path(broken))

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    assert journal_path(broken).read_bytes() == corrupt_bytes
    assert published_names(tmp_path / "new-project") == []
    assert not (tmp_path / "other-project").exists()


#: 锁路径**可用性**故障形态（环境驱动，与日志字段是否齐全无关）：锁路径指向已存在目录
#: （``GENERIC_READ|GENERIC_WRITE`` 打不开 → ``FileLockError``）、锁路径父级是普通文件
#: （``mkdir`` 抛 ``FileExistsError``，不是 ``FileLockError``，只有 ``OSError`` 才覆盖）。
UNUSABLE_LOCK_PATHS: dict[str, Callable[[dict, Path], None]] = {
    "lock-path-at-a-directory": lambda journal, attempt_dir: journal.update(
        lock_path=str(attempt_dir)
    ),
    "lock-path-below-a-file": lambda journal, attempt_dir: _lock_path_below_a_file(
        journal, attempt_dir
    ),
}


def _lock_path_below_a_file(journal: dict, attempt_dir: Path) -> None:
    blocker = attempt_dir / "blocker.txt"
    blocker.write_text("占位普通文件", encoding="utf-8")
    journal["lock_path"] = str(blocker / "target.lock")


@pytest.mark.parametrize("corruption", sorted(UNUSABLE_LOCK_PATHS))
def test_recovery_skips_a_committed_journal_with_an_unusable_lock_path(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """已提交日志的锁路径不可用：只跳过这一条，绝不终止整批恢复。"""
    committed = make_candidate(tmp_path, job_id="job-1")
    committed_target = tmp_path / "new-project"
    ProjectPublisher().publish_new_project(committed, committed_target, "job-1", 1)
    published = published_names(committed_target)
    journal = read_journal(committed)
    UNUSABLE_LOCK_PATHS[corruption](journal, committed.attempt_dir)
    _write_journal(journal_path(committed), journal)
    corrupted = journal_path(committed).read_text(encoding="utf-8")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(healthy, tmp_path / "other-project", "job-2", 1)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    assert journal_path(committed).read_text(encoding="utf-8") == corrupted
    assert published_names(committed_target) == published
    assert not (tmp_path / "other-project").exists()


def test_recovery_skips_a_committed_journal_while_the_target_lock_is_held(
    tmp_path: Path, candidate, publisher: ProjectPublisher
) -> None:
    """已提交日志的目标锁被占用（另一进程正在发布/恢复）：不介入现场，不终止整批恢复。"""
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    journal = read_journal(candidate)
    published = published_names(target)

    with WorkspaceTransactionLock(Path(journal["lock_path"])):
        outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert outcomes == []
    assert read_journal(candidate) == journal
    assert published_names(target) == published


def test_recovery_skips_a_committed_journal_when_post_commit_cleanup_fails(
    tmp_path: Path,
    candidate,
    fault_injector: FaultInjector,
    publisher: ProjectPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """提交后归档的环境故障（权限/占用/磁盘）：只跳过这一条，绝不终止整批恢复。"""
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    published = published_names(target)
    journal = read_journal(candidate)
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(healthy, tmp_path / "other-project", "job-2", 1)

    def fail_cleanup(*_args: object, **_kwargs: object) -> bool:
        raise OSError("注入提交后归档故障：磁盘不可写")

    monkeypatch.setattr(publisher, "_finish_committed_cleanup", fail_cleanup)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-2", "ROLLED_BACK")]
    assert read_journal(candidate) == journal
    assert published_names(target) == published
    assert not (tmp_path / "other-project").exists()


@pytest.mark.parametrize("corruption", sorted(UNUSABLE_LOCK_PATHS))
def test_recovery_isolates_a_rollback_journal_with_an_unusable_lock_path(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, corruption: str
) -> None:
    """回滚阶段锁路径不可用：既有隔离分支接管，现场零改动，不逃出启动路径。"""
    candidate = make_candidate(tmp_path, job_id="job-1")
    target = tmp_path / "new-project"
    fault_injector.fail_at_stage("PUBLISHING")
    with pytest.raises(ProcessInterrupted):
        publisher.publish_new_project(candidate, target, "job-1", 1)
    journal = read_journal(candidate)
    UNUSABLE_LOCK_PATHS[corruption](journal, candidate.attempt_dir)
    _write_journal(journal_path(candidate), journal)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-1", "NEEDS_REVIEW")]
    assert read_journal(candidate)["status"] == "ROLLBACK_FAILED"
    assert published_names(target) == []


#: 日志**内容**驱动、且 ``json.loads`` 仍能成功解析的写回失败形态：日志文本里的
#: ``"\ud800"`` 转义会被解析成孤立代理对，而 ``json.dumps(..., ensure_ascii=False)``
#: 与随后的 UTF-8 编码都对它抛 ``UnicodeEncodeError``（``ValueError`` 子类，既不是
#: ``JSONDecodeError`` 也不是 ``OSError``，因此 ``write_journal_best_effort`` 的
#: ``except OSError`` 捕不到）。
def _journal_with_a_lone_surrogate(journal: dict) -> bytes:
    """把日志文本写成含孤立代理对转义（``U+D800``）的 JSON：可解析，但写回必抛 ``UnicodeEncodeError``。"""
    journal["note"] = "\ud800"
    return json.dumps(journal, ensure_ascii=True).encode("utf-8")


@pytest.mark.parametrize("drop_files", [False, True], ids=["files-intact", "files-missing"])
def test_recovery_isolates_a_rollback_journal_with_a_lone_surrogate(
    tmp_path: Path, fault_injector: FaultInjector, publisher: ProjectPublisher, drop_files: bool
) -> None:
    """回滚分支的日志含孤立代理对：写回抛 ``UnicodeEncodeError`` 也必须隔离为人工核对。

    ``files-intact`` 走「回滚本身正常、处理器内的写回失败」；``files-missing`` 先让回滚
    失败（缺 ``files``）再让写回失败——两条路径都必须被守住，且不得阻断同批健康任务。
    """
    broken = make_candidate(tmp_path, job_id="job-1")
    healthy = replace(
        make_candidate(tmp_path, job_id="job-2"), target_path=str(tmp_path / "other-project")
    )
    fault_injector.fail_at_stage("PUBLISHING")
    for item, target in (
        (broken, tmp_path / "new-project"),
        (healthy, tmp_path / "other-project"),
    ):
        with pytest.raises(ProcessInterrupted):
            publisher.publish_new_project(item, target, item.job_id, item.attempt)
    journal = read_journal(broken)
    if drop_files:
        journal.pop("files")
    raw = _journal_with_a_lone_surrogate(journal)
    journal_path(broken).write_bytes(raw)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    assert [(item.job_id, item.conclusion) for item in outcomes] == [
        ("job-1", "NEEDS_REVIEW"),
        ("job-2", "ROLLED_BACK"),
    ]
    # 写不回去的日志原样保留（不猜测性改写），现场保留供人工核对
    assert journal_path(broken).read_bytes() == raw
    assert published_names(tmp_path / "new-project") == []
    assert not (tmp_path / "other-project").exists()


def test_recovery_contains_a_committed_journal_with_a_lone_surrogate(
    tmp_path: Path, candidate, publisher: ProjectPublisher
) -> None:
    """已提交日志含孤立代理对：提交后归档的写回本就在守护内，绝不逃出启动恢复。"""
    target = tmp_path / "new-project"
    publisher.publish_new_project(candidate, target, "job-1", 1)
    published = published_names(target)
    journal = read_journal(candidate)
    raw = _journal_with_a_lone_surrogate(journal)
    journal_path(candidate).write_bytes(raw)

    outcomes = publisher.recover_creation_publishes(creation_jobs_root(tmp_path))

    # 成果文件确已提交：归档只是证据补齐，写不回去既不改结论也不回滚成果
    assert [(item.job_id, item.conclusion) for item in outcomes] == [("job-1", "COMMITTED")]
    assert journal_path(candidate).read_bytes() == raw
    assert published_names(target) == published
