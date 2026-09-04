import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .runtime import is_frozen


def _default_draft_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "dst-manager" / "drafts").resolve()


def _frozen_app_dir() -> Path | None:
    """frozen onedir 态的 exe 所在目录；开发态返回 None。"""
    return Path(sys.executable).resolve().parent if is_frozen() else None


def _default_data_dir() -> Path:
    """frozen 态数据落用户目录，避免双击启动把数据写进程序目录、zip 更新时被覆盖。"""
    app_dir = _frozen_app_dir()
    if app_dir is None:
        return Path(".dst-manager-data")
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "dst-manager" / "data").resolve()


def _default_plugin(version: str) -> Path | None:
    """frozen 态默认使用随包分发的 Worker 插件 DLL；开发态保持 None（显式配置）。"""
    app_dir = _frozen_app_dir()
    if app_dir is None:
        return None
    return (app_dir / f"autocad{version}" / "DstManager.AutoCAD.dll").resolve()


class Settings(BaseSettings):
    """只接受显式路径，不通过注册表或 PATH 猜测 AutoCAD。"""

    data_dir: Path = Field(default_factory=_default_data_dir)
    draft_dir: Path = Field(default_factory=_default_draft_dir)
    autocad_2016_console: Path | None = None
    autocad_2016_plugin: Path | None = Field(default_factory=lambda: _default_plugin("2016"))
    autocad_2020_console: Path | None = None
    autocad_2020_plugin: Path | None = Field(default_factory=lambda: _default_plugin("2020"))
    cad_timeout_seconds: int = 600
    cad_max_parallel: int = Field(default=4, ge=1, le=10)
    worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    enable_add_number_suffix: bool = Field(default=True, validation_alias="EnableAddNumberSuffix")
    number_suffix_type: Literal[1, 2] = Field(default=1, validation_alias="NumberSuffixType")
    model_config = SettingsConfigDict(env_prefix="DST_MANAGER_", env_file=".env")

    @field_validator("enable_add_number_suffix", mode="before")
    @classmethod
    def validate_enable_add_number_suffix(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("EnableAddNumberSuffix 仅接受 true 或 false")

    @field_validator("draft_dir")
    @classmethod
    def validate_draft_dir(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("draft_dir 必须为绝对路径")
        return value.resolve()

    @field_validator(
        "autocad_2016_console",
        "autocad_2016_plugin",
        "autocad_2020_console",
        "autocad_2020_plugin",
    )
    @classmethod
    def validate_cad_paths(cls, value: Path | None) -> Path | None:
        # accoreconsole 子进程内 NETLOAD 按自身工作目录解析相对 DLL 路径：Python 侧
        # is_file（相对项目根）会通过但加载失败，必须在源头统一规范化为绝对路径
        return value.resolve() if value is not None else None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'dst-manager.db').resolve().as_posix()}"
