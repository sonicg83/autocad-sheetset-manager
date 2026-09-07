---
id: PLAN-DM-019
title: 设置中心实施计划（配置域后端 + 设置中心 UI）
status: proposed
owners:
  - dst-manager
created: 2026-09-08
updated: 2026-09-08
related:
  - ARCH-DM-004
  - SPEC-DM-011
  - GUIDE-DM-001
---

# 设置中心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付应用内设置中心——未加载 DST 即可经顶部齿轮配置 9 个应用配置项（即时生效、跨 API/Worker 进程一致）并查看关于页。

**Architecture:** Pydantic `Settings` 保持唯一语义权威；新增 `settings/` 包（store 原子存取、registry 展示元数据、resolver 快照合并、runtime 持有者与保存事务）；Worker 按任务认领前检测 `config_revision` 重载并冻结任务级快照；前端 `SettingsDialog.vue` 按注册表描述动态渲染，齿轮入口入 `TopBar.vue`。

**Tech Stack:** Python 3.12 + UV、FastAPI、SQLAlchemy/Alembic、pywebview、Vue 3 + TypeScript、Playwright。

**Spec:** [ARCH-DM-004](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)（行为权威）· [SPEC-DM-011](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)（UI 权威 + 冻结设计）

## Global Constraints

- 文件一律 UTF-8；注释、commit message 用简体中文，动词开头（AGENTS.md）。
- Python 不低于 3.12；只用 `uv` 管理依赖；验证命令：`uv run ruff check .`、`uv run pytest -q`（仓库根）。
- 单源文件约 500 行软上限；`App.vue` 已超限——任务 11 只允许在 `TopBar.vue` 加入口与在 `App.vue` 加不超过 5 行的挂载代码。
- `config.py` 的字段、默认值、validator 语义**不得改动**；`registry.py` → `config.py` 单向依赖，禁止反向导入。
- `settings.json` 只存**显式覆盖值**；空字符串/纯空白路径一律按 `null`（未配置）处理，绝不解析为 cwd。
- 所有写操作只落 `%LOCALAPPDATA%\dst-manager\`（或回退目录），不写程序目录/项目目录。
- 服务只监听 `127.0.0.1`；日志/诊断不得无差别复制完整路径。
- 冻结设计（SPEC-DM-011 §7 截图索引）是 G8 比对基准；Demo 再变更须重开 G4。

## 追踪矩阵（G6 依据）

| ID | 要求（来源） | 实施任务 | 自动测试 | 设计 QA | 真实验收 |
| --- | --- | --- | --- | --- | --- |
| A-01 | 原子存储 + 四类诊断码（ARCH §2.2） | 任务 1 | `test_settings_store.py` | — | — |
| A-02 | 注册表只存展示元数据、派生约束、完整性（ARCH §2.1） | 任务 2 | `test_settings_registry.py` | — | — |
| A-03 | Resolver 三层合并、source 记录、空串→null（ARCH §2.3） | 任务 3 | `test_settings_resolver.py` | — | — |
| A-04 | 保存事务锁、expected_revision/409（ARCH §2.3/§3） | 任务 4 | `test_settings_runtime.py` | — | — |
| A-05 | 3 个 API 端点契约（ARCH §3） | 任务 5 | `test_api_settings.py` | — | — |
| A-06 | Worker 热更新 + 任务快照 + 租约按任务判断（ARCH §2.4） | 任务 6 | `test_worker_settings_propagation.py` | — | — |
| A-07 | 打包触点：LICENSE datas + dist-info（ARCH §8） | 任务 7 | spec 静态检查 | — | G9 手工 |
| SC-01~05 | 齿轮/对话框/动态渲染/路径控件/来源标记 | 任务 8~11 | e2e | G8 截图比对 | G9 |
| SC-06~09 | 校验/保存状态机/未保存保护/键盘 | 任务 10 | e2e | G8 | G9 |
| SC-10 | 主题/视口 | 任务 10 | — | G8 截图 | G9 |
| SC-11 | 关于页 + 外链 | 任务 5（端点）+ 10（UI） | `test_api_settings.py` + e2e | G8 | G9 |
| SC-12 | 诊断横幅 | 任务 10 | e2e | G8 | — |
| SC-13 | 预览重算提示 | 任务 11 | e2e | — | — |
| SC-14 | 拖拽不穿透遮罩 | 任务 10 | e2e | — | — |

---

### Task 1: `settings/store.py` 用户配置文件原子存取

**Files:**
- Create: `src/dst_manager/settings/__init__.py`（空导出）、`src/dst_manager/settings/store.py`
- Test: `tests/unit/test_settings_store.py`

**Interfaces（Produces）:**
```python
SCHEMA_VERSION = 1
class SettingsFileMissing(Exception): ...      # SETTINGS_FILE_MISSING
class SettingsFileCorrupt(Exception): ...      # SETTINGS_FILE_CORRUPT（携带 backup_path）
class SettingsSchemaNewer(Exception): ...      # SETTINGS_SCHEMA_NEWER
class SettingsSchemaOlder(Exception): ...      # SETTINGS_SCHEMA_OLDER

class UserSettingsStore:
    def __init__(self, path: Path) -> None: ...
    def load(self) -> tuple[dict[str, object], int, list[str]]:
        """返回 (values 覆盖字典, config_revision, 诊断码列表)。文件缺失 → ({}, 0, ["SETTINGS_FILE_MISSING"])；
        损坏 → 原样重命名为 <name>.corrupt-<时间戳> 备份后返回 ({}, 0, ["SETTINGS_FILE_CORRUPT"])；
        schema_version > SCHEMA_VERSION → 抛 SettingsSchemaNewer（原文件不动）；
        schema_version < SCHEMA_VERSION → 抛 SettingsSchemaOlder（本期无迁移器）。"""
    def save_overrides(self, values: dict[str, object], previous_revision: int) -> int:
        """原子写（同目录临时文件 + os.replace）；config_revision = previous_revision + 1；返回新修订号。"""
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_settings_store.py
import json
from pathlib import Path

import pytest

from dst_manager.settings.store import (
    SCHEMA_VERSION,
    SettingsFileCorrupt,
    SettingsSchemaNewer,
    SettingsSchemaOlder,
    UserSettingsStore,
)


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    assert store.load() == ({}, 0, ["SETTINGS_FILE_MISSING"])


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    revision = store.save_overrides({"cad_timeout_seconds": 900}, previous_revision=0)
    assert revision == 1
    values, loaded_revision, diagnostics = store.load()
    assert values == {"cad_timeout_seconds": 900}
    assert loaded_revision == 1 and diagnostics == []


def test_written_file_contains_schema_and_revision(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({}, previous_revision=5)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data == {"schema_version": SCHEMA_VERSION, "config_revision": 6, "values": {}}


def test_corrupt_file_backed_up_and_reset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{截断的 JSON", encoding="utf-8")
    store = UserSettingsStore(path)
    values, revision, diagnostics = store.load()
    assert values == {} and revision == 0
    assert diagnostics == ["SETTINGS_FILE_CORRUPT"]
    assert not path.exists()  # 原文件已重命名为备份
    backups = list(tmp_path.glob("settings.json.corrupt-*"))
    assert len(backups) == 1 and "截断" in backups[0].read_text(encoding="utf-8")


def test_unknown_newer_schema_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = json.dumps({"schema_version": SCHEMA_VERSION + 1, "config_revision": 3, "values": {"x": 1}, "future_field": True})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(SettingsSchemaNewer):
        UserSettingsStore(path).load()
    assert path.read_text(encoding="utf-8") == original  # 字节不变


def test_older_schema_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION - 1, "config_revision": 1, "values": {}}), encoding="utf-8")
    with pytest.raises(SettingsSchemaOlder):
        UserSettingsStore(path).load()


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({"a": 1}, previous_revision=0)
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.json"]
```

- [ ] **Step 2: 运行确认失败** —— `uv run pytest tests/unit/test_settings_store.py -q`，预期 `ModuleNotFoundError: dst_manager.settings`
- [ ] **Step 3: 最小实现** —— `store.py`：`load()` 按上文语义（`json.loads` 异常/非 dict/`values` 非 dict → corrupt 分支；重命名用 `time.strftime("%Y%m%d-%H%M%S")` 时间戳，冲突时追加 `-1` 序号）；`save_overrides()` 用 `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)` 写临时文件后 `os.replace`；无任何网络/路径拼接。
- [ ] **Step 4: 运行通过** —— 同 Step 2，预期 `7 passed`
- [ ] **Step 5: 提交** —— `git add src/dst_manager/settings tests/unit/test_settings_store.py && git commit -m "新增设置中心用户配置原子存储"`

### Task 2: `settings/registry.py` 展示元数据注册表

**Files:**
- Create: `src/dst_manager/settings/registry.py`
- Test: `tests/unit/test_settings_registry.py`

**Interfaces（Produces）:**
```python
@dataclass(frozen=True)
class SettingsItemMeta:
    key: str          # 与 Settings 字段同名
    label: str        # 中文显示名
    category: str     # "AutoCAD 2016" | "AutoCAD 2020" | "任务执行" | "编号规则"
    control: str      # "path" | "bool" | "int" | "enum"
    nullable: bool = False        # 仅 path
    file_filter: str | None = None  # 仅 path："可执行程序 (*.exe)" / ".NET 程序集 (*.dll)"

REGISTRY: tuple[SettingsItemMeta, ...]  # 9 项，顺序即 API 稳定排序

def min_max(key: str) -> tuple[int, int]:    # 从 Settings.model_fields 的 metadata(ge/le) 派生
def enum_options(key: str) -> list[dict]:    # 从 Literal 注解派生 number_suffix_type → [{value:1,text:"类型 1"},{value:2,text:"类型 2"}]
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_settings_registry.py
from dst_manager.config import Settings
from dst_manager.settings.registry import REGISTRY


def test_registry_covers_exactly_the_nine_ui_fields() -> None:
    ui_fields = {m.key for m in REGISTRY}
    assert ui_fields == {
        "autocad_2016_console", "autocad_2016_plugin",
        "autocad_2020_console", "autocad_2020_plugin",
        "cad_timeout_seconds", "cad_max_parallel", "worker_lease_seconds",
        "enable_add_number_suffix", "number_suffix_type",
    }
    excluded = {"data_dir", "draft_dir"}
    assert not (ui_fields & excluded)


def test_every_key_exists_on_settings() -> None:
    settings = Settings()
    for meta in REGISTRY:
        assert hasattr(settings, meta.key)


def test_derived_constraints_match_settings_schema() -> None:
    assert min_max("cad_max_parallel") == (1, 10)
    assert min_max("worker_lease_seconds") == (30, 3600)
    assert [o["value"] for o in enum_options("number_suffix_type")] == [1, 2]


def test_path_fields_declare_nullable_and_filters() -> None:
    for meta in REGISTRY:
        if meta.control == "path":
            assert meta.nullable and meta.file_filter is not None
    console = next(m for m in REGISTRY if m.key == "autocad_2016_console")
    assert "*.exe" in console.file_filter
    plugin = next(m for m in REGISTRY if m.key == "autocad_2016_plugin")
    assert "*.dll" in plugin.file_filter
```

- [ ] **Step 2: 运行确认失败** —— `uv run pytest tests/unit/test_settings_registry.py -q`，预期 ModuleNotFoundError
- [ ] **Step 3: 实现** —— `registry.py`：dataclass + 9 项 `REGISTRY` 元组（label/category 按冻结设计文案：如 "Core Console"、"Worker 插件"、"CAD 超时（秒）"、"最大并行任务数"、"Worker 租约（秒）"、"图纸编号追加后缀"、"后缀类型"）；`min_max()` 遍历 `Settings.model_fields[key].metadata` 取 `ge`/`le`；`enum_options()` 用 `typing.get_args(Settings.model_fields[key].annotation)`。不导入 store/resolver。
- [ ] **Step 4: 运行通过** —— 预期 `4 passed`
- [ ] **Step 5: 提交** —— `git commit -m "新增设置中心展示元数据注册表"`

### Task 3: `settings/resolver.py` 快照合并

**Files:**
- Create: `src/dst_manager/settings/resolver.py`
- Test: `tests/unit/test_settings_resolver.py`

**Interfaces（Produces / Consumes）:**
```python
from dataclasses import dataclass
from dst_manager.config import Settings

@dataclass(frozen=True)
class FieldSource:
    source: str                # "default" | "env" | "file"
    has_file_override: bool

@dataclass(frozen=True)
class SettingsSnapshot:
    settings: Settings
    sources: dict[str, FieldSource]     # 仅 REGISTRY 中的 9 个 key
    diagnostics: list[str]
    config_revision: int
    schema_blocked: bool                # True = Schema 过新，只读

class SettingsResolver:
    def __init__(self, store: UserSettingsStore) -> None: ...
    def load_snapshot(self) -> SettingsSnapshot:
        """合并优先级 默认 < env < 文件覆盖；source 判定规则见测试；
        文件覆盖值经 kwargs 注入 Settings(...)；空字符串/纯空白路径 → None；
        SettingsSchemaNewer → 用纯 env/默认构造 Settings，schema_blocked=True。"""
```

- [ ] **Step 1: 写失败测试**（关键用例；`_write` 辅助函数直接写 JSON 文件）

```python
# tests/unit/test_settings_resolver.py
import json
from pathlib import Path

from dst_manager.config import Settings
from dst_manager.settings.resolver import SettingsResolver
from dst_manager.settings.store import UserSettingsStore


def _resolver(tmp_path: Path, values: object, version: int = 1) -> SettingsResolver:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": version, "config_revision": 4, "values": values}), encoding="utf-8")
    return SettingsResolver(UserSettingsStore(path))


def test_file_only_stores_overrides_and_merges_over_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 900}).load_snapshot()
    assert snap.settings.cad_timeout_seconds == 900          # file > env
    src = snap.sources["cad_timeout_seconds"]
    assert (src.source, src.has_file_override) == ("file", True)


def test_source_is_env_when_no_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {}).load_snapshot()
    assert snap.settings.cad_timeout_seconds == 777
    assert snap.sources["cad_timeout_seconds"].source == "env"


def test_source_is_file_even_when_value_equals_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 777}).load_snapshot()
    assert snap.sources["cad_timeout_seconds"].source == "file"  # 不从终值反推


def test_empty_string_path_normalizes_to_none(tmp_path) -> None:
    snap = _resolver(tmp_path, {"autocad_2016_console": "   "}).load_snapshot()
    assert snap.settings.autocad_2016_console is None        # 绝不解析为 cwd


def test_relative_path_still_resolves_absolute(tmp_path) -> None:
    snap = _resolver(tmp_path, {"autocad_2016_console": "console/accoreconsole.exe"}).load_snapshot()
    assert snap.settings.autocad_2016_console.is_absolute()  # 兼容现状


def test_newer_schema_blocks_but_falls_back(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 900}, version=99).load_snapshot()
    assert snap.schema_blocked and snap.config_revision == 4
    assert snap.settings.cad_timeout_seconds == 777          # 覆盖值被忽略


def test_env_unset_paths_stay_none_in_dev(tmp_path) -> None:
    snap = _resolver(tmp_path, {}).load_snapshot()
    assert snap.settings.autocad_2016_console is None        # 开发态默认 None
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** —— `resolver.py`：区分"来源"用双层构造——先构造仅 env 的 `Settings()` 记录 env 值基线，再对有覆盖的 key 用 `Settings(**overrides)` 构造最终实例；`source = "file" if key in overrides else ("env" if env 基线值 != 默认值 else "default")`（env 基线比较仅对 int/bool/enum 做 `!=`，path 类 env 存在即 `"env"`）；空串/空白在传入 kwargs 前置为 None。不缓存——每次 `load_snapshot()` 重读文件（Worker 每任务调用，成本可忽略）。
- [ ] **Step 4: 运行通过** —— 预期 `7 passed`；同时跑 `uv run pytest tests/unit/test_config.py -q` 确认既有配置测试无回归
- [ ] **Step 5: 提交** —— `git commit -m "新增设置快照解析器与来源追踪"`

### Task 4: `settings/runtime.py` 运行时持有者与保存事务

**Files:**
- Create: `src/dst_manager/settings/runtime.py`
- Test: `tests/unit/test_settings_runtime.py`

**Interfaces（Produces / Consumes）:**
```python
class SettingsConflict(Exception): ...        # expected_revision 不符 → API 409
class SettingsValidationError(Exception):
    errors: dict[str, str]                    # key → 中文消息 → API 422

class RuntimeSettings:
    """进程内快照持有者 + 保存事务。API 与（同进程的）desktop 服务共用。"""
    def __init__(self, store: UserSettingsStore) -> None: ...
    def current(self) -> SettingsSnapshot:            # 返回缓存快照；首次调用加载
    def refresh_if_changed(self) -> bool:             # 文件 stat 变化才重解析（Worker 每任务前调用）
    def apply_changes(self, set_values: dict[str, object], unset: list[str], expected_revision: int) -> SettingsSnapshot:
        """锁内全流程：校验（registry 约束 + Settings 构造）→ 锁内 load 基准 →
        合并新覆盖集 → store.save_overrides → 替换缓存快照 → 返回新快照。
        校验失败抛 SettingsValidationError（文件与内存均不动）；
        expected_revision != 当前 → SettingsConflict（无任何副作用）。"""

def default_store() -> UserSettingsStore:   # %LOCALAPPDATA%\dst-manager\settings.json（LOCALAPPDATA 缺失回退 ~/AppData/Local），与 config._default_data_dir 同规则
```

- [ ] **Step 1: 写失败测试**（核心用例：事务原子性、并发交错、409、校验失败不落盘）

```python
# tests/unit/test_settings_runtime.py
import json
import threading
from pathlib import Path

import pytest

from dst_manager.settings.runtime import RuntimeSettings, SettingsConflict, SettingsValidationError
from dst_manager.settings.store import UserSettingsStore


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
    def worker(key: str) -> None:
        barrier.wait()
        try:
            rt.apply_changes({key: 8}, [], expected_revision=rt.current().config_revision)
        except SettingsConflict:
            pass  # 后到者 409 是合法结果
    threads = [threading.Thread(target=worker, args=("cad_max_parallel",)),
               threading.Thread(target=worker, args=("worker_lease_seconds",))]
    for t in threads: t.start()
    for t in threads: t.join()
    disk = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    mem = rt.current()
    assert disk["config_revision"] == mem.config_revision       # 磁盘与内存一致
    assert set(disk["values"]) == (set(mem.settings.model_dump()) & set(disk["values"]))  # 覆盖集一致


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
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** —— `runtime.py`：`threading.RLock` 覆盖 `apply_changes` 全流程；校验逻辑 = registry 约束（int 范围、enum、path 字符）+ 空串→None + `Settings(**merged_overrides)` 构造兜底（pydantic 异常转成 `errors`）；`refresh_if_changed` 比较 `(st_mtime_ns, st_size)` 缓存。`default_store()` 复用 `LOCALAPPDATA` 回退规则（参照 `config._default_data_dir` 实现，不导入其私有函数）。
- [ ] **Step 4: 运行通过** —— `uv run pytest tests/unit/test_settings_runtime.py -q` 预期 `8 passed`
- [ ] **Step 5: 提交** —— `git commit -m "新增设置运行时持有者与保存事务"`

### Task 5: API 端点与装配

**Files:**
- Modify: `src/dst_manager/interfaces/api.py`（`create_app` 增加可选参数与 3 个路由）
- Create: `src/dst_manager/interfaces/responses.py` 内追加（或新建 `interfaces/settings_contracts.py`，若 responses.py 超 500 行上限则新建）——`SettingsResponse`、`SettingsPutRequest`、`SettingsItemModel`、`AboutResponse`（均为 `ContractModel` 子类）
- Modify: `src/dst_manager/interfaces/shell.py`（`run_desktop` 装配 `RuntimeSettings(default_store())` 并传入 `create_app`）
- Test: `tests/integration/test_api_settings.py`（沿用既有 API 集成测试夹具模式）

**Interfaces（Produces）:**
```python
def create_app(settings: Settings | None = None, ..., runtime_settings: RuntimeSettings | None = None) -> FastAPI
# runtime_settings 为 None 时（开发态 serve / 既有测试）不注册这 3 个端点，契约零变化

GET  /api/settings → SettingsResponse   # {schema_version, config_revision, items[], diagnostics[]}
PUT  /api/settings → SettingsResponse   # body {expected_revision:int, set:dict, unset:[str]}
                                      # SettingsValidationError → 422 {"errors": {...}}；SettingsConflict → 409
GET  /api/about → AboutResponse        # {app_name, version, license:{spdx,text}, homepage, feedback_url}
```

- [ ] **Step 1: 写失败测试**（代表性用例）

```python
# tests/integration/test_api_settings.py
def test_get_settings_returns_items_with_metadata(client_with_runtime) -> None:
    body = client_with_runtime.get("/api/settings").json()
    assert body["schema_version"] == 1 and body["config_revision"] == 0
    keys = [item["key"] for item in body["items"]]
    assert keys[0] == "autocad_2016_console" and len(keys) == 9      # REGISTRY 顺序稳定
    item = body["items"][4]
    assert item["label"] and item["category"] and item["source"] in ("default", "env", "file")


def test_put_partial_update_does_not_freeze_env_values(client_with_runtime, monkeypatch) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    rev = client_with_runtime.get("/api/settings").json()["config_revision"]
    resp = client_with_runtime.put("/api/settings", json={"expected_revision": rev, "set": {"cad_max_parallel": 8}, "unset": []})
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert items["cad_max_parallel"]["has_file_override"] is True
    assert items["cad_timeout_seconds"]["source"] == "env"           # 未被固化


def test_put_stale_revision_returns_409(client_with_runtime) -> None:
    resp = client_with_runtime.put("/api/settings", json={"expected_revision": 99, "set": {}, "unset": []})
    assert resp.status_code == 409


def test_put_field_errors_return_422_with_errors_map(client_with_runtime) -> None:
    rev = client_with_runtime.get("/api/settings").json()["config_revision"]
    resp = client_with_runtime.put("/api/settings", json={"expected_revision": rev, "set": {"cad_max_parallel": 99}, "unset": []})
    assert resp.status_code == 422 and "cad_max_parallel" in resp.json()["errors"]


def test_about_returns_version_and_mit_license(client_with_runtime) -> None:
    body = client_with_runtime.get("/api/about").json()
    assert body["license"]["spdx"] == "MIT"
    assert "MIT License" in body["license"]["text"]
    assert body["version"] and body["app_name"]


def test_endpoints_absent_without_runtime(client) -> None:
    """开发态/既有测试的 create_app() 不注册设置端点，契约零变化。"""
    assert client.get("/api/settings").status_code == 404
```

`client_with_runtime` 夹具：在既有 API 测试 `conftest` 基础上，用 `tmp_path` 的 `UserSettingsStore` 构造 `RuntimeSettings` 传入 `create_app`。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现** —— 端点用 `ContractModel` 请求/响应模型；`about` 的版本：`importlib.metadata.version("dst-manager")`，`PackageNotFoundError` 时回退读 `pyproject.toml`（`tomllib`，路径经 `runtime.resource_dir()` 向上找）；LICENSE 文本：开发态读仓库根 `LICENSE`，frozen 态读 `resource_dir()/LICENSE`（任务 7 打包）。`run_desktop` 装配处同步传入；`cli serve` 保持 None（不注册端点也可用，属可接受降级，G9 验收只覆盖 desktop 入口）。**`default_store()` 必须尊重 `DST_MANAGER_SETTINGS_PATH` 环境变量**（存在时用作 settings.json 完整路径）——Task 10 的 e2e 依赖它隔离配置文件。
- [ ] **Step 4: 运行通过** —— `uv run pytest tests/integration/test_api_settings.py tests/unit -q`；再全量 `uv run pytest -q` 确认基线无回归（≥642 passed）
- [ ] **Step 5: 提交** —— `git commit -m "新增设置与关于 API 端点"`

### Task 6: Worker 配置热更新与任务级快照

**Files:**
- Modify: `src/dst_manager/infrastructure/persistence/models.py`（`JobRow` 增加可空列 `lease_seconds: Mapped[int | None]`）
- Create: `migrations/versions/0005_dm019_job_lease_seconds.py`（`revision="0005_dm019_job_lease_seconds"`，`down_revision="0004_dm007_layout_name_cache"`，`op.add_column("jobs", sa.Column("lease_seconds", sa.Integer(), nullable=True))` + 降级 `drop_column`）
- Modify: `src/dst_manager/infrastructure/persistence/database.py:364`（`claim_next_job` 的 `.values(...)` 增加 `lease_seconds=lease_seconds`，签名加 `lease_seconds: int = 120` 关键字参数）；`database.py:418`（`recover_stale_jobs` 改为逐行 `cutoff = now - timedelta(seconds=row.lease_seconds or lease_seconds)`）
- Modify: `src/dst_manager/application/service.py:104`（`run_next_job` 先 `self._runtime.refresh_if_changed()`，再以 `self._runtime.current().settings` 取值；认领传入当前 lease；任务事件 detail 追加 `cfg=r<revision>`）
- Modify: `src/dst_manager/interfaces/cli.py:87`（`worker` 命令构造 `RuntimeSettings(default_store())` 注入 `DstManagerService`）
- Modify: `src/dst_manager/application/service.py` 构造函数（新增可选 `runtime_settings: RuntimeSettings | None`；None 时退化为启动期一次性快照——`serve`/既有测试行为不变）
- Test: `tests/unit/test_worker_settings_propagation.py` + `tests/unit/test_database.py` 追加用例

**Interfaces（Produces）:**
```python
DstManagerService(settings: Settings | None = None, *, runtime_settings: RuntimeSettings | None = None)
# run_next_job(): 认领前 refresh_if_changed()；本任务使用的 lease 随认领写入 jobs.lease_seconds；
#                 运行期间一律读认领时冻结的局部变量，不再读 self.settings
```

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_worker_settings_propagation.py（夹具参照 tests/unit/test_database.py 既有
# Database 临时库与任务入队/认领模式；下为租约快照核心用例全文，其余用例同构）
from datetime import datetime, timedelta, UTC

from dst_manager.infrastructure.persistence.database import Database
from dst_manager.settings.runtime import RuntimeSettings
from dst_manager.settings.store import UserSettingsStore


def test_lease_snapshot_written_on_claim_and_used_by_recovery(tmp_path) -> None:
    db = Database(f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")  # 构造方式以既有夹具为准
    job_id = db.enqueue_change_set(_sample_cad_payload())            # 既有夹具的入队辅助
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({"worker_lease_seconds": 60}, previous_revision=0)
    runtime = RuntimeSettings(store)
    claimed = db.claim_next_job(lease_seconds=runtime.current().settings.worker_lease_seconds)
    assert claimed["id"] == job_id
    assert db._fetch_row(job_id).lease_seconds == 60                 # 认领时冻结进行
    db.update_heartbeat(job_id, claimed["worker_id"], at=datetime.now(UTC) - timedelta(seconds=50))
    # 行 lease=60、心跳 50 秒前：全局默认 120 会放过，按行快照必须回收
    recovered = db.recover_stale_jobs(lease_seconds=120)
    assert any(r["id"] == job_id for r in recovered)


def test_old_lease_row_not_reaped_after_global_lease_decreased(tmp_path) -> None:
    # 行 lease=120、心跳 100 秒前、调用方传 lease_seconds=30 → 不回收（按行快照判断）
    ...
```

（`_sample_cad_payload`、`update_heartbeat`、行读取辅助以 `tests/unit/test_database.py` 现有名称为准；若不存在则在本任务内补最小辅助函数，不改动既有测试文件。）

- [ ] **Step 2: 运行确认失败** —— 新列不存在/逻辑未接，预期 FAIL
- [ ] **Step 3: 实现** —— 按上文 Files 描述逐点修改；`run_next_job` 内把 `timeout_seconds`/`max_parallel`/`lease` 取局部变量冻结，任务执行链路只读局部变量（`service.py:116-117` 一带）；JobEventRow detail 追加 `cfg=r{revision}`。
- [ ] **Step 4: 运行通过 + 迁移验证** —— `uv run pytest tests/unit/test_worker_settings_propagation.py tests/unit/test_database.py -q`；然后全新库迁移验证：删临时库后 `uv run alembic upgrade head` 成功、`uv run alembic downgrade -1 && uv run alembic upgrade head` 往返成功
- [ ] **Step 5: 提交** —— `git commit -m "Worker 任务级配置快照与租约按行回收"`

### Task 7: 打包触点（spec 两处）

**Files:**
- Modify: `packaging/dst-manager.spec`（`datas` 增加 `(PROJECT_ROOT / "LICENSE", ".")`；确认 `dst-manager.dist-info` 被收集——若 `importlib.metadata` 在 frozen 态取不到版本，增加 `copy_metadata("dst-manager")` hook）

- [ ] **Step 1: 修改 spec** —— datas 增加上述条目；版本元数据按需 `from PyInstaller.utils.hooks import copy_metadata` + `datas += copy_metadata("dst-manager")`。
- [ ] **Step 2: 静态验证** —— `uv run python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`（确认版本号来源可读）；spec 语法检查 `uv run python -m PyInstaller --check packaging/dst-manager.spec 2>/dev/null || echo "check 不可用，留待 G9 构建验证"`（PyInstaller --check 若版本不支持则记录，留给 rc 构建验证）。
- [ ] **Step 3: 提交** —— `git commit -m "打包随附 LICENSE 与版本元数据"`
- 注：frozen 态真实验证（about 版本/LICENSE 读取、路径选择器）归 G9 手工清单，不在本任务声明完成。

### Task 8: ShellBridge `select_folder` 与前端桥封装

**Files:**
- Modify: `src/dst_manager/interfaces/shell.py:140` 附近（新增 `select_folder(self) -> str | None`，用 `webview.FOLDER_DIALOG`，模式与 `select_file` 一致）
- Modify: `web/src/api/shell.ts`（`ShellBridge` 类型加 `select_folder():Promise<string|null>`；新增 `selectSettingsPath(filter: "exe" | "dll" | "folder"): Promise<string | null | undefined>`——undefined = 桥不可用（浏览器开发态），调用方禁用"浏览"按钮；沿用"新方法缺失返回 null"降级模式）
- Test: `tests/unit/test_shell.py` 追加 `select_folder` 存在性与窗口未就绪抛错用例（参照既有 `select_file` 用例）

- [ ] **Step 1: 写失败测试**（test_shell.py 追加：`test_select_folder_requires_window`、`test_select_folder_uses_folder_dialog`——后者用 fake window 断言 `create_file_dialog` 收到 `webview.FOLDER_DIALOG`）
- [ ] **Step 2: 运行确认失败** —— `uv run pytest tests/unit/test_shell.py -q`
- [ ] **Step 3: 实现** —— 如上；文件过滤器常量在前端定义：`const EXE_FILTERS=["可执行程序 (*.exe)"]`、`const DLL_FILTERS=[".NET 程序集 (*.dll)"]`（pywebview 括号格式约束见 shell.ts 既有注释）。
- [ ] **Step 4: 运行通过 + 前端构建** —— `uv run pytest tests/unit/test_shell.py -q`；`cd web && npm run build`
- [ ] **Step 5: 提交** —— `git commit -m "ShellBridge 新增文件夹选择器与前端降级封装"`

### Task 9: 前端设置 API 客户端与 `useSettings` 组合式函数

**Files:**
- Create: `web/src/api/settings.ts`（类型 + `fetchSettings`/`putSettings`/`fetchAbout`，基于 `client.ts` 的 `request<T>`/`ApiError.fields`）
- Create: `web/src/composables/useSettings.ts`（模块级单例，模式同 `useTheme.ts`）
- Test: `web/test/settings.spec.ts`（若现有前端单测框架未覆盖 composable，则以 e2e 为准，跳过本文件——检查 `web/package.json` test 脚本后裁决，e2e 为最低要求）

**Interfaces（Produces）:**
```ts
export interface SettingsItem { key:string; label:string; category:string; control:"path"|"bool"|"int"|"enum";
  value:string|null|number|boolean; default:unknown; source:"default"|"env"|"file";
  hasFileOverride:boolean; nullable?:boolean; fileFilter?:string; min?:number; max?:number; options?:{value:number;text:string}[] }
export interface SettingsSnapshot { schemaVersion:number; configRevision:number; items:SettingsItem[]; diagnostics:{code:string;message:string}[] }
export function useSettings():{ snapshot:Ref<SettingsSnapshot|null>; loading:Ref<boolean>; load():Promise<void>;
  save(set:Record<string,unknown>, unset:string[]):Promise<void>;  // 409 → 抛 ApiError(409)；422 → ApiError.fields
}
```

- [ ] **Step 1: 实现 `settings.ts`** —— PUT 成功后用响应体整体替换快照；`ApiError.status===409`/`422` 原样上抛供对话框处理。
- [ ] **Step 2: 实现 `useSettings`** —— `save` 内部携带当前 `configRevision` 为 `expected_revision`；保存成功后把 `configRevision` 更新为响应值。
- [ ] **Step 3: 类型与构建验证** —— `cd web && npm run build`（零类型错误）
- [ ] **Step 4: 提交** —— `git commit -m "前端设置 API 客户端与 useSettings 状态"`

### Task 10: `SettingsDialog.vue` 模态对话框

**Files:**
- Create: `web/src/components/settings/SettingsDialog.vue`（分区结构 + 动态表单 + 状态机 + 键盘/焦点；对照 SPEC-DM-011 冻结截图 `assets/SPEC-DM-011/`）
- Modify: `web/src/components/ui/`（若需共享样式则建 `settings.css`，不新增全局规则）
- Test: `web/e2e/settings-dialog.spec.ts`（追加到既有 Playwright 套件）

**要点（对应 SC-02/03/04/05/06/07/08/09/12/14）:**
- 结构：`<dialog>` + 左分区列表（常规配置/关于）+ 右滚动面板；分组标题按 `category`。
- 控件映射：path=文本框+浏览（`selectSettingsPath`，undefined 时禁用）+清除（nullable，写入 `null`）；bool=checkbox；int=number（min/max）；enum=radio。
- 来源徽章：`默认/环境变量/用户覆盖` + 有覆盖时"恢复继承"链接（下一次保存随 `unset` 提交）。
- 编辑缓冲：本地 `edits` map，未保存字段 amber 边框；行内校验（int 范围）实时显示，错误字段红边框 + `role=alert`。
- 保存：按钮"保存中…"禁用；422 → `ApiError.fields` 逐字段显示并 focus 第一错误字段；409 → 提示"配置已被其他窗口修改"并重新 `load()`（输入保留）；成功 → toast"已保存"+ SC-13 条件提示（`enable_add_number_suffix`/`number_suffix_type`/`cad_max_parallel` 在本次 set 中时追加"相关预览将按新配置重算"）。
- 关闭守卫：有未保存修改时 Esc/✕/遮罩 → 复用 `ConfirmModal.vue` 确认（放弃/留在此处）；关闭后焦点归还触发按钮。
- 键盘：Esc 关闭、Tab 焦点圈闭于对话框内（`<dialog>` showModal 原生行为 + 显式归还）；打开时首字段聚焦。
- 诊断横幅：`diagnostics` 非空时面板顶部显示（损坏=amber；`SETTINGS_SCHEMA_NEWER`=红色只读，隐藏保存按钮）。
- 拖拽穿透：对话框打开时宿主拖拽回调无副作用（遮罩由 `<dialog>` 原生提供；e2e 断言 drop 事件不改变底层页面）。

- [ ] **Step 1: 写 e2e 失败测试**（`settings-dialog.spec.ts` 核心用例）

```typescript
// web/e2e/settings-dialog.spec.ts（用例全文两则，其余同构；夹具沿用既有 e2e 的启动模式，
// 通过 DST_MANAGER_SETTINGS_PATH 指向临时目录隔离配置）
import { test, expect } from "@playwright/test";

test("修改→保存→重开对话框值保留且来源变为用户覆盖", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByRole("dialog", { name: "设置" })).toBeVisible();
  const timeout = page.locator('input[data-key="cad_timeout_seconds"]');
  await timeout.fill("900");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("已保存")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "设置" }).click();
  await expect(timeout).toHaveValue("900");
  const row = page.locator('[data-key="cad_timeout_seconds"]').locator("..");
  await expect(row).toContainText("用户覆盖");
});

test("数字超范围显示行内错误且保存禁用", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置" }).click();
  const timeout = page.locator('input[data-key="cad_timeout_seconds"]');
  await timeout.fill("5000");
  await expect(page.getByText("必须在 1–3600 之间")).toBeVisible();
  await expect(page.getByRole("button", { name: "保存" })).toBeDisabled();
});
```

（e2e 需要后端注入 `RuntimeSettings(tmp store)` 的测试模式——在 Playwright 全局 setup 启动 `uv run dst-manager serve` 时设置 `DST_MANAGER_SETTINGS_PATH` 环境变量指向临时目录；为此 Task 5 的 `default_store()` 需尊重该环境变量——在 Task 5 实现时一并加入。）

- [ ] **Step 2: 运行确认失败** —— `cd web && npx playwright test e2e/settings-dialog.spec.ts`
- [ ] **Step 3: 实现组件** —— 按"要点"清单逐项实现；单文件若超 500 行则拆 `SettingsFormRow.vue`（单字段渲染）与 `SettingsDialog.vue`（容器/状态机）。
- [ ] **Step 4: 运行通过 + 生产构建** —— e2e 全绿；`npm run build` 零错误
- [ ] **Step 5: 提交** —— `git commit -m "新增设置中心模态对话框"`

### Task 11: TopBar 齿轮入口装配

**Files:**
- Modify: `web/src/layout/TopBar.vue`（主题按钮旁加齿轮按钮，`aria-label="设置"`，点击打开对话框并保持焦点归还）
- Modify: `web/src/App.vue`（不超过 5 行：挂载 `SettingsDialog`；SC-13 的 toast 复用 `useToast`）
- Test: `web/e2e/settings-dialog.spec.ts` 补入口用例（齿轮在未加载态可见/可聚焦/焦点归还）

- [ ] **Step 1: 补失败 e2e** —— `test("焦点归还:关闭设置后焦点回到齿轮按钮")`
- [ ] **Step 2: 实现装配** —— 如上；不改 TopBar 既有布局与样式令牌。
- [ ] **Step 3: 运行通过** —— `npx playwright test`（全量 e2e 无回归）+ `npm run build`
- [ ] **Step 4: 提交** —— `git commit -m "顶栏接入设置中心齿轮入口"`

### Task 12: 全量回归、G8 截图比对与文档收尾

**Files:**
- Modify: `changelog.md`、`docs/dst-manager/README.md`（索引状态）、`.planning/plans/dst-manager/PLAN-DM-019`（本文件状态与实际验证）、`docs/dst-manager/specs/SPEC-DM-011`（门禁记录 G7/G8/G9）

- [ ] **Step 1: 全量验证** —— `uv run ruff check .`；`uv run pytest -q`（基线 642 passed 不回归）；`uv lock --check`；`cd web && npm ci && npm run build && npx playwright test`
- [ ] **Step 2: G8 设计 QA** —— 生产实现 vs `assets/SPEC-DM-011/` 冻结截图同状态比对（默认/校验失败/保存/深色/诊断/最小视口）；逐项差异记入 SPEC-DM-011 门禁记录（缺陷/已接受差异/后续项）
- [ ] **Step 3: G9 清单登记** —— 桌面壳手工验收项写入 Plan「实际验证」待办：路径选择器真实弹窗（EXE/DLL）、外链系统浏览器、frozen about 版本/LICENSE、保存后真实 CAD 任务按新配置执行、移动绿色包后默认插件路径跟随
- [ ] **Step 4: 文档同步 + 提交** —— `git commit -m "设置中心交付与文档收尾"`

## 批次划分（G7）

- **批次 1 = Task 1–4**（纯后端配置域，可独立评审）
- **批次 2 = Task 5–7**(API + Worker 传播 + 打包，可独立演示：curl 验证端点)
- **批次 3 = Task 8–11**（前端纵向切片，可独立演示：对话框完整流程）
- **批次 4 = Task 12**（回归 + QA + 收尾）

## 实际验证

（实施中按批次回填：命令、通过数、偏差记录、G8 差异裁决、G9 手工验收状态。）
