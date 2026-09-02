import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_draft_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "dst-manager" / "drafts").resolve()


class Settings(BaseSettings):
    """只接受显式路径，不通过注册表或 PATH 猜测 AutoCAD。"""

    data_dir: Path = Path(".dst-manager-data")
    draft_dir: Path = Field(default_factory=_default_draft_dir)
    autocad_2016_console: Path | None = None
    autocad_2016_plugin: Path | None = None
    autocad_2020_console: Path | None = None
    autocad_2020_plugin: Path | None = None
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

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'dst-manager.db').resolve().as_posix()}"
