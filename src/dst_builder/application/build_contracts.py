"""构建用例契约：固定错误族与结果视图（SPEC-DB-001 §11，PLAN-DB-001 Task 9）。

错误码只使用 §11 固定清单及用例必需的补充码（PLAN_NOT_FOUND 等）；
接口层统一以 ``code``/``message``/``field``/``recovery_action`` 呈现。
"""

from __future__ import annotations

from dataclasses import dataclass

from dst_builder.domain.models import Diagnostic

__all__ = [
    "BUILD_FAILED",
    "AttemptView",
    "BuildAlreadyRunningError",
    "BuildDataIntegrityError",
    "BuildNotFoundError",
    "BuildServiceError",
    "BuildStatusView",
    "BuildTargetExistsError",
    "BuildTargetInvalidError",
    "CancelNotAcceptedError",
    "PlanBlockedError",
    "PlanConfirmation",
    "PlanNotConfirmedError",
    "PlanNotFoundError",
    "PlanPreview",
    "PlanStaleError",
]

# 计划外补充码（§11 为"至少"清单）：意外失败兜底。
BUILD_FAILED = "BUILD_FAILED"


class BuildServiceError(Exception):
    """构建用例错误：固定 §11 code + HTTP 状态码 + 恢复动作。"""

    code = BUILD_FAILED
    status_code = 400

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    @property
    def recovery_action(self) -> str:  # pragma: no cover - 子类覆盖
        return ""


class PlanNotFoundError(BuildServiceError):
    code = "PLAN_NOT_FOUND"
    status_code = 404

    @property
    def recovery_action(self) -> str:
        return "重新执行 POST /api/plans 提交修订后再试"


class PlanNotConfirmedError(BuildServiceError):
    code = "PLAN_NOT_CONFIRMED"
    status_code = 422

    @property
    def recovery_action(self) -> str:
        return "先调用 POST /api/plans/{id}/confirm 显式确认计划"


class PlanStaleError(BuildServiceError):
    code = "PLAN_STALE"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "草稿已变化；重新提交修订并确认计划后再构建"


class PlanBlockedError(BuildServiceError):
    """存在阻断诊断；code 取第一个阻断诊断码。"""

    status_code = 422

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message, field=diagnostic.field)
        self.code = diagnostic.code

    @property
    def recovery_action(self) -> str:
        return "先解决阻断诊断，再提交并确认计划"


class BuildNotFoundError(BuildServiceError):
    code = "BUILD_NOT_FOUND"
    status_code = 404

    @property
    def recovery_action(self) -> str:
        return "确认构建 ID 后重试"


class BuildDataIntegrityError(BuildServiceError):
    code = BUILD_FAILED
    status_code = 500

    @property
    def recovery_action(self) -> str:
        return "项目库构建记录不完整；请保留 project.dstb 并联系维护人员"


class BuildAlreadyRunningError(BuildServiceError):
    code = "BUILD_ALREADY_RUNNING"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "等待当前 attempt 到达终止状态后再启动新 attempt"


class CancelNotAcceptedError(BuildServiceError):
    """终止状态或 PUBLISHING 阶段不响应取消（§6）。"""

    code = "CANCEL_NOT_ACCEPTED"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "PUBLISHING 与终止状态不响应取消；等待构建自行结束"


class BuildTargetExistsError(BuildServiceError):
    """正式目标已存在；首期不覆盖或合并既有目录。"""

    code = "PACKAGE_TARGET_EXISTS"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "更换成果目录或删除既有目录；首期不覆盖既有成果"


class BuildTargetInvalidError(BuildServiceError):
    code = "PROJECT_PATH_INVALID"
    status_code = 400

    @property
    def recovery_action(self) -> str:
        return "确认成果目录父目录存在且可写后重试"


@dataclass(frozen=True, slots=True)
class PlanPreview:
    plan_id: str
    revision_id: str
    revision_sha256: str
    plan_sha256: str
    diagnostics: tuple[Diagnostic, ...]
    preview: dict


@dataclass(frozen=True, slots=True)
class PlanConfirmation:
    plan_id: str
    revision_id: str
    confirmed_at: str


@dataclass(frozen=True, slots=True)
class AttemptView:
    attempt: int
    status: str
    progress: int
    error_code: str | None


@dataclass(frozen=True, slots=True)
class BuildStatusView:
    build_id: str
    plan_id: str
    attempt: int
    status: str
    progress: int
    error_code: str | None
    error_detail: str | None
    published_path: str | None
    created_at: str
    finished_at: str | None
    attempts: tuple[AttemptView, ...]
