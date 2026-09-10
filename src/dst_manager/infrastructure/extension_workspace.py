"""已登记工作区的只读 DST 解码 reader（PLAN-DM-020 Task 4 / ARCH-DM-006 §6.2）。

为扩展只读快照提供工作区投影来源：从应用数据库**已登记**的
``workspaces`` 行定位当前 DST，再解码投影为领域文档。刻意不调用
``DstManagerService.open_workspace()``（会重算修订并 ``upsert_workspace``
写库）与任何写路径——本模块只做只读查询，不写 DST/DWG、不创建工程内
``.dst-manager/``、不改变工程文件时间戳。

输出值对象 :class:`DecodedWorkspace` 只携带标识、修订哈希与领域文档；
根目录、DST 绝对路径与 ``root_override`` 停留在本模块内部，不进入快照。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dst_manager.domain.models import SheetSetDocument
from dst_manager.infrastructure.acsm_xml import AcsmValidationError, load_acsm
from dst_manager.infrastructure.dst_codec import CodecError, DstCodec
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.infrastructure.persistence.database import WorkspaceRow

__all__ = [
    "DecodedWorkspace",
    "ExtensionWorkspaceReadError",
    "ExtensionWorkspaceReader",
]


class ExtensionWorkspaceReadError(RuntimeError):
    """只读解码失败；``code`` 与扩展平台错误/诊断码封闭词汇对齐。"""

    def __init__(
        self, code: str, message: str, *, params: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.params = dict(params) if params else {}


@dataclass(frozen=True, slots=True)
class DecodedWorkspace:
    """reader 的唯一输出：工作区标识、当前修订哈希与领域投影。"""

    workspace_id: str
    revision_id: str
    document: SheetSetDocument


class ExtensionWorkspaceReader:
    """从已登记 workspace row 解码当前 DST 投影（只读，零副作用）。"""

    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

    def load(self, workspace_id: str) -> DecodedWorkspace:
        row = self._registered_row(workspace_id)
        dst_path = Path(row.dst_path)
        # 与 open_workspace 的投影口径一致：根目录取 DST 所在目录，
        # root_override 沿用登记行；但不重算登记、不写任何行。
        root = dst_path.parent
        override = Path(row.root_override) if row.root_override else None
        document = self._project(workspace_id, dst_path, root, override)
        return DecodedWorkspace(
            workspace_id=row.id,
            revision_id=file_sha256(dst_path),
            document=document,
        )

    def _registered_row(self, workspace_id: str) -> WorkspaceRow:
        with self._sessions() as session:
            row = session.get(WorkspaceRow, workspace_id)
        if row is None:
            raise ExtensionWorkspaceReadError(
                "EXTENSION_NOT_FOUND",
                f"工作区未登记：{workspace_id}",
                params={"workspace_id": workspace_id},
            )
        return row

    @staticmethod
    def _project(
        workspace_id: str,
        dst_path: Path,
        root: Path,
        override: Path | None,
    ) -> SheetSetDocument:
        try:
            acsm = load_acsm(DstCodec().decode_file(dst_path))
            return acsm.project(root, override)
        except (CodecError, AcsmValidationError, OSError) as exc:
            raise ExtensionWorkspaceReadError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"当前 DST 投影不可用：{exc}",
                params={"workspace_id": workspace_id},
            ) from exc
