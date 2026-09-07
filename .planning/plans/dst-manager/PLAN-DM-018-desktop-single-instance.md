---
id: PLAN-DM-018
title: 桌面壳单实例守卫实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-07
updated: 2026-09-07
related:
  - SPEC-DM-007
  - ARCH-DM-002
  - PLAN-DM-014
---

# 桌面壳单实例守卫实施计划

> **来源：** 用户对运行日志 `tests/user-feedback/logs/user-weng/` 的错误分析（
> `PUBLISH_RECOVERY_FAILED`、`WinError 32 发布 journal 被占用`）提出诉求：
> 限制 DST Manager 只能有一个实例；再打开一个时弹窗报错，并把已启动实例的窗口切到最前。

**Goal:** 桌面壳（pywebview/WebView2，唯一交付入口，SPEC-DM-007）同一 Windows 会话只允许一个实例。第二个实例启动时弹置顶告警框，用户点击“确定”后由后启动进程把既有窗口还原（若最小化）并置前，然后退出——避免双实例同时操作同一工作区的 `.dst-manager` 锁、发布 journal 与 SQLite 任务队列造成踩踏。

**Architecture:** 新增 `src/dst_manager/infrastructure/single_instance.py`，仅标准库 + ctypes 直调 Win32（不引入 pywin32）：

- **命名互斥量**（`CreateMutexW`，`Local\` 会话级命名空间）：内核对象，进程退出（含崩溃）自动释放、不遗留陈旧锁；互斥量名按 `%LOCALAPPDATA%/dst-manager` 用户维度确定性派生，不同 Windows 用户互不阻断。
- **前台唤起**由“后启动”进程执行：它刚被 Shell 激活、持有前台权限，才能可靠调用 `SetForegroundWindow`（Windows 前台锁规则）；最小化窗口先经 `ShowWindow(SW_RESTORE)` 还原，前台锁拦截时退化为任务栏闪烁兜底。
- 平台开关 `WINDOWS` 为模块级常量，非 Windows（Linux CI）直接放行；`base` 注入参数仅供测试。

**Tech Stack:** Python 3.12 + uv、ctypes/Win32（user32、kernel32）、Win11。

**Spec:** 无独立 SPEC；本计划为桌面壳进程生命周期加固，范围由用户裁决：仅限制桌面壳 `desktop` 入口，`serve`/`doctor`/`worker`（壳子进程，天然同实例）不受限；唤起顺序为“弹窗 → 用户确认 → 切换”。

## Global Constraints

- 全程简体中文注释与用户文案；标识符保持英文。
- 开发态零行为变化：非 Windows 或首个实例启动路径与现状等价。
- 不引入新依赖（不触碰 `pyproject.toml` / `uv.lock`）。
- 不新增 API 端点、不改 API 契约；守卫只发生在进程层。
- 发布安全基线（DST/DWG 发布器、SCR、锁与事务）不涉及。
- 每个 task 完成时更新根目录 `changelog.md`；commit message 简体中文、动词开头。
- Python 验证基线：`uv run ruff check .` 与 `uv run pytest -q` 全绿（基线 628 passed / 72 skipped，本计划应新增约 10 项单测）。

---

### Task 1: 单实例守卫模块 `single_instance.py`

**Files:**
- Create: `src/dst_manager/infrastructure/single_instance.py`
- Test: `tests/unit/test_single_instance.py`

**Interfaces:**
- Consumes: 仅标准库（`ctypes`、`hashlib`、`os`、`sys`、`time`、`pathlib`）。
- Produces: `acquire_instance_mutex(key_base=None) -> int | None`（None=已有实例；
  非 Windows 返回放行标记 `_NO_GUARD_REQUIRED`）；`release_instance_mutex(guard) -> None`；
  `notify_already_running_and_raise(title=APP_WINDOW_TITLE) -> None`（弹窗→确认→唤起既有窗口）；
  `find_app_window(title, attempts, delay) -> HWND | None`；`restore_and_foreground(hwnd) -> bool`
  。窗口标题常量 `APP_WINDOW_TITLE = "DST Manager"` 与壳的 `create_window` 共用。

- [x] **Step 1: 写失败测试**

```python
"""桌面壳单实例守卫单测：互斥量名称派生、先启动持锁/后启动被拒、释放重入、
唤起容错与非 Windows 放行。Windows 内核对象用例在非 Windows 平台跳过。"""
```

要点：互斥量名称确定性（同 base 同值、不同 base 不同值、固定前缀 + 12 位摘要）；
真实内核互斥量先拿后拒、释放重入（Windows 实跑）；`WINDOWS=False` 模拟下放行标记
不等于“第二个实例”、release 无事发生；`find_app_window` 找不到窗口容错返回 None；
`notify_already_running_and_raise` 全流程不抛异常且向 stderr 报告。

- [x] **Step 2: 实现模块**

关键实现决策：

1. **两段式取锁**：先 `OpenMutexW(SYNCHRONIZE)` 探测存在性（命中即关闭句柄返回
   “非唯一”），再 `CreateMutexW` 建立；创建返回 `ERROR_ALREADY_EXISTS` 说明竞态中
   另有进程抢先，同样判为“非唯一”。消除句柄复用歧义。
2. **句柄类型**：`CreateMutexW`/`OpenMutexW` 的 `restype` 必须为 `ctypes.c_void_p`，
   否则 64 位 Windows 上句柄被截断。
3. **唤起顺序**（用户裁决）：`MessageBoxW`（`MB_TOPMOST|MB_SETFOREGROUND|MB_ICONWARNING`）
   置顶报错 → 用户点确定 → `find_app_window` 依标题找 HWND → `ShowWindow(SW_RESTORE)` +
   `SetForegroundWindow`，失败则 `FlashWindow` 闪烁任务栏兜底。
4. **容错**：唤起全程 best-effort（首个实例仍在启动窗口未建时找不到 HWND 就直接退出，
   不抛异常、不影响“报错”本身）。

- [x] **Step 3: 集成 `run_desktop`**

`src/dst_manager/interfaces/shell.py`：`run_desktop` 起点获取守卫——`guard is None`
时调用 `notify_already_running_and_raise()` 后 `return`；否则以 `try/finally` 包住既有
启动体，`finally` 中 `release_instance_mutex(guard)`。`create_window` 标题改引
`APP_WINDOW_TITLE` 常量。Worker 由壳拉起不触碰守卫。

### Task 2: 验证

- [x] **Step 1: 自动化门禁**

```powershell
$env:UV_LINK_MODE = "copy"
uv run ruff check src/ tests/
uv run pytest tests/unit/test_single_instance.py tests/unit/test_shell.py -q
uv run pytest -q   # 全量
```

实际结果：ruff 全绿；单实例 10 项单测全过（含真实互斥量持锁/被拒/重入）；
全量 **638 passed / 72 skipped（0 失败）**，相对既有基线 628 恰好 +10，无回归。

- [x] **Step 2: 真实桌面冒烟（人工）**

需用户在本机 Windows 11 + pywebview(WebView2) 环境手动复验：
1. 双击/命令行启动一次 `uv run dst-manager desktop`；
2. 再次启动第二个实例：应弹“已在运行”置顶告警框，点确定后第一个实例窗口被还原并置前，第二个实例退出；
3. 最小化第一个实例后重复第 2 步：窗口应被还原后再置前；
4. Worker 子进程退出时互斥量自动释放，第三次启动不受影响。

## 实际验证

- 自动化：`uv run ruff check .` 通过；`uv run pytest -q` 全量 **638 passed / 72 skipped / 0 failed**（新增 10 项单实例单测，其余无回归）。
- 待用户完成：本机真实桌面双开冒烟（见 Task 2 Step 2）。
- 未执行：真实 AutoCAD 系统测试（按仓库约定需 `DST_MANAGER_RUN_AUTOCAD=1` 显式启用，本改动不涉及 CAD 链路）。