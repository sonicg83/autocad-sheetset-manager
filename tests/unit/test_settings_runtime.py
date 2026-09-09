import json
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from dst_manager.config import Settings
from dst_manager.settings.registry import REGISTRY
from dst_manager.settings.runtime import (
    RuntimeSettings,
    SettingsConflict,
    SettingsValidationError,
    _pydantic_fallback_errors,
    default_store,
)
from dst_manager.settings.store import UserSettingsStore


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch, tmp_path):
    # Settings 的 env_file=".env" 按 cwd 解析：开发机常存在真实 .env（gitignored），
    # 切到 tmp_path 保证快照断言不受本机 .env 污染
    monkeypatch.chdir(tmp_path)


def _runtime(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(UserSettingsStore(tmp_path / "settings.json"))


def test_set_writes_only_overrides_and_bumps_revision(tmp_path) -> None:
    rt = _runtime(tmp_path)
    rt.apply_changes({"cad_timeout_seconds": 900}, [], expected_revision=0)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["values"] == {"cad_timeout_seconds": 900} and data["config_revision"] == 1
    assert rt.current().settings.cad_timeout_seconds == 900
    assert rt.current().sources["cad_timeout_seconds"].source == "file"


def test_unset_restores_inheritance_chain(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "555")
    rt = _runtime(tmp_path)
    rt.apply_changes({"cad_timeout_seconds": 900}, [], expected_revision=0)
    snap = rt.apply_changes({}, ["cad_timeout_seconds"], expected_revision=1)
    assert snap.settings.cad_timeout_seconds == 555            # file → env
    assert snap.sources["cad_timeout_seconds"].source == "env"


def test_conflicting_revision_returns_conflict_without_side_effects(tmp_path) -> None:
    rt = _runtime(tmp_path)
    rt.apply_changes({"cad_timeout_seconds": 900}, [], expected_revision=0)
    with pytest.raises(SettingsConflict):
        rt.apply_changes({"cad_max_parallel": 8}, [], expected_revision=0)
    assert rt.current().settings.cad_max_parallel == 4
    assert "cad_max_parallel" not in json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["values"]


def test_validation_failure_writes_nothing(tmp_path) -> None:
    rt = _runtime(tmp_path)
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"cad_max_parallel": 99}, [], expected_revision=0)
    assert "cad_max_parallel" in exc_info.value.errors
    assert not (tmp_path / "settings.json").exists()
    assert rt.current().settings.cad_max_parallel == 4


def test_unknown_key_rejected(tmp_path) -> None:
    with pytest.raises(SettingsValidationError) as exc_info:
        _runtime(tmp_path).apply_changes({"no_such_key": 1}, [], expected_revision=0)
    assert "no_such_key" in exc_info.value.errors


def test_concurrent_applies_serialize_to_consistent_state(tmp_path) -> None:
    rt = _runtime(tmp_path)
    barrier = threading.Barrier(2)

    def worker(key: str, value: int) -> None:
        barrier.wait()
        for _ in range(50):
            try:
                rt.apply_changes({key: value}, [], expected_revision=rt.current().config_revision)
                return
            except SettingsConflict:
                continue  # 后到者 409 是合法结果：刷新修订号重试直至落盘

    # 两个取值都合法（45 在 worker_lease_seconds 下限 30 之上），保证真正双写竞争
    threads = [threading.Thread(target=worker, args=("cad_max_parallel", 8)),
               threading.Thread(target=worker, args=("worker_lease_seconds", 45))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    disk = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    mem = rt.current()
    assert disk["config_revision"] == mem.config_revision       # 磁盘与内存一致
    assert disk["values"] == {"cad_max_parallel": 8, "worker_lease_seconds": 45}  # 两写都未丢
    assert mem.settings.cad_max_parallel == 8 and mem.settings.worker_lease_seconds == 45


def test_empty_string_path_becomes_null_override(tmp_path) -> None:
    rt = _runtime(tmp_path)
    snap = rt.apply_changes({"autocad_2016_console": ""}, [], expected_revision=0)
    assert snap.settings.autocad_2016_console is None
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["values"]["autocad_2016_console"] is None


def test_refresh_if_changed_reloads_after_external_write(tmp_path) -> None:
    rt = _runtime(tmp_path)
    rt.apply_changes({"cad_timeout_seconds": 900}, [], expected_revision=0)
    other = RuntimeSettings(UserSettingsStore(tmp_path / "settings.json"))
    other.apply_changes({"cad_max_parallel": 8}, [], expected_revision=1)
    assert rt.refresh_if_changed() is True
    assert rt.current().settings.cad_max_parallel == 8


def test_refresh_if_changed_keeps_cache_when_file_untouched(tmp_path) -> None:
    rt = _runtime(tmp_path)
    rt.apply_changes({"cad_timeout_seconds": 900}, [], expected_revision=0)
    assert rt.refresh_if_changed() is False
    assert rt.current().settings.cad_timeout_seconds == 900


def test_registry_constraints_rejected_with_field_errors(tmp_path) -> None:
    rt = _runtime(tmp_path)
    # int 范围、bool 类型、enum 取值、path 非法字符四类约束逐一体检
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"number_suffix_type": 3}, [], expected_revision=0)
    assert "number_suffix_type" in exc_info.value.errors
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"enable_add_number_suffix": "yes"}, [], expected_revision=0)
    assert "enable_add_number_suffix" in exc_info.value.errors
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"autocad_2020_console": "console<a>.exe"}, [], expected_revision=0)
    assert "autocad_2020_console" in exc_info.value.errors
    assert not (tmp_path / "settings.json").exists()


def test_unhashable_enum_payload_rejected_as_validation_error(tmp_path) -> None:
    # 任意 JSON 负载（list/dict 不可哈希）都须转成 422 语义，不得 TypeError 崩成 500
    rt = _runtime(tmp_path)
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"number_suffix_type": ["1"]}, [], expected_revision=0)
    assert "number_suffix_type" in exc_info.value.errors
    assert not (tmp_path / "settings.json").exists()
    assert rt.current().config_revision == 0


def test_alias_fields_round_trip_by_registry_key(tmp_path) -> None:
    # enable_add_number_suffix / number_suffix_type 带 validation_alias，
    # registry key 必须能作为字段名直接构造与回读
    rt = _runtime(tmp_path)
    snap = rt.apply_changes({"enable_add_number_suffix": False, "number_suffix_type": 2}, [], expected_revision=0)
    assert snap.settings.enable_add_number_suffix is False
    assert snap.settings.number_suffix_type == 2
    assert rt.refresh_if_changed() is False
    assert rt.current().settings.enable_add_number_suffix is False
    assert rt.current().settings.number_suffix_type == 2


def test_hand_edited_bad_value_type_degrades_instead_of_crashing(tmp_path) -> None:
    # 控制器挂账：手编 values 值类型非法（str 塞进 int 字段）不得让 current()/refresh 崩溃，
    # 降级为"忽略文件覆盖按默认+env 运行"并携带诊断；后续保存事务仍可自愈
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema_version": 1, "config_revision": 3, "values": {"cad_timeout_seconds": "abc"}}),
        encoding="utf-8",
    )
    rt = RuntimeSettings(UserSettingsStore(path))
    snap = rt.current()
    assert snap.settings.cad_timeout_seconds == 600             # 回退默认
    assert snap.config_revision == 3                            # 修订号仍取文件值
    assert any("SETTINGS_FILE_CORRUPT" in d for d in snap.diagnostics)
    assert snap.sources["cad_timeout_seconds"].source == "default"
    assert rt.refresh_if_changed() is False
    healed = rt.apply_changes({"cad_max_parallel": 8}, [], expected_revision=3)
    assert healed.settings.cad_timeout_seconds == 600
    assert healed.settings.cad_max_parallel == 8
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["values"] == {"cad_max_parallel": 8}            # 非法遗留值随保存清理


def test_default_store_respects_settings_path_env(monkeypatch, tmp_path) -> None:
    # Task 10 e2e 的隔离机制：DST_MANAGER_SETTINGS_PATH 指向自定义 settings.json 完整路径
    monkeypatch.setenv("DST_MANAGER_SETTINGS_PATH", str(tmp_path / "custom" / "settings.json"))
    assert default_store().path == tmp_path / "custom" / "settings.json"


def test_default_store_falls_back_to_local_app_data(monkeypatch) -> None:
    monkeypatch.delenv("DST_MANAGER_SETTINGS_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\demo\AppData\Local")
    assert default_store().path == Path(r"C:\Users\demo\AppData\Local\dst-manager\settings.json")


# ---- ui_locale 保存与结构化字段错误（PLAN-DM-021 Task 1 / I18N-10）----


def test_ui_locale_round_trips_through_save_transaction(tmp_path) -> None:
    rt = _runtime(tmp_path)
    snap = rt.apply_changes({"ui_locale": "en-US"}, [], expected_revision=0)
    assert snap.settings.ui_locale == "en-US"
    assert snap.sources["ui_locale"].source == "file"
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["values"] == {
        "ui_locale": "en-US"
    }


def test_ui_locale_rejected_outside_whitelist_with_structured_error(tmp_path) -> None:
    rt = _runtime(tmp_path)
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"ui_locale": "fr-FR"}, [], expected_revision=0)
    error = exc_info.value.errors["ui_locale"]
    assert error.code == "SETTING_ENUM_VALUE"
    assert error.message_key == "settings.validation.enumValue"
    assert error.params == {"allowed_values": ["en-US", "system", "zh-CN"]}
    assert error.message  # 迁移期兼容中文文本仍在


def test_integer_range_error_carries_structured_params(tmp_path) -> None:
    rt = _runtime(tmp_path)
    with pytest.raises(SettingsValidationError) as exc_info:
        rt.apply_changes({"cad_max_parallel": 99}, [], expected_revision=0)
    error = exc_info.value.errors["cad_max_parallel"]
    assert error.code == "SETTING_INTEGER_RANGE"
    assert error.message_key == "settings.validation.integerRange"
    assert error.params == {"min": 1, "max": 10}
    assert error.message


def test_unknown_key_error_is_structured(tmp_path) -> None:
    with pytest.raises(SettingsValidationError) as exc_info:
        _runtime(tmp_path).apply_changes({"no_such_key": 1}, [], expected_revision=0)
    error = exc_info.value.errors["no_such_key"]
    assert error.code == "SETTING_UNKNOWN"
    assert error.message_key == "settings.validation.unknownKey"
    assert error.params == {}


def test_field_error_params_stay_within_whitelist(tmp_path) -> None:
    # params 只允许 str/int/bool/list[str]，且不携带已本地化 label 或完整句子
    rt = _runtime(tmp_path)
    cases: list[dict[str, object]] = [
        {"cad_max_parallel": 99},
        {"worker_lease_seconds": "abc"},
        {"enable_add_number_suffix": "yes"},
        {"autocad_2020_console": "console<a>.exe"},
        {"autocad_2016_plugin": 3},
        {"number_suffix_type": 3},
        {"number_suffix_type": ["1"]},
        {"ui_locale": "fr-FR"},
        {"no_such_key": 1},
    ]
    labels = {meta.label for meta in REGISTRY}
    for case in cases:
        with pytest.raises(SettingsValidationError) as exc_info:
            rt.apply_changes(case, [], expected_revision=0)
        for error in exc_info.value.errors.values():
            assert error.message_key.startswith("settings.validation."), error.code
            for value in error.params.values():
                assert isinstance(value, (str, int, bool, list)), error.code
                if isinstance(value, list):
                    assert all(isinstance(item, str) for item in value), error.code
                if isinstance(value, str):
                    assert value not in labels, error.code  # 不传中文 label


def test_pydantic_fallback_error_is_structured() -> None:
    # 兜底转换分支（registry 约束之外，如 lax 模式仍拒绝的负载）直接以真实
    # pydantic 异常驱动：同样必须产出结构化对象而非中文纯字符串
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, cad_max_parallel=99)
    errors = _pydantic_fallback_errors(exc_info.value)
    error = errors["cad_max_parallel"]
    assert error.code == "SETTING_INVALID_FORMAT"
    assert error.message_key == "settings.validation.invalidFormat"
    assert error.params == {}
    assert error.message
