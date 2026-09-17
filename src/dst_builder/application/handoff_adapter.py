"""Manager 交接适配器的 HTTP 传输原语（SPEC-DB-001 §10/§11，Task 10）。

Builder 不共享 Manager 数据库：“一键交接”是对本机 Manager API 的显式
调用。本模块只承载传输与显式配置（环境变量 / 默认端口），不承载交接
规则；编排与错误族在 :mod:`dst_builder.application.builds`。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

__all__ = [
    "DEFAULT_MANAGER_BASE_URL",
    "MANAGER_BASE_URL_ENV",
    "HandoffTransport",
    "default_handoff_transport",
]

# Manager serve 默认 127.0.0.1:8000（与 Builder 8100 区分）；显式环境变量覆盖。
DEFAULT_MANAGER_BASE_URL = "http://127.0.0.1:8000"
MANAGER_BASE_URL_ENV = "DST_BUILDER_MANAGER_URL"
HANDOFF_TIMEOUT_SECONDS = 30.0

HandoffTransport = Callable[[str, dict], tuple[int, dict]]


def default_handoff_transport(url: str, payload: dict) -> tuple[int, dict]:
    """POST JSON 并返回 ``(status, 解析后的 JSON)``；网络故障抛 OSError。

    Manager 的 4xx/5xx 错误负载也按 ``(status, payload)`` 返回，由编排层
    决定错误码透传；HTTP 层错误同样包装为 OSError 的子类语义。
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HANDOFF_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, (json.loads(body) if body else {})
        except json.JSONDecodeError:
            return error.code, {}
    except urllib.error.URLError as error:
        raise OSError(str(error.reason)) from error


def manager_base_url_from_environ(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    value = env.get(MANAGER_BASE_URL_ENV, "").strip()
    return value.rstrip("/") if value else DEFAULT_MANAGER_BASE_URL
