"""设置中心 e2e 后端启动器（PLAN-DM-019 任务 10 测试夹具，非生产代码）。

`dst-manager serve` 走模块级 ``create_app()``（不注入 RuntimeSettings，设置端点
不注册——该降级是 ARCH-DM-014 计划裁决，生产仅桌面壳入口注入）。而任务 10 的
契约红线要求 e2e 真实打后端（不 mock /api/settings），故本夹具按桌面壳
（interfaces/shell.py run_desktop）的同一装配方式构造应用并启动 HTTP 服务：

    create_app(Settings(), runtime_settings=RuntimeSettings(default_store()))

``DST_MANAGER_SETTINGS_PATH`` 由 Playwright 全局 setup 注入，default_store()
据此把 settings.json 指向测试隔离目录。

用法：uv run python tests/e2e/serve_backend.py --port 9001 --run-id e2e-settings
"""

from __future__ import annotations

import argparse
import os

import uvicorn

from dst_manager.config import Settings
from dst_manager.interfaces.api import create_app
from dst_manager.settings.runtime import RuntimeSettings, default_store


def main() -> None:
    parser = argparse.ArgumentParser(description="设置中心 e2e 后端（注入 RuntimeSettings）")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--run-id", default="e2e-settings")
    args = parser.parse_args()
    if args.run_id:
        os.environ["DST_MANAGER_RUN_ID"] = args.run_id

    # 与桌面壳 run_desktop 相同的装配：快照持有者单例注入，API 可读写设置
    app = create_app(Settings(), runtime_settings=RuntimeSettings(default_store()))
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
