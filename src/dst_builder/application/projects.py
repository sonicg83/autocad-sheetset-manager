"""项目与草稿用例编排（SPEC-DB-001 §2/§3/§4/§11）。

事务边界在本层控制：仓储适配器只映射行，所有写操作通过
``Database.sessions.begin()`` 提交。错误以固定 §11 错误码抛出，由接口层
映射为统一错误响应。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from dst_builder.domain.models import (
    DRAFT_SCHEMA_VERSION,
    Diagnostic,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.normalization import canonical_json
from dst_builder.domain.planning import validate_draft
from dst_builder.infrastructure.persistence.database import (
    Database,
    DatabaseSchemaError,
    create_project_database,
    project_database_path,
    utc_now_iso,
)
from dst_builder.infrastructure.persistence.repositories import (
    DraftRecord,
    ProjectRecord,
    ProjectRepository,
    SqliteProjectRepository,
)

__all__ = [
    "DRAFT_CONFLICT",
    "PROJECT_PATH_INVALID",
    "BuilderProjectService",
    "DraftConflictError",
    "DraftPatch",
    "ProjectCreation",
    "ProjectNotInitializedError",
    "ProjectServiceError",
    "ProjectState",
    "draft_from_payload",
    "draft_to_payload",
]

PROJECT_PATH_INVALID = "PROJECT_PATH_INVALID"
DRAFT_CONFLICT = "DRAFT_CONFLICT"

_WIZARD_STEP_MIN = 1
_WIZARD_STEP_MAX = 7


class ProjectServiceError(Exception):
    """用例错误：固定 §11 code + 用户信息 + 恢复动作。"""

    code = PROJECT_PATH_INVALID

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.recovery_action = self._recovery_action()

    def _recovery_action(self) -> str:  # pragma: no cover - 子类覆盖
        return ""


class ProjectNotInitializedError(ProjectServiceError):
    """项目库不存在，只读接口不可用。"""

    code = PROJECT_PATH_INVALID

    def _recovery_action(self) -> str:
        return "先调用 POST /api/projects 创建项目，再读取当前状态"


class DraftConflictError(ProjectServiceError):
    """草稿已被其他保存更新（base_updated_at 过期）。"""

    code = DRAFT_CONFLICT

    def _recovery_action(self) -> str:
        return "重新读取 GET /api/projects/current 获取最新 updated_at 后再保存"


@dataclass(frozen=True, slots=True)
class ProjectCreation:
    name: str
    stage: str
    discipline: str
    output_path: str


@dataclass(frozen=True, slots=True)
class DraftPatch:
    draft: DraftProjectV1
    base_updated_at: str
    wizard_step: int
    focused_field: str | None


@dataclass(frozen=True, slots=True)
class ProjectState:
    project: ProjectRecord
    draft: DraftRecord
    diagnostics: tuple[Diagnostic, ...]


def draft_to_payload(draft: DraftProjectV1) -> dict:
    """§4 草稿 JSON 载荷（trim 后）；键名与契约示例一致。"""
    return {
        "schema_version": draft.schema_version,
        "project": {
            "name": draft.project.name.strip(),
            "stage": draft.project.stage.strip(),
            "discipline": draft.project.discipline.strip(),
            "output_path": draft.project.output_path.strip(),
        },
        "numbering": {
            "prefix": draft.numbering.prefix.strip(),
            "start": draft.numbering.start,
            "width": draft.numbering.width,
        },
        "cad_version": draft.cad_version.strip(),
        "sheets": [{"title": sheet.title.strip()} for sheet in draft.sheets],
        "template": {
            "base_asset_id": draft.template.base_asset_id.strip(),
            "layout_asset_id": draft.template.layout_asset_id.strip(),
            "source_layout": draft.template.source_layout.strip(),
        },
    }


def draft_from_payload(payload: dict) -> DraftProjectV1:
    """由 §4 载荷重建内部草稿；schema 版本不符直接拒绝。"""
    if payload.get("schema_version") != DRAFT_SCHEMA_VERSION:
        raise ValueError("草稿 schema_version 只支持 1")
    return DraftProjectV1(
        project=ProjectInput(
            name=payload["project"]["name"],
            stage=payload["project"]["stage"],
            discipline=payload["project"]["discipline"],
            output_path=payload["project"]["output_path"],
        ),
        numbering=NumberingInput(
            prefix=payload["numbering"]["prefix"],
            start=payload["numbering"]["start"],
            width=payload["numbering"]["width"],
        ),
        cad_version=payload["cad_version"],
        sheets=tuple(SheetInput(title=sheet["title"]) for sheet in payload["sheets"]),
        template=TemplateInput(
            base_asset_id=payload["template"]["base_asset_id"],
            layout_asset_id=payload["template"]["layout_asset_id"],
            source_layout=payload["template"]["source_layout"],
        ),
    )


def _initial_draft(creation: ProjectCreation) -> DraftProjectV1:
    """初始草稿：工程字段来自创建请求，其余留空交由七步引导补全。"""
    return DraftProjectV1(
        project=ProjectInput(
            name=creation.name.strip(),
            stage=creation.stage.strip(),
            discipline=creation.discipline.strip(),
            output_path=creation.output_path.strip(),
        ),
        numbering=NumberingInput(prefix="", start=1, width=3),
        cad_version="2020",
        sheets=(SheetInput(title=""),),
        template=TemplateInput(base_asset_id="", layout_asset_id="", source_layout=""),
    )


def _validate_wizard_step(wizard_step: int) -> int:
    if not _WIZARD_STEP_MIN <= wizard_step <= _WIZARD_STEP_MAX:
        raise ValueError(f"wizard_step 必须在 {_WIZARD_STEP_MIN}～{_WIZARD_STEP_MAX} 之间")
    return wizard_step


class BuilderProjectService:
    """项目库生命周期与当前草稿的用例编排。"""

    def __init__(self, project_root: str | Path | None) -> None:
        self._project_root = Path(project_root) if project_root is not None else None
        self._database: Database | None = None

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    @property
    def database_path(self) -> Path:
        return project_database_path(self._require_root())

    def _require_root(self) -> Path:
        if self._project_root is None:
            raise ProjectNotInitializedError("未绑定项目根目录")
        return self._project_root

    def _require_database(self) -> Database:
        if self._database is None:
            db_path = self.database_path
            if not db_path.is_file():
                raise ProjectNotInitializedError("项目库尚未创建")
            database = Database(db_path)
            try:
                database.check_schema()
            except DatabaseSchemaError as error:
                raise ProjectServiceError(str(error)) from error
            self._database = database
        return self._database

    # -- 用例 ---------------------------------------------------------------

    def create_project(self, creation: ProjectCreation) -> ProjectState:
        root = self._require_root()
        db_path = project_database_path(root)
        if db_path.exists():
            # 幂等语义（创建即打开）：目录已是 Builder 项目时打开既有项目，
            # 不重置草稿、不补建目录；是否为既有项目由响应的 opened_existing 区分。
            return self.load_current()

        create_project_database(db_path)
        (root / "assets").mkdir(exist_ok=True)
        (root / "builds").mkdir(exist_ok=True)

        database = Database(db_path)
        database.check_schema()
        self._database = database

        now = utc_now_iso()
        project = ProjectRecord(
            id=str(uuid.uuid4()),
            name=creation.name.strip(),
            stage=creation.stage.strip(),
            discipline=creation.discipline.strip(),
            output_path=creation.output_path.strip(),
            created_at=now,
            updated_at=now,
        )
        draft = _initial_draft(creation)
        draft_record = DraftRecord(
            project_id=project.id,
            payload_json=canonical_json(draft_to_payload(draft)),
            wizard_step=1,
            focused_field=None,
            updated_at=now,
        )
        with database.sessions.begin() as session:
            repository: ProjectRepository = SqliteProjectRepository(session)
            repository.insert_project(project)
            repository.insert_draft(draft_record)
        return ProjectState(project, draft_record, validate_draft(draft, output_exists=False))

    def load_current(self) -> ProjectState:
        database = self._require_database()
        with database.sessions.begin() as session:
            repository = SqliteProjectRepository(session)
            project = self._require_project(repository)
            draft = self._require_draft(repository, project.id)
        return ProjectState(project, draft, self._diagnostics(draft))

    def save_draft(self, patch: DraftPatch) -> ProjectState:
        database = self._require_database()
        draft = patch.draft
        diagnostics = validate_draft(draft, output_exists=False)
        payload_json = canonical_json(draft_to_payload(draft))
        now = utc_now_iso()
        wizard_step = _validate_wizard_step(patch.wizard_step)

        with database.sessions.begin() as session:
            repository = SqliteProjectRepository(session)
            project = self._require_project(repository)
            updated = repository.update_draft(
                project.id,
                expected_updated_at=patch.base_updated_at,
                payload_json=payload_json,
                wizard_step=wizard_step,
                focused_field=patch.focused_field,
                updated_at=now,
            )
            if not updated:
                raise DraftConflictError("草稿已被其他保存更新；当前写入基于过期版本")
            draft_record = self._require_draft(repository, project.id)
        return ProjectState(project, draft_record, diagnostics)

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _require_project(repository: ProjectRepository) -> ProjectRecord:
        project = repository.load_project()
        if project is None:
            raise ProjectServiceError("项目库缺少 projects 记录")
        return project

    @staticmethod
    def _require_draft(repository: ProjectRepository, project_id: str) -> DraftRecord:
        draft = repository.load_draft(project_id)
        if draft is None:
            raise ProjectServiceError("项目库缺少当前草稿记录")
        return draft

    @staticmethod
    def _diagnostics(draft: DraftRecord) -> tuple[Diagnostic, ...]:
        return validate_draft(draft_from_payload(json.loads(draft.payload_json)), output_exists=False)
