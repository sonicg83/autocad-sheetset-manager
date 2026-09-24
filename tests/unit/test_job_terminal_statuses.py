"""任务终态集合的单一来源与前后端一致性（PLAN-DM-036 Task 9）。

后端 `TERMINAL_JOB_STATUSES`（`infrastructure/persistence/database.py`）是任务终态的唯一
来源：SSE 事件流的终止判定必须复用它（曾经漏掉创建任务可终局的 `NEEDS_REVIEW`），前端
`web/src/composables/useJobMonitor.ts` 导出的 `TERMINAL_JOB_STATUSES` 必须与它逐项相同——
创建域的任务监视器（`features/creation/useCreationJob.ts`）复用前端那一份，不再另写集合。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from dst_manager.infrastructure.persistence.database import TERMINAL_JOB_STATUSES
from dst_manager.interfaces import api as api_module

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_MONITOR = REPO_ROOT / "web" / "src" / "composables" / "useJobMonitor.ts"


def frontend_terminal_statuses() -> set[str]:
    """从 `useJobMonitor.ts` 的 `TERMINAL_JOB_STATUSES` 字面量解析终态集合。"""
    source = FRONTEND_MONITOR.read_text(encoding="utf-8")
    match = re.search(
        r"export const TERMINAL_JOB_STATUSES\s*=\s*\[(.*?)\]", source, re.DOTALL
    )
    assert match is not None, "前端必须导出唯一的任务终态集合 TERMINAL_JOB_STATUSES"
    return set(re.findall(r'"([A-Z_]+)"', match.group(1)))


def test_sse_event_stream_reuses_the_shared_terminal_set() -> None:
    """SSE 终止判定必须用共享常量：内联集合漏状态时没有任何门禁能发现。"""
    source = inspect.getsource(api_module)
    assert 'in TERMINAL_JOB_STATUSES' in source
    assert '{"SUCCEEDED", "FAILED", "ROLLED_BACK", "BLOCKED_FILE_LOCK"}' not in source


def test_frontend_terminal_set_matches_backend() -> None:
    """前后端终态集合逐项相同（创建任务可终局于 NEEDS_REVIEW）。"""
    assert frontend_terminal_statuses() == set(TERMINAL_JOB_STATUSES)
    assert "NEEDS_REVIEW" in TERMINAL_JOB_STATUSES
