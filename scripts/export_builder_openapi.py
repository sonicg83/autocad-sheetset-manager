"""导出 DST Builder OpenAPI 规范到 builder-web/src/api/openapi.json。

用法：``uv run python scripts/export_builder_openapi.py``

只写 Builder 前端（builder-web/）的目标文件；绝不改写 Manager 前端的
``web/src/api/openapi.json``（内置守卫）。
"""

from __future__ import annotations

import json
from pathlib import Path

from dst_builder.interfaces.api import create_builder_app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TARGET = _REPO_ROOT / "builder-web" / "src" / "api" / "openapi.json"
_FORBIDDEN = _REPO_ROOT / "web" / "src" / "api" / "openapi.json"


def main() -> None:
    if _TARGET.resolve() == _FORBIDDEN.resolve():
        raise SystemExit("禁止改写 Manager 的 web/src/api/openapi.json")

    spec = create_builder_app().openapi()
    _TARGET.parent.mkdir(parents=True, exist_ok=True)
    _TARGET.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(_TARGET)


if __name__ == "__main__":
    main()
