"""Manager 显式交接编排（SPEC-DB-001 §10，PLAN-DB-001 Task 10）。

``HandoffOperations`` 以 mixin 组合进 ``DstManagerService``：
:meth:`open_handoff` 先以 :mod:`dst_manager.infrastructure.handoff.reader`
完成 §10 步骤 1-3 的全部只读验证（任何失败零写入），通过后才创建修订
目录证据（步骤 5）并以单事务写库（步骤 4），最后返回工作区与初始修订
信息（步骤 6）。幂等键是 ``package_id``：相同 package_id + 相同 manifest
哈希重复交接返回同一工作区与初始修订；不同哈希抛 ``HANDOFF_ID_CONFLICT``。
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.filesystem.publish_primitives import file_sha256
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.handoff.reader import (
    HandoffPackage,
    HandoffPackageError,
    read_handoff_package,
)

__all__ = ["HANDOFF_INITIAL_KIND", "HANDOFF_SOURCE_SCHEMA", "HandoffOperations"]

HANDOFF_INITIAL_KIND = "handoff_initial"
HANDOFF_SOURCE_SCHEMA = "dst-manager.handoff-source/v1"
HANDOFF_REVISION_MANIFEST_SCHEMA = "dst-manager.handoff-revision/v1"
HANDOFF_EVIDENCE_FILES = ("metadata/manifest.json", "metadata/handoff.json")


def _invalid(message: str) -> ApplicationError:
    return ApplicationError("HANDOFF_INVALID", message, 422)


def _conflict(package_id: str) -> ApplicationError:
    return ApplicationError(
        "HANDOFF_ID_CONFLICT",
        f"同一成果包标识已绑定不同内容，拒绝重复交接：{package_id}",
        409,
        params={"package_id": package_id},
    )


class HandoffOperations:
    def open_handoff(self, handoff_path: Path) -> dict[str, Any]:
        package = self._read_package(handoff_path)
        root: Path = package.root
        dst_path = package.dst_path
        workspace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(dst_path).casefold()))

        # 幂等 / 冲突短路：不产生任何文件或数据库写入
        existing = self.database.get_handoff_source(package.package_id)
        if existing is not None:
            if existing["manifest_sha256"] != package.manifest_sha256:
                raise _conflict(package.package_id)
            revision = self.database.get_revision(existing["revision_id"])
            if revision is None:
                raise ApplicationError(
                    "HANDOFF_INVALID",
                    "交接来源记录存在但初始修订缺失，Manager 数据库状态不一致",
                    409,
                )
            return self._response(package, existing["workspace_id"], revision, idempotent=True)

        operation_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"dst-manager:handoff:{package.package_id}")
        )
        revision_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"dst-manager:handoff-revision:{package.package_id}")
        )
        revision_dir = root / ".dst-manager" / "revisions" / operation_id / "attempt-001"
        source_json = self._source_summary(package)

        created_dir = self._ensure_revision_directory(package, revision_dir, source_json)
        status, registered = self.database.register_handoff(
            package_id=package.package_id,
            workspace_id=workspace_id,
            root=root,
            dst_path=dst_path,
            revision_id=revision_id,
            operation_id=operation_id,
            before_hash=package.dst_sha256,
            result_hash=package.dst_sha256,
            revision_dir=revision_dir,
            source_json=source_json,
            manifest_sha256=package.manifest_sha256,
            build_id=package.build_id,
            plan_id=package.plan_id,
            handoff_path=str(package.handoff_path),
            # Manager 语义：工作区当前修订 = DST 内容哈希（与 open_workspace 一致）
            current_revision=package.dst_sha256,
        )
        if status == "exists":
            # 并发重复交接；哈希不同的冲突路径不得留下本次新建的证据目录
            if registered["manifest_sha256"] != package.manifest_sha256:
                if created_dir:
                    shutil.rmtree(revision_dir.parent, ignore_errors=True)
                raise _conflict(package.package_id)
            revision = self.database.get_revision(registered["revision_id"])
            if revision is None:  # pragma: no cover - 同事务刚提交
                raise ApplicationError("HANDOFF_INVALID", "交接来源记录存在但初始修订缺失", 409)
            return self._response(package, registered["workspace_id"], revision, idempotent=True)

        # 接管标记：workspace.json（尽力而为，失败不影响已闭环的数据库状态）
        try:
            write_workspace_metadata(root, workspace_id, dst_path, revision_id, "2020")
        except OSError:  # pragma: no cover - 磁盘故障仅在下次打开时重新生成
            pass
        revision = self.database.get_revision(revision_id)
        assert revision is not None  # pragma: no cover - 同事务刚提交
        return self._response(package, workspace_id, revision, idempotent=False)

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _read_package(handoff_path: Path) -> HandoffPackage:
        try:
            return read_handoff_package(Path(handoff_path))
        except HandoffPackageError as error:
            raise _invalid(str(error)) from error

    @staticmethod
    def _source_summary(package: HandoffPackage) -> str:
        payload = {
            "schema": HANDOFF_SOURCE_SCHEMA,
            "package_id": package.package_id,
            "build_id": package.build_id,
            "plan_id": package.plan_id,
            "manifest_sha256": package.manifest_sha256,
            "dst_relative": package.dst_relative,
            "dst_sha256": package.dst_sha256,
            "handoff_path": str(package.handoff_path),
            "builder_version": package.builder_version,
            "handoff_created_at": package.created_at,
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def _ensure_revision_directory(
        self,
        package: HandoffPackage,
        revision_dir: Path,
        source_json: str,
    ) -> bool:
        """创建（或复用崩溃残留的）修订证据目录；返回是否本次新建。

        布局：``attempt-001/{manifest.json, drawings/..., metadata/...}``。
        ``manifest.json`` 满足 Manager 修订读取/恢复所需结构（journal 形态
        的 files 条目，backup 指向修订目录内基线副本），status 不是
        ``COMMITTED``，启动恢复的已提交清单枚举会跳过它。
        """
        if revision_dir.exists():
            self._reuse_existing_revision_directory(package, revision_dir)
            if not (revision_dir / "manifest.json").is_file():
                self._write_revision_manifest(package, revision_dir, source_json)
            return False
        operation_dir = revision_dir.parent
        staging = operation_dir / f".staging-{uuid.uuid4().hex}"
        try:
            for entry in (*package.drawing_entries, *package.metadata_entries):
                self._copy_verified(package.root, entry["path"], staging / entry["path"])
            for relative in HANDOFF_EVIDENCE_FILES:
                self._copy_verified(package.root, relative, staging / relative)
            operation_dir.mkdir(parents=True, exist_ok=True)
            staging.rename(revision_dir)
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self._write_revision_manifest(package, revision_dir, source_json)
        return True

    @staticmethod
    def _copy_verified(source_root: Path, relative: str, destination: Path) -> None:
        """复制包内已验证文件并在暂存区复核哈希，失败即整体放弃。"""
        import hashlib

        destination.parent.mkdir(parents=True, exist_ok=True)
        source = source_root / relative
        shutil.copy2(source, destination)
        digest = hashlib.sha256()
        with destination.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != file_sha256(source):
            raise OSError(f"交接基线副本哈希不符：{relative}")

    @staticmethod
    def _reuse_existing_revision_directory(package: HandoffPackage, revision_dir: Path) -> None:
        """崩溃残留（目录已改名、数据库未提交）时复用：副本必须与包一致。"""
        manifest_path = revision_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise _invalid("交接修订目录已存在且清单不可读，请检查 .dst-manager 状态") from error
            handoff_block = manifest.get("handoff")
            if (
                manifest.get("kind") != HANDOFF_INITIAL_KIND
                or not isinstance(handoff_block, dict)
                or handoff_block.get("package_id") != package.package_id
                or handoff_block.get("manifest_sha256") != package.manifest_sha256
            ):
                raise _invalid("交接修订目录已存在且来源不符，拒绝复用")
            return
        # manifest 尚未写出（改名字与写清单之间崩溃）：核对副本哈希后补写。
        for entry in (*package.drawing_entries, *package.metadata_entries):
            copy = revision_dir / entry["path"]
            if not copy.is_file() or file_sha256(copy) != entry["sha256"]:
                raise _invalid("交接修订目录副本不完整，请检查 .dst-manager 状态")
        for relative in HANDOFF_EVIDENCE_FILES:
            copy = revision_dir / relative
            source = package.root / relative
            if not copy.is_file() or file_sha256(copy) != file_sha256(source):
                raise _invalid("交接修订目录副本不完整，请检查 .dst-manager 状态")

    @staticmethod
    def _write_revision_manifest(
        package: HandoffPackage, revision_dir: Path, source_json: str
    ) -> None:
        """修订清单：drawings/ 基线的可恢复条目 + 交接来源摘要。

        身份字段（baseline/before/staged/result identity）在改名后按最终
        文件捕获，保证恢复预览的 source_conflict 比较自洽。
        """
        from dst_manager.infrastructure.filesystem.publish_primitives import (
            file_identity,
        )

        files = []
        for entry in package.drawing_entries:
            backup = revision_dir / entry["path"]
            identity = file_identity(backup)
            files.append(
                {
                    "target": str(package.root / entry["path"]),
                    "staged": str(backup),
                    "backup": str(backup),
                    "before_hash": entry["sha256"],
                    "staged_hash": entry["sha256"],
                    "result_hash": entry["sha256"],
                    "baseline_identity": identity,
                    "before_identity": identity,
                    "staged_identity": identity,
                    "result_identity": identity,
                }
            )
        manifest = {
            "schema": HANDOFF_REVISION_MANIFEST_SCHEMA,
            "kind": HANDOFF_INITIAL_KIND,
            "identity_version": 1,
            "operation_id": revision_dir.parent.name,
            "attempt": 1,
            "status": HANDOFF_INITIAL_KIND,
            "handoff": json.loads(source_json),
            "files": files,
        }
        atomic_write_text(
            revision_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _response(
        package: HandoffPackage, workspace_id: str, revision: dict[str, Any], *, idempotent: bool
    ) -> dict[str, Any]:
        return {
            "handoff_path": str(package.handoff_path),
            "workspace_id": workspace_id,
            "root": str(package.root),
            "dst_path": str(package.dst_path),
            "revision_id": revision["id"],
            "revision_dir": revision["revision_dir"],
            "kind": revision["kind"],
            "package_id": package.package_id,
            "build_id": package.build_id,
            "plan_id": package.plan_id,
            "manifest_sha256": package.manifest_sha256,
            "dst_sha256": package.dst_sha256,
            "idempotent": idempotent,
        }
