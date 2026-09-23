"""创建候选成果的对外值类型与稳定错误（PLAN-DM-036 Task 5）。

暂存运行器（:mod:`dst_manager.application.creation_job`）按这些名字产出结果与
失败码，新项目发布事务与系统测试也只消费这里的形状：候选物只含**隔离 attempt
中的暂存路径**与最终名字，不含目标项目目录里的任何文件。

本模块只有冻结值类型与错误类型，不含流程逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CreationCandidate",
    "CreationJobError",
    "CreationValidationReport",
    "StagedDrawing",
]


class CreationJobError(RuntimeError):
    """创建暂存失败：``code`` 为稳定错误码，消息以该码开头。"""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class StagedDrawing:
    """一个图纸组的主 DWG 候选：暂存文件与它在目标目录中的最终文件名。"""

    group_id: str
    staged_path: Path
    file_name: str


@dataclass(frozen=True, slots=True)
class CreationValidationReport:
    """候选校验报告：全部校验通过才会产出候选（失败即抛出，不留半成品）。

    ``repair_status`` 与 ``semantic_issue_codes`` 是 DST 编码往返后重新加载的实测
    结果（前者必须为 ``VALID``、后者必须为空）；``encoded_sha256`` 是暂存 DST 的
    内容哈希，供发布事务登记结果基准。
    """

    repair_status: str
    semantic_issue_codes: tuple[str, ...]
    encoded_sha256: str
    dwg_count: int
    sheet_count: int


@dataclass(frozen=True, slots=True)
class CreationCandidate:
    """隔离 attempt 中的候选成果：DST、每组主 DWG、布局/Handle 清单与校验报告。

    只含暂存路径与最终名字，**不含目标目录里的任何文件**：把候选发布到目标目录
    由新项目发布事务承担。``layouts``/``handles`` 以图纸 AcSm ID 为键、按计划
    顺序排列。
    """

    job_id: str
    attempt: int
    attempt_dir: Path
    target_path: str
    dst_name: str
    dst_path: Path
    dwgs: tuple[StagedDrawing, ...]
    layouts: dict[str, str]
    handles: dict[str, str]
    report: CreationValidationReport
