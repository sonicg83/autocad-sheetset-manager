"""资产纳入用例编排（SPEC-DB-001 §3/§4/§11 / PLAN-DB-001 Task 4）。

流程：校验扩展名与大小 → 复制前后校验大小与 SHA-256（复制中源文件变化
报 ``ASSET_HASH_MISMATCH``）→ 数据库查重 → 原子落盘 → 入库。文件落盘与
数据库写入都在 ``Database.sessions.begin()`` 事务内完成：任一步失败都回滚
并清理已落盘文件，不留“文件无记录”或“记录无文件”的假状态；``(role,
sha256)`` 唯一约束命中时幂等返回既有记录。

``source_name`` 只用于记录展示，绝不参与任何路径拼接；项目内路径一律由
内容寻址名生成，并经 ``domain.paths`` 边界校验。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dst_builder.application.projects import ProjectNotInitializedError
from dst_builder.domain.models import AssetRole
from dst_builder.domain.paths import ProjectPathError, resolve_within_project
from dst_builder.infrastructure.assets.store import (
    MAX_ASSET_BYTES,
    AssetRecord,
    SqliteAssetRepository,
    asset_relative_path,
    file_sha256,
    make_temp_file,
    place_file_atomically,
    stream_copy,
)
from dst_builder.infrastructure.persistence.database import Database

__all__ = [
    "ASSET_FILE_TOO_LARGE",
    "ASSET_HASH_MISMATCH",
    "ASSET_NOT_FOUND",
    "ASSET_OUTSIDE_PROJECT",
    "ASSET_SOURCE_MISSING",
    "ASSET_TYPE_REJECTED",
    "CAD_VERSION_UNAVAILABLE",
    "AssetFileTooLargeError",
    "AssetHashMismatchError",
    "AssetIntake",
    "AssetNotFoundError",
    "AssetOutsideProjectError",
    "AssetServiceError",
    "AssetSourceMissingError",
    "AssetTypeRejectedError",
    "BuilderAssetService",
    "CadInspectionUnavailableError",
    "LayoutInspection",
]

# §4 门禁码：§11 固定清单为“至少”，扩展名与大小上限是 §4 的独立门禁。
ASSET_TYPE_REJECTED = "ASSET_TYPE_REJECTED"
ASSET_FILE_TOO_LARGE = "ASSET_FILE_TOO_LARGE"
ASSET_SOURCE_MISSING = "ASSET_SOURCE_MISSING"
ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
ASSET_HASH_MISMATCH = "ASSET_HASH_MISMATCH"
ASSET_OUTSIDE_PROJECT = "ASSET_OUTSIDE_PROJECT"
# §11 固定码：布局 inspection 端口未接线或 CAD 能力不可用时使用。
CAD_VERSION_UNAVAILABLE = "CAD_VERSION_UNAVAILABLE"

_ALLOWED_SUFFIXES: dict[AssetRole, frozenset[str]] = {
    AssetRole.BASE: frozenset({".dwg"}),
    AssetRole.LAYOUT: frozenset({".dwg", ".dwt"}),
}


class AssetServiceError(Exception):
    """资产用例错误：固定 §11 code + 用户信息 + 恢复动作（形态同项目服务错误）。"""

    code = ASSET_NOT_FOUND

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.recovery_action = self._recovery_action()

    def _recovery_action(self) -> str:  # pragma: no cover - 子类覆盖
        return ""


class AssetTypeRejectedError(AssetServiceError):
    """扩展名不符合 §4 资产规则（base→.dwg；layout→.dwg/.dwt）。"""

    code = ASSET_TYPE_REJECTED

    def _recovery_action(self) -> str:
        return "基础资产必须为 .dwg，布局资产必须为 .dwg 或 .dwt；请更换文件后重试"


class AssetFileTooLargeError(AssetServiceError):
    """源文件超过 §4 单文件 2 GiB 上限。"""

    code = ASSET_FILE_TOO_LARGE

    def _recovery_action(self) -> str:
        return "单个资产文件不得超过 2 GiB；请压缩或拆分后重试"


class AssetSourceMissingError(AssetServiceError):
    """请求引用的源文件不存在。"""

    code = ASSET_SOURCE_MISSING

    def _recovery_action(self) -> str:
        return "确认源文件位置后重试；文件需在本机可读"


class AssetNotFoundError(AssetServiceError):
    """引用的资产记录不存在。"""

    code = ASSET_NOT_FOUND

    def _recovery_action(self) -> str:
        return "重新执行 POST /api/assets 纳入资产后再试"


class AssetHashMismatchError(AssetServiceError):
    """复制前后 SHA-256 不一致：源文件在复制过程中发生了变化。"""

    code = ASSET_HASH_MISMATCH

    def _recovery_action(self) -> str:
        return "源文件在纳入过程中被修改；请关闭占用该文件的程序后重试"


class AssetOutsideProjectError(AssetServiceError):
    """项目内路径越界或大小写碰撞（§3：路径必须位于项目根内）。"""

    code = ASSET_OUTSIDE_PROJECT

    def _recovery_action(self) -> str:
        return "资产只能位于项目根 assets/ 内；清理同名冲突后重试"


class CadInspectionUnavailableError(AssetServiceError):
    """布局 inspection 端口未接线或匹配版本 CAD 不可用。

    裁决（PLAN-DB-001 Task 4）：端口未接线时固定返回 HTTP 501 +
    ``CAD_VERSION_UNAVAILABLE``；真实 CAD 布局读取由 Task 7 接线。
    """

    code = CAD_VERSION_UNAVAILABLE

    def _recovery_action(self) -> str:
        return "需要配置匹配版本的 AutoCAD Core Console 与 Builder 插件后才能读取布局"


@dataclass(frozen=True, slots=True)
class AssetIntake:
    """一次资产纳入请求；``source_name`` 取 ``source_path.name``，仅用于记录。"""

    role: AssetRole
    source_path: Path


class LayoutInspection(Protocol):
    """§11 ``POST /api/assets/{id}/inspect`` 的端口：匹配版本 CAD 读取可用布局。

    Task 7 以真实 CAD 执行器实现本协议并注入应用工厂；在此之前端口保持
    未接线状态，端点固定返回 501（见 ``CadInspectionUnavailableError``）。
    """

    def list_layouts(self, asset: AssetRecord, cad_version: str) -> tuple[str, ...]: ...


class BuilderAssetService:
    """资产纳入、读取与布局 inspection 端口调用。"""

    def __init__(
        self, project_root: str | Path | None, *, max_bytes: int = MAX_ASSET_BYTES
    ) -> None:
        self._project_root = Path(project_root) if project_root is not None else None
        self._max_bytes = max_bytes
        self._database: Database | None = None

    # -- 用例 ---------------------------------------------------------------

    def intake(self, intake: AssetIntake) -> AssetRecord:
        """纳入一个模板资产：复制 → 校验 → 内容寻址落盘 → 入库（幂等去重）。"""
        root = self._require_root()
        # 先校验项目库：未初始化的项目不得在磁盘上留下任何痕迹。
        self._require_database()
        source = intake.source_path
        if not source.is_file():
            raise AssetSourceMissingError(f"源文件不存在：{source}", field="source_path")
        suffix = source.suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES[intake.role]:
            raise AssetTypeRejectedError(
                f"资产扩展名 {suffix!r} 不适用于角色 {intake.role.value}",
                field="source_path",
            )

        pre_size, pre_sha256 = file_sha256(source)
        self._ensure_size(pre_size)

        temp = make_temp_file(root, intake.role)
        try:
            stream_copy(source, temp)
            post_size, post_sha256 = file_sha256(temp)
            if (post_size, post_sha256) != (pre_size, pre_sha256):
                raise AssetHashMismatchError(
                    "源文件在复制过程中发生了变化，纳入已中止"
                )
            relative_path = asset_relative_path(intake.role, post_sha256, suffix)
            self._ensure_within_project(root, relative_path)
            record = AssetRecord(
                id=str(uuid.uuid4()),
                role=intake.role,
                relative_path=relative_path,
                sha256=post_sha256,
                size=post_size,
                source_name=source.name,
            )
            return self._commit(root, intake.role, post_sha256, temp, record)
        finally:
            temp.unlink(missing_ok=True)

    def load_asset(self, asset_id: str) -> AssetRecord:
        database = self._require_database()
        with database.sessions.begin() as session:
            record = SqliteAssetRepository(session).load(asset_id)
        if record is None:
            raise AssetNotFoundError(f"资产不存在：{asset_id}")
        return record

    def inspect_layouts(
        self, asset_id: str, cad_version: str, inspector: LayoutInspection | None
    ) -> tuple[str, ...]:
        """通过 inspection 端口读取可用布局；端口未接线即固定 501 语义。"""
        asset = self.load_asset(asset_id)
        if inspector is None:
            raise CadInspectionUnavailableError(
                "布局 inspection 端口尚未接线：需要匹配版本的 CAD 执行器"
            )
        return inspector.list_layouts(asset, cad_version)

    # -- 内部 ---------------------------------------------------------------

    def _require_root(self) -> Path:
        if self._project_root is None:
            raise ProjectNotInitializedError("未绑定项目根目录")
        return self._project_root

    def _require_database(self) -> Database:
        if self._database is None:
            root = self._require_root()
            db_path = root / "project.dstb"
            if not db_path.is_file():
                raise ProjectNotInitializedError("项目库尚未创建")
            database = Database(db_path)
            database.check_schema()
            self._database = database
        return self._database

    def _ensure_size(self, size: int) -> None:
        if size > self._max_bytes:
            raise AssetFileTooLargeError(
                f"源文件大小 {size} 字节超过上限 {self._max_bytes} 字节"
            )

    @staticmethod
    def _ensure_within_project(root: Path, relative_path: str) -> None:
        try:
            resolve_within_project(root, relative_path)
        except ProjectPathError as error:
            raise AssetOutsideProjectError(str(error)) from error

    def _commit(
        self,
        root: Path,
        role: AssetRole,
        sha256: str,
        temp: Path,
        record: AssetRecord,
    ) -> AssetRecord:
        """在单个事务内完成查重、落盘与入库；任一步失败都不留假状态。"""
        database = self._require_database()
        placed = False
        try:
            with database.sessions.begin() as session:
                repository = SqliteAssetRepository(session)
                try:
                    existing = repository.find_by_role_and_sha256(role, sha256)
                    if existing is not None:
                        final = self._existing_path(root, existing.relative_path)
                        if not final.is_file():
                            # 记录在而文件缺失：用已校验内容重新落盘自愈。
                            place_file_atomically(root, existing.relative_path, temp)
                        return existing
                    place_file_atomically(root, record.relative_path, temp)
                    placed = True
                    repository.insert(record)
                except ProjectPathError as error:
                    raise AssetOutsideProjectError(str(error)) from error
        except BaseException:
            if placed:
                # 数据库提交失败：清理已落盘文件，不留“文件无记录”假状态。
                (root / record.relative_path).unlink(missing_ok=True)
            raise
        return record

    @staticmethod
    def _existing_path(root: Path, relative_path: str) -> Path:
        try:
            return resolve_within_project(root, relative_path)
        except ProjectPathError as error:
            raise AssetOutsideProjectError(str(error)) from error
