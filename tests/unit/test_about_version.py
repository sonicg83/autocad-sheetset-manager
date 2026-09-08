"""关于接口版本回退链单元测试（PLAN-DM-019 设置中心任务 5）。

开发态/异常环境下 ``importlib.metadata`` 找不到 ``dst-manager`` 分发信息，
须回退读 ``resource_dir()/pyproject.toml``；文件也缺失时容错为"版本未知"
字符串，绝不崩溃（frozen 态 pyproject.toml 不保证随包分发）。
"""

import pytest

import dst_manager.interfaces.api as api_module
from dst_manager.interfaces.api import _app_version


def _no_distribution(name: str) -> str:
    raise api_module.PackageNotFoundError(name)


def test_app_version_reads_pyproject_in_dev(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(api_module, "package_version", _no_distribution)
    monkeypatch.setattr(api_module, "resource_dir", lambda: tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    assert _app_version() == "9.9.9"


def test_app_version_tolerates_missing_metadata_and_pyproject(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(api_module, "package_version", _no_distribution)
    monkeypatch.setattr(api_module, "resource_dir", lambda: tmp_path)
    assert _app_version() == "版本未知"


def test_app_version_prefers_installed_distribution(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "package_version", lambda name: "1.2.3")
    assert _app_version() == "1.2.3"


def test_app_version_queries_project_distribution_name(monkeypatch) -> None:
    """查询名必须是 pyproject.toml [project].name（autocad-sheetset）。

    发行名不是包目录名/CLI 名 dst-manager：查错名字会永远 PackageNotFoundError，
    importlib 主路径沦为死代码、全靠 pyproject 兜底（Task 7 打包评审修正）。
    """
    queried: list[str] = []

    def spy(name: str) -> str:
        queried.append(name)
        return "0.0.0"

    monkeypatch.setattr(api_module, "package_version", spy)
    assert _app_version() == "0.0.0"
    assert queried == ["autocad-sheetset"]


@pytest.mark.parametrize(
    "content",
    [
        "not = valid toml [[[",
        '[project]\nname = "x"\n',  # 缺 version 键
    ],
)
def test_app_version_tolerates_unreadable_pyproject(monkeypatch, tmp_path, content) -> None:
    monkeypatch.setattr(api_module, "package_version", _no_distribution)
    monkeypatch.setattr(api_module, "resource_dir", lambda: tmp_path)
    (tmp_path / "pyproject.toml").write_text(content, encoding="utf-8")
    assert _app_version() == "版本未知"
