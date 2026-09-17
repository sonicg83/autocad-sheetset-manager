"""跨产品共享诊断模型（所有权自 ``dst_manager.domain.models`` 迁入）。

``Severity`` 与 ``ValidationIssue`` 是 DST 契约诊断的权威类型：
Manager domain 与 Builder 都消费本模块定义的**同一类型对象**，
不得再各自复制第二套诊断模型（PLAN-DB-001 Task 6）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["Severity", "ValidationIssue"]


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    object_id: str | None = None
    location: str | None = None
