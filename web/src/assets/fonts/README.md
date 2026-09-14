# 本地字体资产溯源与复核

本目录存放 PLAN-DM-029 Task 2 引入的两套生产字体子集，以及它们的许可证文本。字体随 Web 产物
本地打包，**运行时不得访问 CDN**；`web/scripts/ui-contracts/font-assets.mjs` 以
`missing-font-asset`、`remote-font-url`、`font-budget-exceeded` 三条硬门禁看守这一约束。

| 产物 | 上游 | 上游版本 | 字节 |
| --- | --- | --- | --- |
| `InterLatin.woff2` | Inter 4.1 发行包（`Inter-4.1.zip` 内 `web/InterVariable.woff2`），可变字体 | `name` 表 `Version 4.001;git-9221beed3`；含 `fvar` 轴 `opsz`、`wght` | 56928 |
| `IBMPlexMonoLatin.woff2` | npm `@ibm/plex-mono@2.5.0`（`IBMPlexMono-Regular`），静态实例 | `name` 表 `Version 2.005`；无 `fvar` 轴 | 12488 |
| `OFL-Inter.txt` | Inter 发行包内许可证 | — | 4366 |
| `OFL-IBM-Plex-Mono.txt` | npm 包内许可证 | — | 4363（git blob；工作区落盘 4456 字节为 CRLF 行尾） |

身份不是按文件名断定的，而是用 fontTools 直读 `name` 表与 `fvar` 表实测得出（见下方复核命令）。

## 声明字符集

`web/src/styles/tokens.css` 两处 `@font-face` 的 `unicode-range`：

```text
U+0020-007E, U+00A0-00FF, U+2013-2014, U+2018-201D, U+2026
```

即 Basic Latin、Latin-1 Supplement，加上界面实际使用的通用标点（– — ‘ ’ ‚ ‛ “ ” …）。**不含任何
CJK 码位**，中文继续回落系统字体（Microsoft YaHei → `system-ui`），与 ARCH-DM-007 §4.2 一致。

实测覆盖（`cmap` 直接读取）：两套字体各 **199** 个表意码位，最小 `U+0020`、最大 `U+2026`，全部落在
声明范围内；CJK 统一表意文字、CJK 扩展 A、CJK 符号与标点、全角形式、中日韩部首补充、平假名、片假名、
谚文音节命中数均为 **0**。声明范围与实取数量的差别来自上游字体本身未提供的码位（Inter 有 `U+201A`
与 `U+201B`，IBM Plex Mono 少 `U+201B`）。

## 复核方法（可复制执行）

依赖系统 Python 3.13 + fontTools 4.59.0（`pyftsubset` 可在 `/c/Python313/Scripts/pyftsubset`）。**项目
`pyproject.toml` / `uv.lock` 不含 fontTools**，这些命令只用于人工复核，不进入 CI 依赖（Ruling 9）。

```powershell
# 1. 体积与身份
Get-ChildItem web/src/assets/fonts/*.woff2 | Select-Object Name, Length
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'web/src/assets/fonts/InterLatin.woff2'); print(f['name'].getDebugName(1), '|', f['name'].getDebugName(5), '|', [a.axisTag for a in f['fvar'].axes] if 'fvar' in f else '静态')"
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'web/src/assets/fonts/IBMPlexMonoLatin.woff2'); print(f['name'].getDebugName(1), '|', f['name'].getDebugName(5), '|', [a.axisTag for a in f['fvar'].axes] if 'fvar' in f else '静态')"

# 2. 码位数、最大码位与 CJK 扫描（两个文件各跑一次）
python -c "from fontTools.ttLib import TTFont; c=TTFont(r'web/src/assets/fonts/InterLatin.woff2').getBestCmap(); print(len(c), hex(min(c)), hex(max(c)))"
```

Chromium 侧只需确认产物真的被加载且无远程请求，可由 Task 2 已落地的三条 e2e 断言覆盖
（`web/tests/e2e/main.spec.ts` 的 `-g Task 2` 用例：控件计算字体栈含 `Inter`/`IBM Plex Mono`、
`document.fonts` 就绪后的 `unicode-range` 码位区间覆盖 Basic Latin 且不含 CJK）。

## 已知保留项：子集化命令行未经证实

**两套 WOFF2 的原始 `pyftsubset` 命令行没有留下记录，复核时无法逐字复原**，因此本目录不声称
「按某条命令可复现」：

- npm 包 `@ibm/plex-mono@2.5.0` 内没有 TTF/OTF，只有 `fonts/complete/woff/IBMPlexMono-Regular.woff`
  （66924 字节）与对应 WOFF2。用包内 `woff` 原件按声明范围重跑子集化得 **11220 字节 ≠ 已入库
  12488 字节**（疑似原命令保留了 hinting），据此不可用复原物替换已入库产物。
- `Inter-4.1.zip` 在当时的构建环境不可达，无法取到原件重跑。

因此本目录只声明**已实测**的四类事实：上游身份与版本、字符集与标点覆盖、工具版本、精确字节数与
预算余量（合计 69416 ≤ 256000）。若需要命令级可复现，必须在可访问上游的环境重做子集化，并同步替换
产物、复核体积/字符集/浏览器加载三类证据——该保留项已登记在
`.planning/plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md` 的 Task 12 收口责任。
