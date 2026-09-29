# 集成测试夹具导入依赖收集顺序

日期：2026-09-29

状态：待办（尚未被任何计划承接；来源：PLAN-DM-036 Task 9 收尾验证时发现）

关联：`PLAN-DM-036`

## 背景

`tests/integration/test_standard_delete.py` 从 `tests/unit/` 目录导入共享夹具模块 `creation_xlsx_fixtures`（`from creation_xlsx_fixtures import STANDARD_DOCUMENT`）。仓库的 `[tool.pytest.ini_options]` 没有配置 `pythonpath`，`tests/unit` 能被导入只是因为 pytest 对无 `__init__.py` 的测试目录按「rootdir 插入」把该目录加入 `sys.path`；因此该导入是否成功取决于收集顺序。

## 实测证据（2026-09-29，临时文件已删除）

- 单跑该文件：`uv run pytest tests/integration/test_standard_delete.py -q -o addopts=""` → `ModuleNotFoundError: No module named 'creation_xlsx_fixtures'`，1 个收集错误，退出码 1。
- 与任一单元测试同跑：`uv run pytest tests/unit/test_shell_workspace.py tests/integration/test_standard_delete.py -q -o addopts=""` → **33 passed**（单元目录先进入 `sys.path`）。
- 默认并行全量：`uv run pytest -q` 在该文件先被收集时以同一收集错误失败；加 `--ignore=tests/integration/test_standard_delete.py` 时 **2151 项 / 74 skipped / 0 failed**。
- 该测试文件与 `pyproject.toml` 在排查中均未被修改（`git diff` 为空），故属既有缺陷，不是那一次改动引入。

## 影响

并行收集顺序变化时全量 pytest 会以 1 个收集错误退出，掩盖真实回归信号，并与 AGENTS.md「测试不得依赖执行顺序」相悖。

## 候选修复（择一，未实施）

1. 把 `creation_xlsx_fixtures.py` 移到 `tests/` 根目录（或 `tests/fixtures/` 并配 `conftest.py`），并在 `pyproject.toml` 登记 `pythonpath`——语义最清晰，但要同步更新 `tests/unit` 内 6 处导入。
2. 仅补 `pythonpath = ["tests/unit"]`——改动最小，但把「单元夹具」暴露给全部测试。
3. 把该用例需要的夹具下沉到 `tests/integration/` 自己的夹具模块——不动单元侧，代价是标准文档夹具出现第二份副本（与「同一内容只保留一个权威位置」冲突，不推荐）。

## 验收

`uv run pytest -q` 与单跑该文件都必须通过，且结果不随 xdist 收集顺序变化。
