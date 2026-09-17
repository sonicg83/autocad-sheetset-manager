"""跨产品依赖门禁：AST 静态扫描 src 下产品包的 import 语句。

冻结三条禁止关系（PLAN-DB-001 Task 1）：
1. dst_builder 不得依赖 dst_manager；
2. dst_platform 不得依赖任何产品包（dst_builder / dst_manager）；
3. dst_builder.domain 不得依赖框架（领域层纯净）。
"""

import ast
from pathlib import Path

import pytest

import dst_builder  # noqa: F401
import dst_platform  # noqa: F401

SRC_DIR = Path(__file__).resolve().parents[2] / "src"

# (说明, 相对 src 的包目录, 禁止的顶层依赖名)
FORBIDDEN_RELATIONS = [
    (
        "dst_builder 不得依赖 dst_manager",
        "dst_builder",
        {"dst_manager"},
    ),
    (
        "dst_platform 不得依赖任何产品包",
        "dst_platform",
        {"dst_builder", "dst_manager"},
    ),
    (
        "dst_builder.domain 不得依赖框架",
        "dst_builder/domain",
        {"fastapi", "sqlalchemy", "uvicorn", "pywebview", "typer"},
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
    assert len(FORBIDDEN_RELATIONS) == 3
    assert all(item[2] for item in FORBIDDEN_RELATIONS)
