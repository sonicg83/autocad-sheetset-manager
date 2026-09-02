"""导出或校验 DST Manager 的确定性 OpenAPI 契约。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "web" / "src" / "api" / "openapi.json"


def rendered_schema() -> str:
    previous_data_dir = os.environ.get("DST_MANAGER_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="dst-manager-openapi-") as temporary_directory:
        os.environ["DST_MANAGER_DATA_DIR"] = temporary_directory
        from dst_manager.interfaces.api import app

        try:
            schema = app.openapi()
        finally:
            app.state.service.database.engine.dispose()
    if previous_data_dir is None:
        os.environ.pop("DST_MANAGER_DATA_DIR", None)
    else:
        os.environ["DST_MANAGER_DATA_DIR"] = previous_data_dir
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
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
