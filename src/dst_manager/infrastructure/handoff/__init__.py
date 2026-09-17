"""交接验证基础设施包（SPEC-DB-001 §10，PLAN-DB-001 Task 10）。"""

from dst_manager.infrastructure.handoff.reader import (
    HandoffPackage,
    HandoffPackageError,
    read_handoff_package,
)

__all__ = ["HandoffPackage", "HandoffPackageError", "read_handoff_package"]
