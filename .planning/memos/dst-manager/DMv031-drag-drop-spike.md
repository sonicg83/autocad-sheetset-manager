# DMv031 拖拽文件路径 Spike 结论与落地决策

- 日期：2026-09-03
- 关联：PLAN-DM-011 Task 8；SPEC-DM-007 §3.2（拖拽路径约束）、§10 修订记录
- 环境：Windows 11（RDP 会话已断开但仍持有交互桌面）、WebView2 Runtime、pywebview 5.4（WinForms/EdgeChromium 后端）、pythonnet 3.1.0、Python 3.13.5
- 结论：**可行 —— pywebview ≥5 原生暴露拖拽文件路径，采用原生桥落地，不走 WinForms IDropTarget 降级。**

---

## 1. 三条验证路径的方法与结论

### 路径 1：pywebview ≥5 的 EdgeChromium 后端是否原生暴露拖拽文件路径 —— **可行（原生机制存在且完整）**

**代码证据（已安装的 pywebview 5.4 源码，非记忆）：**

- `webview/js/api.js` `_jsApiCallback` 的 `edgechromium` 分支：检测到 `drop` 事件且 `dataTransfer.files` 非空时，调用
  `chrome.webview.postMessageWithAdditionalObjects('FilesDropped', files)`（WebView2 专属 API，携带真实 `CoreWebView2File`），再走常规 `postMessage` 把事件转发到 Python。
- `webview/platforms/edgechromium.py` `on_script_notify`：收到 `"FilesDropped"` 后从 `get_AdditionalObjects()` 提取 `CoreWebView2File` 的 `Path`，写入 `webview.dom._dnd_state['paths']`。
- `webview/util.py` `js_bridge_call` 的 `pywebviewEventHandler` 分支：事件类型为 `drop` 时按 basename 匹配 `_dnd_state['paths']`，把绝对路径注入事件字典文件的 `pywebviewFullPath` 字段，随后调用 Python 侧 `window.dom.<element>.on('drop', cb)` 注册的回调。
- 因此 pywebview ≥5 的 EdgeChromium 后端**原生**提供拖拽文件绝对路径，无需 WinForms `IDropTarget` 手工拦截。该机制仅 EdgeChromium/WebView2 存在（Windows 专属），与本项目栈一致。

**实机验证（最小 demo，见 §2）：**

- 真窗口注册 `document.on('drop', DOMEventHandler(cb, prevent_default=True, stop_propagation=True))` 后，JS 派发 drop 事件，Python 回调被触发（`files=[]` 空拖拽正常送达）。
- **环境限制（如实记录）**：本机为 RDP 会话且已断开，输入桌面不活跃 —— `SetCursorPos`/`SetPhysicalCursorPos`/`SendInput` 全部失败、`GetCursorPos` 恒为 `(0,0)`。OLE `DoDragDrop` 依赖光标命中测试，因此**无法在本机完成字面意义上的"从资源管理器拖文件进窗口"**。已尝试自研 OLE CF_HDROP 拖放源（C# 编译 DragSim.dll，pythonnet 进程内调用）与 CDP `Input.dispatchDragEvent`（携带真实磁盘文件路径）：前者因光标死区无法命中目标窗口，后者能派发 DOM drop 事件但 WebView2 只把真实 OS 拖拽产生的 `CoreWebView2File` 作为 additional objects，合成/CDP 文件不会进入 `_dnd_state['paths']`，故 `pywebviewFullPath` 不会填充（该现象本身也佐证了 §1 的代码路径）。这正是"原生路径依赖 OS 级拖拽"的预期行为，不是缺陷。
- 结论：原生机制在代码层面完整、已接线，桥与前端落地在本机可注册、可运行（见 §4 冒烟）；OS 级拖拽的最后一跳因断开的 RDP 会话无法在本机复现，按任务书要求如实记录，不伪造通过结果。

### 路径 2：WinForms 宿主注册 `IDropTarget` 拦截 —— **不需要（路径 1 可行即不再走此降级）**

任务书要求"若不暴露"才走此路径；路径 1 已暴露，故不实施。补充依据：WebView2/Chromium 已在其窗口上注册 OLE `IDropTarget` 并消费 OS 拖放；若在 WinForms 宿主再注册一个竞争性 `IDropTarget`，会与 HTML5 drop（以及 pywebview 的原生 FilesDropped 机制）冲突，正是任务书 Step 1.3 要规避的"原生 drop 与页面 JS 冲突"场景。

### 路径 3（Step 1.3）：拖拽期间页面 JS 不被原生 drop 触发默认导航 —— **通过**

实机验证（demo3）：注册 `DOMEventHandler(prevent_default=True, stop_propagation=True)` 后派发多次 drop，页面 URL 始终保持在 `about:blank`（`NAV=False`，`VERDICT_NAV_PREVENTED=True`）。落地实现沿用同一参数，保证拖入文件不会把页面导航到 `file://`。

## 2. 实机验证证据（minimal demo 与输出）

均在 `%TEMP%\dstmgr-dnd-spike\` 下运行（不进入仓库）：

| demo | 目的 | 关键输出 |
| --- | --- | --- |
| `demo1.py` + `DragSim.dll`（OLE CF_HDROP 拖放源） | 尝试 OS 级 OLE 拖放 | 窗口 rect 有效 `(535,173)-(2024,1195)`，但光标定位失败 `cursor at (0,0)`；DoDragDrop 无目标可命中 |
| `demo2.py`（CDP `Input.dispatchDragEvent`，携带真实磁盘文件） | 派发真实 DOM drop | `dragEnter/dragOver/drop -> {}` 全部成功，但合成文件不产生 `CoreWebView2File`，pywebview 回调未收到（佐证 §1 路径 1 的过滤逻辑） |
| `demo3.py`（JS 派发 drop） | 验证桥送达 + 默认导航拦截 | Test A 空拖拽：`DROP_EVENT files=[] NAV=False`、`VERDICT_NAV_PREVENTED=True`、`VERDICT_BRIDGE=WORKS`；Test B 合成文件：原始 DOM drop 到达（rawDrops=2）但无 `CoreWebView2File` 故未送达 Python（与路径 1 代码分析一致） |
| `demo4.py`（生产 `ShellBridge` 真窗口冒烟） | 落地桥在真实窗口注册与运行 | `on_files_dropped registered OK`、空拖拽/文件拖拽均不崩溃、`VERDICT=OK` |

## 3. 落地（最小范围）

按任务书 Step 2 可行分支：

- `src/dst_manager/interfaces/shell.py`
  - 新增 `ShellBridge.on_files_dropped(callback_id)`：前端传入全局 JS 函数名，桥在 `window.dom.document` 注册 drop 监听（`prevent_default=True, stop_propagation=True`，幂等），命中真实拖拽后把 `pywebviewFullPath` 经 `window.evaluate_js` 调 `window[callback_id](path)` 转交前端。未绑定窗口抛 `RuntimeError`。
  - `run_desktop` 顺手把 `settings` 转发给 `create_app(settings)`（Task 8 交办的上游 minor）。
- `web/src/api/shell.ts`：`ShellBridge` 类型补充 `on_files_dropped(callbackId:string):Promise<void>`。
- `web/src/App.vue`：`selectAndOpenDst` 抽出 `acceptDstPath(path)`（复用同一 `.dst` 校验 + `openByPath`，新增"已打开工作区时拒绝拖入并提示"防御）；`onMounted` 在壳存在时注册全局 `window.__dstManagerAcceptDst` 并调 `bridge.on_files_dropped('__dstManagerAcceptDst')`；未打开态"选择 DST 文件"按钮下加一行 `.drop-hint`（"或将 .dst 文件拖入窗口"）。
- 单测：`tests/unit/test_shell.py` 新增 4 项（未绑定报错、监听器幂等注册、命中路径转发 JS 调用、无 `pywebviewFullPath` 忽略），合计 7 项通过。
- e2e 不覆盖拖拽（Playwright 无法模拟 OS 级 drop），按任务书以手动冒烟记录（demo4）。

**偏离任务书文本（已如实对齐仓库现实）：**

1. 任务书 Step 2 描述的可行落地为"前端可感知的 `on_files_dropped(callback_id)` 回调注册"，落地保持该桥面，但事件源是 pywebview 原生 DOM drop（Python 侧监听），而非前端元素监听后回传——这是 pywebview 原生机制的正确用法（浏览器 JS 拿不到绝对路径，路径必须经 Python 侧 `pywebviewFullPath` 获得）。
2. 监听注册在 `document`（整窗即热区）而非特定热区元素，避免 Vue 渲染时序问题；已打开态由前端 `acceptDstPath` 防御拒绝。

## 4. 验证

- `uv run pytest tests/unit/test_shell.py -q`：7 passed。
- `uv run ruff check .`：All checks passed。
- `cd web && npm run build`：vue-tsc + vite 零类型错误。
- 真窗口冒烟（demo4）：`on_files_dropped` 注册与 drop 处理正常，无异常。

## 5. 结论

- 拖拽文件路径采用 pywebview 原生能力落地，不做 WinForms IDropTarget 降级；SPEC-DM-007 §3.2 的 `on_drop(cb)` 由"视实现可行性"更新为已实现桥 `on_files_dropped(callback_id)`，§10 追加本次修订记录。
- 本机因 RDP 会话断开无法复现 OS 级拖拽最后一跳，需在有活跃输入桌面的机器上做一次人工拖拽冒烟（连接桌面会话后拖入 `.dst`，应直接打开工作区）。
