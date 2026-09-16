# 本地字体资产溯源与复核

本目录存放 PLAN-DM-029 Task 2 引入的两套生产字体子集，以及它们的许可证文本。字体随 Web 产物
本地打包，**运行时不得访问 CDN**，这条约束由四条硬门禁看守——它们在
`web/scripts/ui-contracts/types.mjs` 的 `NON_EXEMPTIBLE_RULES` 里被固定为不可登记例外，实现与落地
在 `web/scripts/ui-contracts/font-assets.mjs`：`missing-font-asset`、`remote-font-url`、
`font-budget-exceeded` 针对字体资产本身（文件在不在、路径是不是远程、合计是否超预算），
`entry-stylesheet-not-import-only` 针对样式入口结构（`src/style.css` 必须存在且只能是分层入口）。

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

声明集合共 **200** 个码位；两套字体各实际提供 **199** 个（`cmap` 直读），实测差集如下：

| 字体 | 声明码位 | 实取码位 | 字体未提供的声明码位 | 声明范围外的码位 |
| --- | --- | --- | --- | --- |
| `InterLatin.woff2` | 200 | 199 | `U+00AD`（软连字符） | 无 |
| `IBMPlexMonoLatin.woff2` | 200 | 199 | `U+201B`（‛ 单高反引号） | 无 |

`U+00AD` 是 Latin-1 Supplement 里的软连字符（不可见，只用于断行提示），上游 Inter 未提供该字形；
`U+201B` 由 Inter 提供、上游 IBM Plex Mono 未提供。**`unicode-range` 声明的是「允许该字体参与哪些
码位」，不是「保证字形齐备」的清单**：声明里包含字体未提供的码位不会让子集产物出问题，浏览器在本
字体缺字形时按字体栈继续回退。两套字体都没有任何声明范围外的码位（越界 0），缺失码位也都不落在
Basic Latin（`U+0020-007E`）区间内，因此那 95 个码位是完整覆盖的。

CJK 统一表意文字、CJK 扩展 A、CJK 符号与标点、全角形式、中日韩部首补充、平假名、片假名、谚文音节
命中数均为 **0**（命令见下）。

## 复核方法（可复制执行）

依赖系统 Python 3.13（本机 `python --version` → `Python 3.13.5`）+ fontTools 4.59.0
（`pyftsubset` 位于 `C:\Python313\Scripts\pyftsubset.exe`）。
**项目 `pyproject.toml` / `uv.lock` 不含 fontTools**：子集化是一次性构建动作、产物入库，把这些命令
留作人工复核即可，不把 fontTools 变成 CI 依赖。复核义务与保留项见本文件末两节，以及
`.planning/plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md` 的 Task 2 Step 1
（资产核验）与 Task 12 收口责任。

以下命令在仓库根目录逐条执行（默认 PowerShell），输出与「实测输出」一致。**本节所有命令都已实际
执行成功**。

### 1. 体积与身份

```powershell
Get-ChildItem web/src/assets/fonts/*.woff2 | Select-Object Name, Length
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'web/src/assets/fonts/InterLatin.woff2'); print(f['name'].getDebugName(1), '|', f['name'].getDebugName(5), '|', [a.axisTag for a in f['fvar'].axes] if 'fvar' in f else 'static')"
python -c "from fontTools.ttLib import TTFont; f=TTFont(r'web/src/assets/fonts/IBMPlexMonoLatin.woff2'); print(f['name'].getDebugName(1), '|', f['name'].getDebugName(5), '|', [a.axisTag for a in f['fvar'].axes] if 'fvar' in f else 'static')"
```

实测输出：

```text
Name                   Length
----                   ------
IBMPlexMonoLatin.woff2  12488
InterLatin.woff2        56928

Inter Variable | Version 4.001;git-9221beed3 | ['opsz', 'wght']
IBM Plex Mono | Version 2.005 | static
```

### 2. 码位数与最大码位（两个文件各跑一次）

```powershell
python -c "from fontTools.ttLib import TTFont; c=TTFont(r'web/src/assets/fonts/InterLatin.woff2').getBestCmap(); print(len(c), hex(min(c)), hex(max(c)))"
python -c "from fontTools.ttLib import TTFont; c=TTFont(r'web/src/assets/fonts/IBMPlexMonoLatin.woff2').getBestCmap(); print(len(c), hex(min(c)), hex(max(c)))"
```

实测输出：

```text
199 0x20 0x2026
199 0x20 0x2026
```

### 3. 声明范围与实取集合的差集（两个文件各跑一次）

`d` 由 `@font-face` 的 `unicode-range` 逐段展开；`font-missing` 是「声明了但字体没有」，`out-of-declared`
是「字体有但没声明」——后者必须为空，否则实际使用面会超出声明。

```powershell
python -c "from fontTools.ttLib import TTFont; d=set(range(0x20,0x7F))|set(range(0xA0,0x100))|set(range(0x2013,0x2015))|set(range(0x2018,0x201E))|{0x2026}; c=set(TTFont(r'web/src/assets/fonts/InterLatin.woff2').getBestCmap()); print('declared', len(d), 'actual', len(c), 'font-missing', [hex(u) for u in sorted(d-c)], 'out-of-declared', [hex(u) for u in sorted(c-d)])"
python -c "from fontTools.ttLib import TTFont; d=set(range(0x20,0x7F))|set(range(0xA0,0x100))|set(range(0x2013,0x2015))|set(range(0x2018,0x201E))|{0x2026}; c=set(TTFont(r'web/src/assets/fonts/IBMPlexMonoLatin.woff2').getBestCmap()); print('declared', len(d), 'actual', len(c), 'font-missing', [hex(u) for u in sorted(d-c)], 'out-of-declared', [hex(u) for u in sorted(c-d)])"
```

实测输出：

```text
declared 200 actual 199 font-missing ['0xad'] out-of-declared []
declared 200 actual 199 font-missing ['0x201b'] out-of-declared []
```

### 4. CJK 区段扫描（两个文件各跑一次）

`R` 是 CJK 相关区段：CJK 部首补充、CJK 符号与标点、平假名、片假名、CJK 扩展 A、CJK 统一表意文字、
谚文音节、全角形式。

```powershell
python -c "from fontTools.ttLib import TTFont; R=[(0x2E80,0x2FDF),(0x3000,0x303F),(0x3040,0x30FF),(0x3400,0x4DBF),(0x4E00,0x9FFF),(0xAC00,0xD7AF),(0xFF00,0xFFEF)]; c=TTFont(r'web/src/assets/fonts/InterLatin.woff2').getBestCmap(); print('cjk-hits', sum(1 for u in c if any(a <= u <= b for a, b in R)))"
python -c "from fontTools.ttLib import TTFont; R=[(0x2E80,0x2FDF),(0x3000,0x303F),(0x3040,0x30FF),(0x3400,0x4DBF),(0x4E00,0x9FFF),(0xAC00,0xD7AF),(0xFF00,0xFFEF)]; c=TTFont(r'web/src/assets/fonts/IBMPlexMonoLatin.woff2').getBestCmap(); print('cjk-hits', sum(1 for u in c if any(a <= u <= b for a, b in R)))"
```

实测输出：

```text
cjk-hits 0
cjk-hits 0
```

## 自动化覆盖到哪里为止

`web/tests/e2e/main.spec.ts` 的 `-g Task 2` 三条用例覆盖的是 **CSSOM 声明层**：

- `@font-face` 规则文本含 `.woff2`、不含 `https?://`、含 `font-display: swap`，且两族恰好是
  `Inter` 与 `IBM Plex Mono`；
- `getComputedStyle()` 解析出的正文/控件字体栈首选 `Inter`，等宽令牌解析出 `IBM Plex Mono`；
- `unicode-range` 的区间语义：覆盖 Basic Latin、不覆盖 CJK。

**它们不覆盖真实加载。** `web/tests/e2e/main.spec.ts` 里 `document.fonts` 零命中，也没有任何网络
请求断言，因此「两套 WOFF2 在运行时确实被请求、响应来自本地 `/assets/…`、全程无远程字体请求」这件事
目前**没有自动化证据**——离线可用性只由「构建产物里带这两份文件 + 静态规则 `remote-font-url` 禁止
远程 `url()` + 上述 CSSOM 断言」间接支撑，字体文件被删、404 或被 CDN 顶替都不会让三条用例转红。
该缺口已登记为计划 Task 12 的证据项（见该任务节末「收口责任」）。

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
