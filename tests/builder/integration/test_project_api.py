"""Builder 项目 API 集成测试（SPEC-DB-001 §3/§4/§11 / PLAN-DB-001 Task 3）。

覆盖：创建项目库与初始草稿、读取当前草稿与诊断、带 base_updated_at 乐观并发
保存、过期写入 409 DRAFT_CONFLICT、只读打开无副作用，以及三个仓储协议的
SQLite 适配器基本往返。
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from dst_builder.interfaces.api import create_builder_app

PROJECT_ROOT_NAME = "示例工程"
NOW = "2026-09-17T00:00:00+00:00"

VALID_DRAFT = {
    "schema_version": 1,
    "project": {
        "name": "示例工程",
        "stage": "施工图",
        "discipline": "建筑",
        "output_path": "D:/deliveries/example-package",
    },
    "numbering": {"prefix": "A-", "start": 1, "width": 3},
    "cad_version": "2020",
    "sheets": [{"title": "首层平面图"}],
    "template": {
        "base_asset_id": "3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
        "layout_asset_id": "8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
        "source_layout": "A1",
    },
}


def _create_body(project_root: Path | None = None) -> dict:
    body = {
        "name": PROJECT_ROOT_NAME,
        "stage": "施工图",
        "discipline": "建筑",
        "output_path": "D:/deliveries/example-package",
    }
    if project_root is not None:
        body["project_root"] = str(project_root)
    return body


def _patch_body(base_updated_at: str, **draft_overrides) -> dict:
    draft = json.loads(json.dumps(VALID_DRAFT))
    for dotted, value in draft_overrides.items():
        section, _, field = dotted.partition(".")
        draft[section][field] = value
    return {
        "base_updated_at": base_updated_at,
        "draft": draft,
        "wizard_step": 1,
        "focused_field": None,
    }


def _snapshot_files(root: Path) -> dict[str, tuple[int, int]]:
    """文件级快照（相对路径 -> 大小 + mtime_ns），用于只读无副作用断言。"""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "project"


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    return TestClient(create_builder_app(project_root=project_root))


def _create_project(client: TestClient) -> dict:
    response = client.post("/api/projects", json=_create_body())
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 创建项目
# ---------------------------------------------------------------------------


def test_create_project_writes_database_and_directories(
    project_root: Path, client: TestClient
) -> None:
    """POST /api/projects 创建 project.dstb、assets/ 与 builds/，并返回初始草稿。"""
    state = _create_project(client)

    assert state["project"]["name"] == PROJECT_ROOT_NAME
    assert state["project"]["stage"] == "施工图"
    assert state["project"]["discipline"] == "建筑"
    assert state["project"]["output_path"] == "D:/deliveries/example-package"
    assert state["project"]["id"]
    assert state["wizard_step"] == 1
    assert state["focused_field"] is None
    assert state["updated_at"]
    # 初始草稿按 §4 形态存储（允许携带非法字段，由诊断指出）。
    assert state["draft"]["schema_version"] == 1
    assert state["draft"]["project"]["name"] == PROJECT_ROOT_NAME
    assert state["draft"]["sheets"] == [{"title": ""}]
    assert state["draft"]["template"] == {
        "base_asset_id": "",
        "layout_asset_id": "",
        "source_layout": "",
    }
    # 初始草稿自带的未完成字段以阻断诊断呈现给七步引导。
    diagnostic_fields = {item["field"] for item in state["diagnostics"]}
    assert "sheets[0].title" in diagnostic_fields

    assert (project_root / "project.dstb").is_file()
    assert (project_root / "assets").is_dir()
    assert (project_root / "builds").is_dir()


def test_duplicate_create_opens_existing_project(client: TestClient) -> None:
    """目录已是 Builder 项目时重复提交创建 → 幂等打开既有项目而非 409。

    桌面壳重启后无法重开既有项目的回归修复：POST /api/projects 语义改为
    "创建或打开"，opened_existing=True 告知前端提示"已为你打开既有项目"。
    """
    created = _create_project(client)
    assert created["opened_existing"] is False
    original_id = created["project"]["id"]
    # 先编辑草稿，证明打开不会重置既有会话数据。
    patched = client.patch(
        "/api/projects/current/draft",
        json=_patch_body(created["updated_at"], **{"project.name": "改名工程"}),
    )
    assert patched.status_code == 200, patched.text

    reopened = client.post("/api/projects", json=_create_body())

    assert reopened.status_code == 200, reopened.text
    payload = reopened.json()
    assert payload["opened_existing"] is True
    assert payload["project"]["id"] == original_id
    assert payload["draft"]["project"]["name"] == "改名工程"
    # 打开后项目库仍可正常读取与保存。
    assert client.get("/api/projects/current").status_code == 200


def test_error_status_inherits_via_mro_for_unregistered_subclass(
    project_root: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """终审 Important ① 回归：未逐字登记的异常子类经 MRO 继承基类状态码，而非落 400。"""
    from dst_builder.application.assets import AssetHashMismatchError
    from dst_builder.application.projects import (
        BuilderProjectService,
        DraftConflictError,
    )
    from dst_builder.interfaces.api import _status_for_error

    class UnregisteredConflictError(DraftConflictError):
        """未在 _STATUS_BY_ERROR 登记的子类（基类映射 409）。"""

    class UnregisteredHashMismatchError(AssetHashMismatchError):
        """未登记的资产子类（基类映射 409）。"""

    # 纯函数路径：MRO 命中基类状态码。
    assert _status_for_error(UnregisteredConflictError("x")) == 409
    assert _status_for_error(UnregisteredHashMismatchError("x")) == 409
    # 完全未登记的错误族仍落默认 400。
    class UnregisteredError(Exception):
        pass

    assert _status_for_error(UnregisteredError("x")) == 400

    # API 路径：handler 抛出的子类异常得到 409 而非 400。
    def raise_subclass(self, creation):
        raise UnregisteredConflictError("注入：子类异常")

    monkeypatch.setattr(BuilderProjectService, "create_project", raise_subclass)
    response = client.post("/api/projects", json=_create_body())
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "DRAFT_CONFLICT"


def test_create_project_without_factory_root_uses_request_root(tmp_path: Path) -> None:
    """应用工厂未绑定根目录时，POST 请求体中的 project_root 生效。"""
    root = tmp_path / "from-request"
    client = TestClient(create_builder_app())

    response = client.post("/api/projects", json=_create_body(root))

    assert response.status_code == 201, response.text
    assert (root / "project.dstb").is_file()


# ---------------------------------------------------------------------------
# 只读打开
# ---------------------------------------------------------------------------


def test_get_current_before_initialization_creates_nothing(tmp_path: Path) -> None:
    """未初始化的根目录上 GET 只读打开返回 404，且不创建任何文件。"""
    root = tmp_path / "empty"
    client = TestClient(create_builder_app(project_root=root))

    response = client.get("/api/projects/current")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "PROJECT_PATH_INVALID"
    assert payload["recovery_action"]
    assert not root.exists()


def test_get_current_returns_project_draft_and_diagnostics(client: TestClient) -> None:
    """GET /api/projects/current 返回项目、当前草稿、步骤与诊断。"""
    created = _create_project(client)

    response = client.get("/api/projects/current")

    assert response.status_code == 200
    state = response.json()
    assert state["project"] == created["project"]
    assert state["draft"] == created["draft"]
    assert state["wizard_step"] == 1
    assert state["focused_field"] is None
    assert state["updated_at"] == created["updated_at"]
    codes = {item["code"] for item in state["diagnostics"]}
    assert "DRAFT_FIELD_INVALID" in codes
    for diagnostic in state["diagnostics"]:
        assert set(diagnostic) == {"code", "severity", "message", "field"}
        assert diagnostic["severity"] == "blocking"


def test_get_current_does_not_modify_project_files(project_root: Path, client: TestClient) -> None:
    """只读打开不改变 project.dstb 与 assets/、builds/ 目录中的任何文件。"""
    _create_project(client)
    (project_root / "assets").mkdir(exist_ok=True)
    (project_root / "builds").mkdir(exist_ok=True)
    before = _snapshot_files(project_root)
    assert "project.dstb" in before

    assert client.get("/api/projects/current").status_code == 200

    assert _snapshot_files(project_root) == before


def test_get_current_draft_matches_contract_hash_source(client: TestClient) -> None:
    """GET 返回的 draft 载荷与保存值逐字一致（规范化 JSON 可直接复现哈希输入）。"""
    _create_project(client)
    patch = client.patch(
        "/api/projects/current/draft",
        json=_patch_body(client.get("/api/projects/current").json()["updated_at"]),
    )
    assert patch.status_code == 200, patch.text

    state = client.get("/api/projects/current").json()
    assert state["draft"] == VALID_DRAFT
    assert state["diagnostics"] == []


# ---------------------------------------------------------------------------
# 保存草稿（乐观并发）
# ---------------------------------------------------------------------------


def test_patch_draft_trims_strings_and_persists(client: TestClient) -> None:
    """PATCH 保存去除首尾空白后的草稿，并返回字段级诊断。"""
    _create_project(client)
    base_updated_at = client.get("/api/projects/current").json()["updated_at"]

    response = client.patch(
        "/api/projects/current/draft",
        json=_patch_body(
            base_updated_at,
            **{"project.name": " 示例工程 ", "numbering.prefix": "<"},
        ),
    )

    assert response.status_code == 200, response.text
    state = response.json()
    # §4：所有字符串保存前去除首尾空白。
    assert state["draft"]["project"]["name"] == "示例工程"
    # 字段级诊断复用领域 validate_draft，非法前缀按字段聚焦。
    prefix_diagnostics = [
        item
        for item in state["diagnostics"]
        if item["field"] == "numbering.prefix" and item["code"] == "DRAFT_FIELD_INVALID"
    ]
    assert prefix_diagnostics
    # 草稿允许携带非法字段保存（防抖保存），读取时保持一致。
    saved = client.get("/api/projects/current").json()
    assert saved["draft"]["numbering"]["prefix"] == "<"
    assert saved["updated_at"] != base_updated_at


def test_patch_draft_rejects_stale_base_updated_at(client: TestClient) -> None:
    """过期写入返回 409 DRAFT_CONFLICT，且不落盘。"""
    _create_project(client)
    fresh = client.get("/api/projects/current").json()

    response = client.patch(
        "/api/projects/current/draft",
        json=_patch_body("2000-01-01T00:00:00+00:00"),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "DRAFT_CONFLICT"
    assert payload["message"]
    assert payload["recovery_action"]
    # 冲突后当前草稿保持原值，客户端可重新读取再保存。
    current = client.get("/api/projects/current").json()
    assert current["draft"] == fresh["draft"]
    assert current["updated_at"] == fresh["updated_at"]


def test_patch_draft_before_initialization_returns_404(tmp_path: Path) -> None:
    """数据库不存在时只有创建项目接口可写；PATCH 返回 404。"""
    root = tmp_path / "empty"
    client = TestClient(create_builder_app(project_root=root))

    response = client.patch("/api/projects/current/draft", json=_patch_body(NOW))

    assert response.status_code == 404
    assert response.json()["code"] == "PROJECT_PATH_INVALID"
    assert not root.exists()


def test_state_survives_server_restart(project_root: Path, client: TestClient) -> None:
    """草稿持久化在 project.dstb 中：新应用实例（重启）读取到同一状态。"""
    _create_project(client)
    base_updated_at = client.get("/api/projects/current").json()["updated_at"]
    assert (
        client.patch("/api/projects/current/draft", json=_patch_body(base_updated_at)).status_code
        == 200
    )

    restarted = TestClient(create_builder_app(project_root=project_root))
    state = restarted.get("/api/projects/current").json()

    assert state["draft"] == VALID_DRAFT
    assert state["project"]["name"] == PROJECT_ROOT_NAME


# ---------------------------------------------------------------------------
# 仓储协议 SQLite 适配器（RevisionRepository / BuildRepository）
# ---------------------------------------------------------------------------


def test_revision_and_build_repositories_round_trip(tmp_path: Path) -> None:
    """三个仓储协议的 SQLite 适配器可写入并读回修订、计划、构建记录与事件。"""
    from dst_builder.infrastructure.persistence.database import (
        Database,
        create_project_database,
    )
    from dst_builder.infrastructure.persistence.repositories import (
        BuildAttemptRecord,
        BuildEventRecord,
        BuildRunRecord,
        PlanRecord,
        RevisionRecord,
        SqliteBuildRepository,
        SqliteRevisionRepository,
    )

    db_path = tmp_path / "project.dstb"
    create_project_database(db_path)
    database = Database(db_path)

    revision = RevisionRecord(
        id="11111111-1111-4111-8111-111111111111",
        canonical_json='{"schema_version":1}',
        sha256="a" * 64,
        created_at=NOW,
    )
    plan = PlanRecord(
        id="22222222-2222-4222-8222-222222222222",
        revision_id=revision.id,
        canonical_json='{"schema_version":1}',
        sha256="b" * 64,
        confirmed_at=None,
    )
    run = BuildRunRecord(
        id="33333333-3333-4333-8333-333333333333",
        plan_id=plan.id,
        status="QUEUED",
        published_path=None,
        created_at=NOW,
        finished_at=None,
    )
    attempt = BuildAttemptRecord(
        build_id=run.id,
        attempt=1,
        status="PREPARING",
        progress=0,
        error_code=None,
        error_detail=None,
    )
    event = BuildEventRecord(
        id=1,
        build_id=run.id,
        attempt=1,
        sequence=1,
        event_json='{"schema_version":1}',
        created_at=NOW,
    )

    with database.sessions.begin() as session:
        revisions = SqliteRevisionRepository(session)
        revisions.insert_revision(revision)
        revisions.insert_plan(plan)
        builds = SqliteBuildRepository(session)
        builds.insert_build_run(run)
        builds.insert_attempt(attempt)
        builds.append_event(event)

    with database.sessions.begin() as session:
        revisions = SqliteRevisionRepository(session)
        builds = SqliteBuildRepository(session)
        assert revisions.load_revision(revision.id) == revision
        assert revisions.load_plan(plan.id) == plan
        assert builds.load_build_run(run.id) == run
        assert builds.list_attempts(run.id) == (attempt,)
        assert builds.list_events(run.id, 1) == (event,)

    # (build_id, attempt, sequence) 唯一：重复 sequence 违反约束。
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        SqliteBuildRepository(session).append_event(
            BuildEventRecord(
                id=2,
                build_id=run.id,
                attempt=1,
                sequence=1,
                event_json="{}",
                created_at=NOW,
            )
        )


def test_project_repository_enforces_single_project(tmp_path: Path) -> None:
    """ProjectRepository 拒绝第二条 projects 记录；数据库层由单例唯一索引兜底。"""
    from dst_builder.infrastructure.persistence.database import (
        Database,
        create_project_database,
    )
    from dst_builder.infrastructure.persistence.repositories import (
        ProjectRecord,
        ProjectRowExistsError,
        SqliteProjectRepository,
    )

    db_path = tmp_path / "project.dstb"
    create_project_database(db_path)
    database = Database(db_path)
    record = ProjectRecord(
        id="11111111-1111-4111-8111-111111111111",
        name=PROJECT_ROOT_NAME,
        stage="施工图",
        discipline="建筑",
        output_path="D:/deliveries/example-package",
        created_at=NOW,
        updated_at=NOW,
    )

    with database.sessions.begin() as session:
        SqliteProjectRepository(session).insert_project(record)
    with database.sessions.begin() as session:
        loaded = SqliteProjectRepository(session).load_project()
    assert loaded == record

    with pytest.raises(ProjectRowExistsError), database.sessions.begin() as session:
        SqliteProjectRepository(session).insert_project(
            ProjectRecord(
                id="22222222-2222-4222-8222-222222222222",
                name=record.name,
                stage=record.stage,
                discipline=record.discipline,
                output_path=record.output_path,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )


def test_project_repository_draft_cas_update(tmp_path: Path) -> None:
    """草稿 CAS 更新只在 expected_updated_at 匹配时生效。"""
    from dst_builder.infrastructure.persistence.database import (
        Database,
        create_project_database,
    )
    from dst_builder.infrastructure.persistence.repositories import (
        DraftRecord,
        ProjectRecord,
        SqliteProjectRepository,
    )

    db_path = tmp_path / "project.dstb"
    create_project_database(db_path)
    database = Database(db_path)
    project = ProjectRecord(
        id="11111111-1111-4111-8111-111111111111",
        name=PROJECT_ROOT_NAME,
        stage="施工图",
        discipline="建筑",
        output_path="D:/deliveries/example-package",
        created_at=NOW,
        updated_at=NOW,
    )
    draft = DraftRecord(
        project_id=project.id,
        payload_json=json.dumps(VALID_DRAFT, ensure_ascii=False),
        wizard_step=1,
        focused_field=None,
        updated_at=NOW,
    )

    with database.sessions.begin() as session:
        repo = SqliteProjectRepository(session)
        repo.insert_project(project)
        repo.insert_draft(draft)

    # 过期 base_updated_at：CAS 返回 False，草稿保持原值。
    with database.sessions.begin() as session:
        repo = SqliteProjectRepository(session)
        assert not repo.update_draft(
            project.id,
            expected_updated_at="2000-01-01T00:00:00+00:00",
            payload_json="{}",
            wizard_step=2,
            focused_field="numbering.prefix",
            updated_at="2026-09-17T01:00:00+00:00",
        )
    with database.sessions.begin() as session:
        unchanged = SqliteProjectRepository(session).load_draft(project.id)
    assert unchanged == draft

    # 匹配 base_updated_at：CAS 命中并写入新值。
    with database.sessions.begin() as session:
        assert SqliteProjectRepository(session).update_draft(
            project.id,
            expected_updated_at=NOW,
            payload_json="{}",
            wizard_step=2,
            focused_field="numbering.prefix",
            updated_at="2026-09-17T01:00:00+00:00",
        )
    with database.sessions.begin() as session:
        updated = SqliteProjectRepository(session).load_draft(project.id)
    assert updated.payload_json == "{}"
    assert updated.wizard_step == 2
    assert updated.focused_field == "numbering.prefix"
    assert updated.updated_at == "2026-09-17T01:00:00+00:00"


def test_project_file_hash_is_stable_across_read_only_opens(
    project_root: Path, client: TestClient
) -> None:
    """只读打开前后 project.dstb 的 SHA-256 一致（数据库头不被读路径改写）。"""
    _create_project(client)
    db_path = project_root / "project.dstb"

    def file_digest() -> str:
        return hashlib.sha256(db_path.read_bytes()).hexdigest()

    before = file_digest()
    assert client.get("/api/projects/current").status_code == 200
    assert file_digest() == before


def test_unbound_factory_binds_project_root_after_creation(tmp_path: Path) -> None:
    """桌面壳以未绑定工厂启动（project_root=None）时，应用内创建项目必须回绑根目录。

    回归背景：壳模式（create_builder_app(project_root=None)）下 POST /api/projects
    成功后 app.state.project_root 仍为 None，此后每次草稿自动保存都报
    "未绑定项目根目录"，向导完全不可用。修复后：创建成功即回绑，读取与保存
    走绑定后的服务。
    """
    project_root = tmp_path / "project"
    client = TestClient(create_builder_app(None))
    created = client.post("/api/projects", json=_create_body(project_root))
    assert created.status_code == 201, created.text
    updated_at = created.json()["updated_at"]

    current = client.get("/api/projects/current")
    assert current.status_code == 200, current.text

    saved = client.patch(
        "/api/projects/current/draft",
        json=_patch_body(updated_at, **{"project.name": "改名工程"}),
    )
    assert saved.status_code == 200, saved.text
    # project.name 是创建时写入 projects 表的行字段，草稿保存只更新 drafts。
    assert saved.json()["draft"]["project"]["name"] == "改名工程"
    assert saved.json()["updated_at"] != updated_at


def test_unbound_factory_reopens_existing_project_after_restart(tmp_path: Path) -> None:
    """壳重启（未绑定工厂）后重复提交同一目录 → 打开既有项目而非 409。

    桌面壳每次启动都以 project_root=None 创建应用；重启后用户在第 1 步
    重新输入同一项目目录，幂等打开让会话得以恢复。
    """
    project_root = tmp_path / "project"
    first = TestClient(create_builder_app(None))
    created = first.post("/api/projects", json=_create_body(project_root))
    assert created.status_code == 201, created.text
    original_id = created.json()["project"]["id"]

    # 模拟壳重启：全新应用实例 + 全新客户端（仍未绑定根目录）。
    second = TestClient(create_builder_app(None))
    reopened = second.post("/api/projects", json=_create_body(project_root))

    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["opened_existing"] is True
    assert reopened.json()["project"]["id"] == original_id
    # 重开后草稿可保存（创建路径回绑同样适用于打开路径）。
    saved = second.patch(
        "/api/projects/current/draft",
        json=_patch_body(reopened.json()["updated_at"]),
    )
    assert saved.status_code == 200, saved.text
