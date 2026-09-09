import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .runtime import is_frozen

# 界面语言三值白名单（I18N-02）：system 表示跟随系统语言，解析在前端完成
UiLocale = Literal["system", "zh-CN", "en-US"]


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
    # 界面语言（ARCH-DM-005 §4.1）：只保存显式覆盖值，不进工作区/草稿/数据库；
    # 仅接受三值白名单，system 的解析（含非中英回落 en-US、无法读取回落 zh-CN）
    # 由前端负责，后端不按语言生成文本。env 通道 DST_MANAGER_UI_LOCALE 沿用
    # env_prefix 既有规则，优先级 默认 < env < settings.json 文件覆盖
    ui_locale: UiLocale = "system"
    # populate_by_name：设置中心以 registry 字段名（snake_case）构造覆盖项，而
    # enable_add_number_suffix/number_suffix_type 的 validation_alias 仅服务
    # .env/环境变量通道——两个入口必须同时可用。顺带使带 DST_MANAGER_ 前缀的
    # 字段名环境变量（如 DST_MANAGER_ENABLE_ADD_NUMBER_SUFFIX，大小写不敏感）
    # 从无效变为生效，与其余 8 个字段一致；别名键（EnableAddNumberSuffix）
    # 与 .env 模板写法不受影响
    model_config = SettingsConfigDict(env_prefix="DST_MANAGER_", env_file=".env", populate_by_name=True)

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

    @field_validator("number_suffix_type", mode="before")
    @classmethod
    def validate_number_suffix_type(cls, value: object) -> object:
        # .env 与环境变量中的值恒为字符串，Literal[1, 2] 不接受 "1"/"2"，
        # 与 EnableAddNumberSuffix 同样在源头做字符串容错
        if value in ("1", "2"):
            return int(value)  # type: ignore[arg-type]
        return value

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
