"""Builder 产出可被 Manager 直接打开（RFC-INT-002 / SPEC-DB-001 §9）。

正常主路径：Builder 发布到目标目录后，Manager 用既有
``POST /api/workspaces/open`` 打开其中的 DST，从磁盘现状建立工作区与
基线。该测试原为移除交接代码前的安全网，交接实现已随 RFC-INT-002 删除，
现作为该主路径的回归护栏。

放在 ``tests/builder/integration/`` 是为了复用本目录 ``conftest.py`` 的 ``env``
夹具（真实 Builder 发布链路 + fake CAD）；``tests/integration/`` 无法导入该夹具。
``tests/architecture/test_product_boundaries.py`` 只扫描 ``src/``，因此测试文件
同时 import 两个产品包不违反依赖门禁。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.interfaces.api import create_app

SHEETSET_NAME = "sheetset.dst"
DWG_NAME = "A-001 首层平面图.dwg"
CATALOG_NAME = "图纸目录.xlsx"


def _publish(env) -> Path:
    """用真实 Builder 发布链路把三件套写入目标目录，返回目标目录。"""
    plan = env.submit_plan()
    env.confirm_plan(plan["plan_id"])
    build = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    final = env.wait_terminal(build["build_id"])
    assert final["status"] == "SUCCEEDED", final
    assert final["published_path"], final
    assert Path(final["published_path"]) == env.target
    return env.target


def _open_workspace(tmp_path: Path, target: Path) -> dict:
    """Manager 用既有 open 端点打开目标目录中的 DST，返回工作区响应体。"""
    manager = TestClient(create_app(Settings(data_dir=tmp_path / "manager-data")))
    response = manager.post(
        "/api/workspaces/open", json={"dst_path": str(target / SHEETSET_NAME)}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _assert_dwg_resolved_in_target(workspace: dict, target: Path) -> None:
    """工作区以 DST 所在目录为根，且 DWG 按 DST 的相对引用解析到该目录内。"""
    assert Path(workspace["root"]).resolve() == target.resolve()
    layout = workspace["sheet_set"]["subsets"][0]["sheets"][0]["layout"]
    assert layout["resolved_path"], layout
    assert Path(layout["resolved_path"]) == target.resolve() / DWG_NAME
    # 钉住解析机制：Manager 的候选顺序是相对 → 绝对 → 同目录 basename → root_override。
    # 扁平布局下 basename 兜底恰好也能命中同一个文件，只看 resolved_path 无法
    # 区分二者；若 Builder 把 DST 引用写成 `drawings/` 前缀（磁盘仍是扁平布局、
    # 文件也确实存在于同目录），只有本断言能拦住该类回归。
    assert layout["resolution_source"] == "relative", layout
    assert workspace["unreferenced_dwgs"] == []


def test_manager_opens_builder_published_dst(tmp_path: Path, env) -> None:
    target = _publish(env)

    # 扁平布局：三件套直接位于目标目录
    assert sorted(path.name for path in target.iterdir()) == [
        DWG_NAME,
        SHEETSET_NAME,
        CATALOG_NAME,
    ]

    _assert_dwg_resolved_in_target(_open_workspace(tmp_path, target), target)


def test_manager_open_ignores_user_added_files(tmp_path: Path, env) -> None:
    """目标目录是用户的工作目录：额外文件与子目录不得影响 Manager 打开 DST 与解析 DWG 引用。"""
    target = _publish(env)
    (target / "notes.txt").write_text("用户备注", encoding="utf-8")
    (target / "backup").mkdir()
    (target / "backup" / "sheetset.bak").write_bytes(b"bak")

    # 与用例 1 同强度的断言：新增文件后根目录与解析位置都必须不变，
    # 避免「DWG 解析到目标目录之外却恰好返回 200」的回归在这里漏网。
    _assert_dwg_resolved_in_target(_open_workspace(tmp_path, target), target)
