"""dst_platform.autocad：AutoCAD Core Console 进程原语（跨产品共享，无产品包依赖）。"""

from dst_platform.autocad.process import (
    CoreConsoleExecutor,
    CoreConsoleRequest,
    CoreConsoleResult,
)

__all__ = ["CoreConsoleExecutor", "CoreConsoleRequest", "CoreConsoleResult"]
