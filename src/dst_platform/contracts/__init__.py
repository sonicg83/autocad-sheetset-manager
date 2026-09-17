"""跨产品共享契约层：不得依赖任何产品包（dst_builder / dst_manager）。"""

from dst_platform.contracts.diagnostics import Severity as Severity
from dst_platform.contracts.diagnostics import ValidationIssue as ValidationIssue

__all__ = ["Severity", "ValidationIssue"]
