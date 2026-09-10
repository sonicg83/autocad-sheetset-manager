"""宿主原子成果发布（PLAN-DM-020 Task 8 / ARCH-DM-006 §9.2）。

扩展只把候选 XLSX 写进宿主临时目录（``ArtifactProposalDirectory``），最终落盘
由宿主完成：目标目录内唯一临时文件 → 复制 → flush → 尽力 fsync → 重新核对
保存授权基线 → ``os.replace`` 原子替换 → 计算最终哈希/大小并登记 Artifact。

失败语义（§9.2 第 7 条 / §14）：任一步失败清理目标临时文件、旧目标字节保持
（``os.replace`` 之前失败）或新目标不存在、不登记成功 Artifact；错误按
``ARTIFACT_WRITE_FAILED`` / ``EXPORT_DESTINATION_CHANGED`` 契约化。日志只关联
调用身份（invocation/扩展 ID/版本/workspace/来源修订/artifact ID），绝不记录
求值属性值或完整输出路径。

**已知窗口（Ruling-10 接受并显式钉住，记入 Task 12 G9 清单）**：``os.replace``
成功之后、Artifact 插入失败（``register-artifact`` 阶段）时，用户目标已是
完整的新文件（非半文件，用户可见结果正确），但后台元数据缺失——即该阶段的
失败语义是"文件已保存但未登记"，与其余阶段"旧目标字节保持或新目标不存在"
不同。不做回滚也不预登记：计划全局约束明文"Artifact 只有最终原子保存成功后
才能登记"，预登记+事后确认违反该约束；运维可凭失败日志中的调用身份
（invocation/扩展 ID/版本/workspace/来源修订 + stage=register-artifact）做
reconciliation。
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from dst_manager.extensions.save_grants import ConsumedSaveGrant, capture_baseline
from dst_manager.infrastructure.persistence.extensions import (
    ArtifactRecord,
    ExtensionStore,
)

__all__ = ["ArtifactExportError", "ArtifactExporter", "ArtifactMetadata"]

logger = logging.getLogger(__name__)

_HASH_CHUNK = 1 << 20

#: 发布各阶段的稳定标识（仅进入日志 ``stage`` 字段，不含用户数据）。
_STAGE_VALIDATE = "validate-candidate"
_STAGE_TEMP = "create-temp"
_STAGE_COPY = "copy"
_STAGE_MEASURE = "measure"
_STAGE_BASELINE = "baseline"
_STAGE_REPLACE = "replace"
_STAGE_REGISTER = "register-artifact"


class ArtifactExportError(RuntimeError):
    """发布失败；``code`` 与 ARCH-DM-006 §12 平台错误码对齐。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    extension_id: str
    extension_version: str
    workspace_id: str
    source_revision_id: str
    kind: Literal["sheet-catalog"]
    media_type: Literal[
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]


def _flush(stream) -> None:
    """把用户态缓冲刷入内核（模块级以便故障注入）。"""
    stream.flush()


def _fsync(stream) -> None:
    """模块级 fsync（平台能力差异的容错在调用侧，便于故障注入）。"""
    os.fsync(stream.fileno())


def _copy_candidate(candidate: Path, temp_path: Path) -> None:
    with candidate.open("rb") as src, temp_path.open("wb") as dst:
        try:
            shutil.copyfileobj(src, dst)
            _flush(dst)
        except OSError as exc:
            raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "候选成果复制失败") from exc
        # 尽力落盘在复制错误包装之外：平台/文件系统不支持 fsync 时容忍失败，
        # 不阻断发布，也不得被上面的 except OSError 误判为复制失败。
        try:
            _fsync(dst)
        except OSError:
            pass


def _measure(path: Path) -> tuple[int, str]:
    """计算最终文件大小与 SHA-256（内容与 replace 后的目标一致）。"""
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(_HASH_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "成果哈希计算失败") from exc
    return size, digest.hexdigest()


def _create_temp(target: Path) -> Path:
    """在目标目录创建唯一临时文件（同卷，保证 ``os.replace`` 原子性）。"""
    try:
        handle, name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".part"
        )
        os.close(handle)
    except OSError as exc:
        raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "目标目录不可写") from exc
    return Path(name)


class ArtifactExporter:
    """把扩展候选成果原子发布到用户目标并登记 Artifact。

    ``invocation_id`` 由调用方（Task 9 的动作执行编排）按次提供；``validator``
    是宿主候选回读校验钩子（SPEC-DM-012 §9，Task 9 接线），抛出即按
    ``ARTIFACT_WRITE_FAILED`` 拒绝发布。
    """

    def __init__(
        self,
        store: ExtensionStore,
        *,
        invocation_id: str = "",
        candidate_validator: Callable[[Path], None] | None = None,
    ) -> None:
        self._store = store
        self._invocation_id = invocation_id
        self._candidate_validator = candidate_validator

    def publish(
        self, grant: ConsumedSaveGrant, candidate: Path, metadata: ArtifactMetadata
    ) -> ArtifactRecord:
        candidate = Path(candidate)
        temp_path: Path | None = None
        stage = _STAGE_VALIDATE
        try:
            self._validate_candidate(candidate)
            stage = _STAGE_TEMP
            temp_path = _create_temp(grant.target)
            stage = _STAGE_COPY
            _copy_candidate(candidate, temp_path)
            stage = _STAGE_MEASURE
            size_bytes, sha256 = _measure(temp_path)
            stage = _STAGE_BASELINE
            self._verify_baseline(grant)
            record = ArtifactRecord(
                artifact_id=uuid.uuid4().hex,
                extension_id=metadata.extension_id,
                extension_version=metadata.extension_version,
                workspace_id=metadata.workspace_id,
                source_revision_id=metadata.source_revision_id,
                kind=metadata.kind,
                media_type=metadata.media_type,
                management_relation="external",
                output_path=str(grant.target),
                file_name=grant.target.name,
                size_bytes=size_bytes,
                sha256=sha256,
                created_at=datetime.now(UTC),
            )
            stage = _STAGE_REPLACE
            os.replace(temp_path, grant.target)
            temp_path = None  # 已被 replace 原子消费，不可再清理
            stage = _STAGE_REGISTER
            self._store.create_artifact(record)
        except ArtifactExportError as exc:
            self._log_failure(exc.code, metadata, stage)
            raise
        except Exception as exc:
            # 仓储/环境层失败统一契约化为 ARTIFACT_WRITE_FAILED；
            # 原始诊断只留类型名，避免把含路径的异常文本写进普通日志。
            self._log_failure("ARTIFACT_WRITE_FAILED", metadata, stage)
            raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "成果发布失败") from exc
        finally:
            # 任一步失败（replace 之前/之中）都清理目标临时文件，不留半写 XLSX。
            if temp_path is not None:
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)
        logger.info(
            "EXTENSION_ARTIFACT_PUBLISHED invocation_id=%s extension_id=%s "
            "extension_version=%s workspace_id=%s source_revision_id=%s "
            "artifact_id=%s file_name=%s size_bytes=%d",
            self._invocation_id,
            metadata.extension_id,
            metadata.extension_version,
            metadata.workspace_id,
            metadata.source_revision_id,
            record.artifact_id,
            grant.target.name,
            record.size_bytes,
        )
        return record

    def _validate_candidate(self, candidate: Path) -> None:
        if not candidate.is_file():
            raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "候选成果不存在")
        if self._candidate_validator is None:
            return
        try:
            self._candidate_validator(candidate)
        except Exception as exc:
            raise ArtifactExportError("ARTIFACT_WRITE_FAILED", "候选成果验证失败") from exc

    @staticmethod
    def _verify_baseline(grant: ConsumedSaveGrant) -> None:
        if capture_baseline(grant.target) != grant.baseline:
            raise ArtifactExportError(
                "EXPORT_DESTINATION_CHANGED", "保存目标在选择后发生了变化"
            )

    def _log_failure(self, code: str, metadata: ArtifactMetadata, stage: str) -> None:
        logger.warning(
            "EXTENSION_ARTIFACT_PUBLISH_FAILED invocation_id=%s extension_id=%s "
            "extension_version=%s workspace_id=%s source_revision_id=%s "
            "stage=%s code=%s",
            self._invocation_id,
            metadata.extension_id,
            metadata.extension_version,
            metadata.workspace_id,
            metadata.source_revision_id,
            stage,
            code,
        )
