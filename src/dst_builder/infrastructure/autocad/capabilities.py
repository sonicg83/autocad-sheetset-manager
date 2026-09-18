"""CAD 能力探测基础设施（SPEC-DB-001 §2/§7 / PLAN-DB-001 Task 4）。

只接受“显式配置且版本匹配”的 2016/2020 ``accoreconsole.exe`` 与对应的
Builder 插件 DLL（``DstBuilder.AutoCAD.dll``）：找到任意 ``acad.exe``、
其他产品的插件 DLL 或未配置项一律不可用。探测是纯配置 + 文件系统检查，
绝不启动进程（进程执行属 Task 7 的执行器）。

配置来源沿用 Manager 既有能力探测的显式路径模式：只读取
``DST_BUILDER_AUTOCAD_<版本>_CONSOLE`` / ``..._PLUGIN`` 环境变量，
不通过注册表或 PATH 猜测 AutoCAD。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dst_builder.runtime import apply_env_file

__all__ = [
    "CAD_CONSOLE_NOT_CONFIGURED",
    "CAD_CONSOLE_NOT_CORE_CONSOLE",
    "CAD_CONSOLE_NOT_FOUND",
    "CAD_PLUGIN_NOT_BUILDER",
    "CAD_PLUGIN_NOT_CONFIGURED",
    "CAD_PLUGIN_NOT_FOUND",
    "CAD_VERSION_UNSUPPORTED",
    "SUPPORTED_CAD_VERSIONS",
    "CadCapabilityStatus",
    "CadConfiguration",
    "evaluate_cad_capability",
    "load_cad_configuration",
]

SUPPORTED_CAD_VERSIONS = ("2016", "2020")

CORE_CONSOLE_NAME = "accoreconsole.exe"
BUILDER_PLUGIN_STEM = "dstbuilder.autocad"
BUILDER_PLUGIN_SUFFIX = ".dll"

# 不可用原因（探测细节）；HTTP 层统一以 §11 CAD_VERSION_UNAVAILABLE 呈现。
CAD_CONSOLE_NOT_CONFIGURED = "CAD_CONSOLE_NOT_CONFIGURED"
CAD_CONSOLE_NOT_FOUND = "CAD_CONSOLE_NOT_FOUND"
CAD_CONSOLE_NOT_CORE_CONSOLE = "CAD_CONSOLE_NOT_CORE_CONSOLE"
CAD_PLUGIN_NOT_CONFIGURED = "CAD_PLUGIN_NOT_CONFIGURED"
CAD_PLUGIN_NOT_FOUND = "CAD_PLUGIN_NOT_FOUND"
CAD_PLUGIN_NOT_BUILDER = "CAD_PLUGIN_NOT_BUILDER"
CAD_VERSION_UNSUPPORTED = "CAD_VERSION_UNSUPPORTED"

_ENV_PREFIX = "DST_BUILDER_AUTOCAD_"


@dataclass(frozen=True, slots=True)
class CadConfiguration:
    """两个受支持版本的显式路径配置；None 表示未配置。"""

    console_2016: Path | None = None
    plugin_2016: Path | None = None
    console_2020: Path | None = None
    plugin_2020: Path | None = None


@dataclass(frozen=True, slots=True)
class CadCapabilityStatus:
    """单个版本的探测结果：只有全部检查通过 ``available`` 才为 True。"""

    cad_version: str
    available: bool
    console_path: str | None = None
    plugin_path: str | None = None
    unavailable_reason: str | None = None


def evaluate_cad_capability(
    cad_version: str, *, console: Path | None, plugin: Path | None
) -> CadCapabilityStatus:
    """对单个版本执行纯文件系统/配置检查，不启动任何进程。"""

    def unavailable(reason: str) -> CadCapabilityStatus:
        return CadCapabilityStatus(
            cad_version=cad_version,
            available=False,
            console_path=str(console) if console is not None else None,
            plugin_path=str(plugin) if plugin is not None else None,
            unavailable_reason=reason,
        )

    if cad_version not in SUPPORTED_CAD_VERSIONS:
        return unavailable(CAD_VERSION_UNSUPPORTED)
    if console is None:
        return unavailable(CAD_CONSOLE_NOT_CONFIGURED)
    if plugin is None:
        return unavailable(CAD_PLUGIN_NOT_CONFIGURED)
    if not console.is_file():
        return unavailable(CAD_CONSOLE_NOT_FOUND)
    # 只接受 Core Console；acad.exe 等完整 AutoCAD 主程序不得视为可用。
    if console.name.casefold() != CORE_CONSOLE_NAME:
        return unavailable(CAD_CONSOLE_NOT_CORE_CONSOLE)
    if not plugin.is_file():
        return unavailable(CAD_PLUGIN_NOT_FOUND)
    # 必须是 Builder 专属插件 DLL，而不是任意 DLL 或其他产品的插件。
    if plugin.suffix.casefold() != BUILDER_PLUGIN_SUFFIX or plugin.stem.casefold() != BUILDER_PLUGIN_STEM:
        return unavailable(CAD_PLUGIN_NOT_BUILDER)
    return CadCapabilityStatus(
        cad_version=cad_version,
        available=True,
        console_path=str(console),
        plugin_path=str(plugin),
    )


def load_cad_configuration(environ: Mapping[str, str] | None = None) -> CadConfiguration:
    """读取显式环境变量配置；未配置的开发态全部为 None（不猜测 AutoCAD）。

    真实进程路径（``environ=None``）在 os.environ 副本上应用一次 .env（frozen=exe
    同目录、开发态=仓库根，见 runtime.apply_env_file）：setup.bat 写入的
    DST_BUILDER_* 键由此对桌面壳与 CLI 生效，进程已有环境变量仍然优先。
    **绝不回写真实进程环境**——.env 是 Manager/Builder 共享文件，键集合不归
    本函数所有，回写会跨产品泄漏配置并污染测试。测试注入的 ``environ`` 不受
    .env 影响。
    """
    if environ is None:
        env: Mapping[str, str] = dict(os.environ)
        apply_env_file(env)
    else:
        env = environ

    def configured(version: str, kind: str) -> Path | None:
        value = env.get(f"{_ENV_PREFIX}{version}_{kind}")
        if not value:
            return _default_plugin(version) if kind == "PLUGIN" else None
        return Path(value).resolve()

    return CadConfiguration(
        console_2016=configured("2016", "CONSOLE"),
        plugin_2016=configured("2016", "PLUGIN"),
        console_2020=configured("2020", "CONSOLE"),
        plugin_2020=configured("2020", "PLUGIN"),
    )


def _default_plugin(version: str) -> Path | None:
    """frozen 态默认使用随包分发的 Builder 插件 DLL；开发态保持显式配置。"""
    if not getattr(sys, "frozen", False):  # pragma: no cover - 打包态专用
        return None
    return (  # pragma: no cover - 打包态专用
        Path(sys.executable).resolve().parent / f"autocad{version}" / "DstBuilder.AutoCAD.dll"
    )
