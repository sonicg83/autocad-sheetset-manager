"""导出或校验 DST Builder OpenAPI 规范。

用法：``uv run python scripts/export_builder_openapi.py [--check] [--output PATH]``

只写 Builder 前端（builder-web/）的目标文件；绝不改写 Manager 前端的
``web/src/api/openapi.json``（内置守卫）。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from dst_builder.interfaces.api import create_builder_app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TARGET = _REPO_ROOT / "builder-web" / "src" / "api" / "openapi.json"
_FORBIDDEN = _REPO_ROOT / "web" / "src" / "api" / "openapi.json"


def rendered_schema() -> str:
    return json.dumps(create_builder_app().openapi(), ensure_ascii=False, indent=2) + "\n"


def _is_forbidden_output(output: Path) -> bool:
    forbidden = _FORBIDDEN.resolve()
    if output == forbidden:
        return True
    try:
        return output.is_file() and forbidden.is_file() and output.samefile(forbidden)
    except OSError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=_TARGET)
    arguments = parser.parse_args(argv)
    output = arguments.output.resolve()
    if _is_forbidden_output(output):
        raise SystemExit("禁止改写 Manager 的 web/src/api/openapi.json")

    rendered = rendered_schema()
    if arguments.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI 契约已漂移：{output}")
            return 1
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
