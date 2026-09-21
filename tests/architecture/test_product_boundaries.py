"""跨产品依赖门禁：AST 静态扫描 src 下产品包的 import 语句。

冻结禁止关系（PLAN-DB-001 Task 1 引入；Builder 归档后仅保留平台规则）：
1. dst_platform 不得依赖任何产品包（dst_manager）或框架。
"""

import ast
from pathlib import Path

import pytest

import dst_platform  # noqa: F401

SRC_DIR = Path(__file__).resolve().parents[2] / "src"

# (说明, 相对 src 的包目录, 禁止的顶层依赖名)
FORBIDDEN_RELATIONS = [
    (
        "dst_platform 不得依赖任何产品包或框架",
        "dst_platform",
        {"dst_manager", "fastapi", "sqlalchemy"},
    ),
]


def _imported_top_levels(path: Path) -> set[str]:
    """返回一个 Python 文件 import 的顶层包名集合（含相对导入解析）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    top_levels: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top_levels.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # 相对导入不会跨出所属顶层包，直接取文件相对 src 的首段。
                top_levels.add(path.relative_to(SRC_DIR).parts[0])
            elif node.module:
                top_levels.add(node.module.split(".")[0])
    return top_levels


@pytest.mark.parametrize(
    ("description", "package_dir", "forbidden"),
    FORBIDDEN_RELATIONS,
    ids=[item[0] for item in FORBIDDEN_RELATIONS],
)
def test_forbidden_dependencies(
    description: str, package_dir: str, forbidden: set[str]
) -> None:
    """被扫描包内的任何 .py 文件都不得 import 禁止的顶层依赖。"""
    package = SRC_DIR / package_dir
    assert package.is_dir(), f"缺少包目录：{package}"

    violations: list[str] = []
    for py_file in sorted(package.rglob("*.py")):
        imported = _imported_top_levels(py_file)
        bad = sorted(imported & forbidden)
        if bad:
            violations.append(f"{py_file.relative_to(SRC_DIR)}: {bad}")

    assert not violations, f"{description} 被违反 -> " + "; ".join(violations)


def test_gate_rules_cover_expected_relations() -> None:
    """门禁规则本身不得被静默清空。"""
    assert len(FORBIDDEN_RELATIONS) >= 1
    assert all(item[2] for item in FORBIDDEN_RELATIONS)
    # dst_platform 的禁止集须与计划元组一致。
    assert {"dst_manager", "fastapi", "sqlalchemy"} <= (
        FORBIDDEN_RELATIONS[0][2]
    )


def test_imported_top_levels_detects_real_imports() -> None:
    """检测器对真实 import 形态必须有产出，防止扫描器恒空导致门禁虚绿。"""
    source = (
        "import dst_manager\n"
        "import fastapi.staticfiles\n"
        "from lxml import etree\n"
        "from . import sibling\n"
        "from ..domain import models\n"
    )
    probe = SRC_DIR / "dst_platform" / "_gate_probe.py"
    probe.write_text(source, encoding="utf-8")
    try:
        imported = _imported_top_levels(probe)
    finally:
        probe.unlink()

    assert imported == {
        "dst_platform",  # 两条相对导入
        "dst_manager",
        "fastapi",
        "lxml",
    }
