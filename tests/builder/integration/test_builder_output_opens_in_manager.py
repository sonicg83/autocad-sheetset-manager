"""Builder 产出可被 Manager 直接打开（RFC-INT-002 / SPEC-DB-001 §9）。

替代交接契约的新主路径：Builder 发布到目标目录后，Manager 用既有
``POST /api/workspaces/open`` 打开其中的 DST，从磁盘现状建立工作区与
基线。该测试是移除交接代码前的安全网。

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


def _publish(env) -> Path:
    """用真实 Builder 发布链路把三件套写入目标目录，返回目标目录。"""
    plan = env.submit_plan()
    env.confirm_plan(plan["plan_id"])
    build = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    final = env.wait_terminal(build["build_id"])
    assert final["status"] == "SUCCEEDED", final
    assert Path(final["published_path"]) == env.target
    return env.target


def test_manager_opens_builder_published_dst(tmp_path: Path, env) -> None:
    target = _publish(env)

    # 扁平布局：三件套直接位于目标目录
    assert sorted(path.name for path in target.iterdir()) == [
        "A-001 首层平面图.dwg",
        "sheetset.dst",
        "图纸目录.xlsx",
    ]

    manager = TestClient(create_app(Settings(data_dir=tmp_path / "manager-data")))
    response = manager.post(
        "/api/workspaces/open", json={"dst_path": str(target / "sheetset.dst")}
    )
    assert response.status_code == 200, response.text
    workspace = response.json()

    # 工作区以 DST 所在目录为根，并把 DWG 解析到该目录内（键路径见 WorkspaceResponse）
    assert Path(workspace["root"]).resolve() == target.resolve()
    layout = workspace["sheet_set"]["subsets"][0]["sheets"][0]["layout"]
    assert Path(layout["resolved_path"]).parent == target.resolve()
    assert Path(layout["resolved_path"]).name.endswith(".dwg")
    assert workspace["unreferenced_dwgs"] == []


def test_manager_open_ignores_user_added_files(tmp_path: Path, env) -> None:
    """目标目录是用户的工作目录：Manager 打开时不得因额外文件而失败。"""
    target = _publish(env)
    (target / "notes.txt").write_text("用户备注", encoding="utf-8")
    (target / "backup").mkdir()
    (target / "backup" / "sheetset.bak").write_bytes(b"bak")

    manager = TestClient(create_app(Settings(data_dir=tmp_path / "manager-data")))
    response = manager.post(
        "/api/workspaces/open", json={"dst_path": str(target / "sheetset.dst")}
    )
    assert response.status_code == 200, response.text
