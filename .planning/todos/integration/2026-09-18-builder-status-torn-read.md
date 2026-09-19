# Builder 构建状态接口撕裂读缺陷待办

日期：2026-09-18

状态：未立项；待建立独立修复计划（该缺陷会以约 1/8 的概率让相关测试偶发失败）

关联：`PLAN-INT-002`、`MEMO-INT-001`

## 目的

记录并修复 `GET /api/builds/{id}` 的读一致性缺陷：该端点可能返回 `status="SUCCEEDED"` 而 `published_path=None`——一个在任何单一时刻都不曾真实存在的状态组合。这类缺陷称为**撕裂读（torn read）**。

该缺陷在 `PLAN-INT-002`（取消 Builder → Manager 交接契约）执行期间由新增的替代主路径集成测试暴露，**不是该计划引入**，但该计划刻意未修：修法涉及共享持久层的读事务与隔离语义，需要独立计划与其自身的回归分析。

## 症状与复现

- 症状签名：`status == "SUCCEEDED"` 且 `published_path is None`。
- 复现率：连跑单个测试 8 次失败 1 次（约 12.5%；实施者先前估约 2.5%）。竞态，概率随机器负载变化。

```powershell
# 连跑量化（不加 -q：addopts 已含 -q，再加会变 -qq 并吞掉计数行）
for ($i=1; $i -le 8; $i++) { uv run python -m pytest tests/builder/integration/test_build_api.py::test_full_build_reaches_succeeded_and_publishes_package -p no:cacheprovider }
```

## 根因（证据等级：推断，尚未逐语句插桩直接观测）

写侧是原子的，撕裂发生在读侧。

- **读**：`src/dst_builder/application/builds.py` 的 `get_build` 在同一 `sessions.begin()` 内做两次独立仓储读取——`load_build_run`（取 `published_path`）与 `list_attempts`（取 `status`）。两个字段来自**两张表、两条 SELECT**。
- **写**：`_commit_transition` 在**同一个事务**内更新 attempt 行（`status`）与 run 行（`published_path`、`finished_at`）；`repositories.py` 的方法只 `flush()` 不 `commit()`。因此写侧不会产生混合视图。
- **为什么两条 SELECT 不在同一快照**：`src/dst_builder/infrastructure/persistence/database.py` 用 `create_engine(f"sqlite:///{db_path}", poolclass=NullPool)`，**没有** `isolation_level`、**没有** `connect_args`、**没有** `BEGIN` 事件钩子。Python 的 `sqlite3` 驱动在默认 legacy 模式下**只为 DML 隐式开启事务，不为 SELECT 开启**；SQLAlchemy 的 `Session.begin()` 只是它自己的逻辑事务记账。于是每条 SELECT 各自在 autocommit 读中取一次当时已提交的状态。
- **排除的替代假设**：曾怀疑 SQLAlchemy 默认 `expire_on_commit=True` 导致 `with` 块之外访问 `run.published_path` 时惰性重读；该仓库显式设了 `expire_on_commit=False`，属性不过期，故不成立。

证据等级说明：上述是唯一能同时解释「症状签名 + 两条独立 SELECT + 无隔离配置 + 写侧原子 + 复现率」的解释，`PLAN-INT-002` 的最终审查者也独立追查写侧并表示同意；但**未做逐语句插桩直接观测那次交错**。修复计划的第一步应是加一条可复现的插桩测试把机制钉死，再动手改隔离语义。

## 影响

- **用户可见且非自愈**：`builder-web/src/steps/BuildStep.vue` 在收到 `SUCCEEDED` 时置 `buildSucceeded` 并**停止轮询**，而「已发布：<路径>」仅在 `published_path` 非空时渲染。若撕裂恰好落在作为终态的那次轮询上，轮询停止，用户会看到「构建成功」却看不到成果位置，直到手动重新触发一次加载。
- **不是发布安全问题，也不是数据损坏**：磁盘上的成果完整正确，构建确实成功。本缺陷纯属读一致性——接口报告了一个不存在的状态组合。
- **测试噪声源**：任何断言终态 `published_path` 的测试都会继承该抖动（见下）。

## 仍暴露的测试

- `tests/builder/integration/test_build_api.py:103`（`assert final["published_path"] == str(env.target)`）
- `tests/builder/integration/test_minimal_loop_fake_cad.py:173`（同上）

两者都经 `tests/builder/integration/conftest.py` 的 `wait_terminal` 取得终态响应——该辅助函数见到终态立即返回，因此可能返回撕裂读的结果。

`tests/builder/integration/test_builder_output_opens_in_manager.py::_publish` 已在 `PLAN-INT-002` 的最终修复波中加入一次**有界重读**（只在 `status == "SUCCEEDED" and not published_path` 这一精确签名上重读一次，重读后仍为空则断言照旧失败），因此不再继承该抖动。该守卫是可复用的参考写法。

## 候选修法（均非机械改动，需在修复计划中评估）

| 方案 | 代价 |
| --- | --- |
| 两条读合成一条语句（JOIN） | 改仓储 API 与查询形状 |
| 让 SELECT 进入真正的读事务（`BEGIN` 事件钩子 / `isolation_level` / `connect_args`） | **影响该引擎上所有读路径**（`stream_events`、`cancel_build`、启动恢复等），需重新分析快照语义、WAL 行为与 `NullPool` 只读不遗留 `-wal`/`-shm` 的既有约束 |
| 让 `status` 与 `published_path` 同源（如把 `published_path` 挪到 attempt 行） | 契约变更 + 迁移 |

不建议「读侧重试」作为修复：它掩盖缺陷而非消除它。

**修 `get_build` 时必须一并评估**：其余多语句读者是否同样暴露（`cancel_build`、事件流、启动恢复），以及 `NullPool` + 只读打开不产生 `-wal`/`-shm` 的要求是否与显式读事务冲突。

## 完成条件

- 有独立修复计划，并在其中**先用插桩测试复现并钉死机制**，再改隔离语义；
- 上述两处测试不再偶发失败，且不靠「失败重跑」掩盖；
- `NullPool` 与只读打开不遗留 `-wal`/`-shm` 的既有约束仍满足；
- 若采纳「同源字段」方案，提供迁移并验证全新库与既有库双向可用。
