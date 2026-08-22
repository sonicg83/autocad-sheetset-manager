import pytest
from pydantic import ValidationError

from dst_manager.config import Settings


def test_suffix_settings_use_spec_defaults(monkeypatch):
    monkeypatch.delenv("EnableAddNumberSuffix", raising=False)
    monkeypatch.delenv("NumberSuffixType", raising=False)
    settings = Settings(_env_file=None)
    assert settings.enable_add_number_suffix is True
    assert settings.number_suffix_type == 1


def test_suffix_settings_reject_invalid_values(monkeypatch):
    monkeypatch.setenv("NumberSuffixType", "3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["1", "0", "yes", "on"])
def test_suffix_settings_reject_loose_boolean_strings(monkeypatch, value: str):
    monkeypatch.setenv("EnableAddNumberSuffix", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
