// UI 静态契约检查器的契约测试（PLAN-DM-029 Task 1）。
//
// 本文件是所有规则的可执行契约：夹具全部写在系统临时目录里，通过
// `collectUiContractViolations({root, exceptions})` 与真实 CLI 子进程验证。
//
// 变异证据套件（Step 8）向合法夹具逐类注入违规并断言真实 CLI 子进程退出 1；它只在
// 检查器、规则或例外格式变化时要求重跑。整套用例实测 5.7～9.7 秒（三次运行 5.7 s /
// 9.0 s / 9.7 s，随机器负载波动），其中 14 次 CLI 子进程启动各占 0.52～0.62 秒，
// 因此新增 CLI 级变异用例时按「每次 spawn 约 0.6 秒」估算预算。

import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdirSync, mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, describe, test} from "node:test";

import {collectUiContractViolations, formatViolation, runCli} from "./check-ui-contracts.mjs";
import {NON_EXEMPTIBLE_RULES} from "./ui-contracts/types.mjs";

const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
const CLI_PATH = join(SCRIPTS_DIR, "check-ui-contracts.mjs");

const TOKENS_CSS = `:root{
  --color-text-primary:#1A2233;
  --color-border-subtle:#E3E8EF;
  --color-border-strong:#C7D0DB;
  --font-label:13px;
  --space-2:8px;
}
html[data-theme="dark"]{--color-text-primary:#E6EAF2}
`;

/** 合法的样式入口夹具：层顺序声明 + 四个分层导入（注释与空行都不影响判定）。 */
const ENTRY_CSS = `/* 分层入口：层顺序固定，正文只在 @import 的分层样式表里 */
@layer tokens, reset, primitives, legacy;

@import "./styles/tokens.css";
@import "./styles/reset.css";
@import "./styles/primitives.css";
@import "./styles/legacy.css";
`;

/** 生成一条 `@font-face` 声明，用于字体资产夹具。 */
function fontFace(family, url) {
  return `@font-face{font-family:"${family}";src:url("${url}") format("woff2")}`;
}

const roots = [];

/** 在临时目录里创建一套工作区夹具；返回工作区根目录。 */
function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), "ui-contracts-"));
  roots.push(root);
  for (const [relative, content] of Object.entries(files)) {
    const path = join(root, relative);
    mkdirSync(dirname(path), {recursive: true});
    writeFileSync(path, content, "utf8");
  }
  return root;
}

/** 只跑检查器，不施加例外棘轮。 */
function rawViolations(files) {
  return collectUiContractViolations({root: fixture(files), exceptions: emptyExceptions()});
}

function emptyExceptions() {
  return {exceptions: [], dynamicVariables: []};
}

function rulesOf(violations) {
  return violations.map((violation) => violation.rule);
}

function only(violations, rule) {
  const found = violations.filter((violation) => violation.rule === rule);
  assert.equal(found.length, 1, `期望恰好 1 条 ${rule}，实际：${JSON.stringify(violations, null, 2)}`);
  return found[0];
}

after(() => {
  for (const root of roots) rmSync(root, {recursive: true, force: true});
});

describe("CSS 变量解析", () => {
  test("未定义变量被拒绝", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Bad.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--color-missing)}</style>
`,
    });
    const violation = only(violations, "undefined-css-variable");
    assert.match(violation.file, /src\/components\/Bad\.vue$/);
    assert.match(violation.message, /--color-missing/);
    assert.equal(typeof violation.line, "number");
    assert.equal(typeof violation.column, "number");
  });

  test("嵌套 fallback 中未定义的变量仍被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Nested.vue": `<template><p>文本</p></template>
<style scoped>.a{border:1px solid var(--color-border-subtle,var(--color-bg-surface-2))}</style>
`,
      }),
      "undefined-css-variable",
    );
    assert.match(violation.message, /--color-bg-surface-2/);
  });

  test("外层已定义但 fallback 未定义时按未定义引用拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Outer.vue": `<template><p>文本</p></template>
<style scoped>.a{border-color:var(--color-border-strong,var(--color-nope))}</style>
`,
      }),
      "undefined-css-variable",
    );
    assert.match(violation.message, /--color-nope/);
  });

  test("已声明变量（含合法 fallback）不报", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Good.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--color-text-primary);padding:var(--space-2,var(--font-label))}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("组件局部声明可解析自身引用", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Local.vue": `<template><p>文本</p></template>
<style scoped>.a{--local-gap:var(--space-2);gap:var(--local-gap)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("循环引用被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": `${TOKENS_CSS}:root{--loop-a:var(--loop-b);--loop-b:var(--loop-a)}`,
        "src/components/Cycle.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--loop-a)}</style>
`,
      }),
      "circular-css-variable",
    );
    assert.match(violation.message, /--loop-[ab]/);
  });

  test("var() 使用平衡括号解析，嵌套括号不误判", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Balanced.vue": `<template><p>文本</p></template>
<style scoped>.a{width:min(390px,calc(100vw - var(--space-2)));color:var(--color-text-primary)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });
});

describe("动态变量白名单", () => {
  const sheets = `<template><div :style="{'--tree-width': '320px'}"><p>文本</p></div></template>
<style scoped>.pane{flex:0 0 var(--tree-width)}</style>
`;

  test("缺生产者的动态变量条目被拒绝", () => {
    const violations = collectUiContractViolations({
      root: fixture({"src/styles/tokens.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
      exceptions: {
        exceptions: [],
        dynamicVariables: [{variable: "--tree-width", consumer: "src/views/Sheets.vue", reason: "运行时写入", expiresWith: "Task 7"}],
      },
    });
    const violation = only(violations, "dynamic-variable-not-registered");
    assert.match(violation.message, /producer/);
  });

  test("字段完整的动态变量条目通过", () => {
    const violations = collectUiContractViolations({
      root: fixture({"src/styles/tokens.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
      exceptions: {
        exceptions: [],
        dynamicVariables: [
          {
            variable: "--tree-width",
            producer: "src/views/Sheets.vue",
            consumer: "src/views/Sheets.vue",
            reason: "图纸树宽度由运行时状态写入内联样式",
            expiresWith: "Task 7 复核可否改为静态令牌",
          },
        ],
      },
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("生产者文件不存在的幽灵条目被拒绝", () => {
    const violations = collectUiContractViolations({
      root: fixture({"src/styles/tokens.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
      exceptions: {
        exceptions: [],
        dynamicVariables: [
          {
            variable: "--tree-width",
            producer: "src/does-not-exist.vue",
            consumer: "src/views/Sheets.vue",
            reason: "声称由不存在的文件写入",
            expiresWith: "Task 7",
          },
        ],
      },
    });
    const violation = only(violations, "dynamic-variable-not-registered");
    assert.match(violation.message, /生产者文件不存在/);
    assert.match(violation.message, /--tree-width/);
  });

  test("未登记的动态变量按未定义引用拒绝", () => {
    const violation = only(
      collectUiContractViolations({
        root: fixture({"src/styles/tokens.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
        exceptions: emptyExceptions(),
      }),
      "undefined-css-variable",
    );
    assert.match(violation.message, /--tree-width/);
  });
});

describe("Vue 语义规则", () => {
  test("按钮缺 type 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Buttons.vue": `<template><button @click="save">保存</button></template>
`,
      }),
      "explicit-button-type",
    );
    assert.match(violation.message, /type/);
    assert.equal(violation.line, 1);
  });

  test("显式 type 的按钮通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Buttons.vue": `<template><button type="button" @click="save">保存</button><button type="submit">提交</button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("搜索输入缺可见 label 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template><div class="search"><input v-model="query" :placeholder="hint" /></div></template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /label/);
  });

  test("label 包裹或 label[for] 关联的输入通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Search.vue": `<template>
  <label class="weak"><span>搜索</span><input v-model="query" /></label>
  <label for="name">名称</label><input id="name" v-model="name" />
  <input type="hidden" v-model="hidden" />
</template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("图标按钮缺可读名称被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/IconButton.vue": `<template><button type="button" class="icon" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button></template>
`,
      }),
      "icon-button-name",
    );
    assert.match(violation.message, /可读名称/);
  });

  test("有 aria-label 的图标按钮通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/IconButton.vue": `<template><button type="button" class="icon" :aria-label="label" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("Unicode 结构图标被拒绝", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Unicode.vue": `<template><span aria-hidden="true">▸</span><span aria-hidden="true">◐</span></template>
`,
    });
    assert.equal(violations.filter((v) => v.rule === "unicode-structure-icon").length, 2);
  });

  test("中文文案与普通标点不被当作结构图标", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Text.vue": `<template><p>保存（另存为）— 已复制，共 3 项；引用“目录”模板。</p></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("属性值里的 > 不截断标签：type 与可见文字仍被正确读取", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Operators.vue": `<template><button :disabled="count>=1" type="button">保存</button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("属性值里的 > 之后仍能定位缺 type 的按钮", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Operators.vue": `<template><button :disabled="count>=1" @click="go">前往</button></template>
`,
      }),
      "explicit-button-type",
    );
    assert.equal(violation.fingerprint, "explicit-button-type|src/components/Operators.vue|前往|1");
  });

  test("图标在文字之前的按钮不误判为缺少可读名称", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/WithIcon.vue": `<template><button type="button" @click="save"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg>保存</button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("含 HTML 注释的模板里图标位置不漂移到前面的行", () => {
    const source = `<template>
  <!-- 一行注释
       第二行注释
       第三行注释 -->
  <button type="button">✕</button>
</template>
`;
    const violation = only(
      rawViolations({"src/styles/tokens.css": TOKENS_CSS, "src/components/Comment.vue": source}),
      "unicode-structure-icon",
    );
    // 手算：第 5 行 `  <button type="button">` 共 24 字符，`✕` 在第 25 列。
    assert.deepEqual({line: violation.line, column: violation.column}, {line: 5, column: 25});
    const text = source.split("\n")[violation.line - 1];
    assert.ok(text.slice(violation.column - 1).startsWith("✕"), text);
  });
});

describe("视觉值规则", () => {
  test("违规位置精确指向值的起点", () => {
    const source = `<template>
<p>文本</p>
</template>
<style scoped>
.a{font-size:15px}
.b{color:#123456}
</style>
`;
    const violations = rawViolations({"src/styles/tokens.css": TOKENS_CSS, "src/components/Positions.vue": source});
    const lines = source.split("\n");
    // 手算：第 5 行 `.a{font-size:` 共 13 字符，`15px` 起于第 14 列；
    // 第 6 行 `.b{color:` 共 9 字符，`#123456` 起于第 10 列。
    const visual = only(violations, "raw-visual-value");
    assert.deepEqual({line: visual.line, column: visual.column}, {line: 5, column: 14});
    assert.ok(lines[visual.line - 1].slice(visual.column - 1).startsWith("15px"));
    const hex = only(violations, "raw-hex-color");
    assert.deepEqual({line: hex.line, column: hex.column}, {line: 6, column: 10});
    assert.ok(lines[hex.line - 1].slice(hex.column - 1).startsWith("#123456"));
  });

  test("未登记的十六进制色被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Color.vue": `<template><p>文本</p></template>
<style scoped>.a{color:#17203333}</style>
`,
      }),
      "raw-hex-color",
    );
    assert.match(violation.message, /#17203333/);
  });

  test("令牌定义块内的十六进制色与 rgba 常量通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": `${TOKENS_CSS}.mask{background:rgba(16,24,40,.55)}`,
      "src/components/Color.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--color-text-primary);background:rgba(16,24,40,.55)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("裸字号、高度与圆角被拒绝，令牌与合法常量通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Size.vue": `<template><p>文本</p></template>
<style scoped>.a{font-size:15px;min-height:36px;border-radius:7px}.b{font-size:var(--font-label);border:1px solid var(--color-border-subtle);height:100%;min-height:0;line-height:1.5;border-radius:50%}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), ["raw-visual-value", "raw-visual-value", "raw-visual-value"]);
    assert.deepEqual(
      violations.map((violation) => violation.message.replace(/^.*?：/, "")),
      ["font-size:15px", "min-height:36px", "border-radius:7px"],
    );
  });

  test("裸全局选择器被拒绝，根类限定选择器通过", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Scope.vue": `<template><p>文本</p></template>
<style>
button{background:none}
.panel button{padding:4px}
</style>
`,
      }),
      "global-selector-in-component",
    );
    assert.match(violation.message, /button/);
  });

  test("选择器列表逐段判定：逗号后段的裸选择器也会被拒绝", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Scope.vue": `<template><p>文本</p></template>
<style>
.panel,.panel div,button{background:none}
.panel .inner,.panel .title{padding:4px}
</style>
`,
    });
    const found = violations.filter((violation) => violation.rule === "global-selector-in-component");
    assert.equal(found.length, 1);
    assert.match(found[0].message, /\.panel,.panel div,button/);
  });

  test("全局业务样式表的裸选择器被拒绝，令牌块通过", () => {
    const violations = rawViolations({
      "src/styles/legacy.css": `${TOKENS_CSS}
main{padding:24px}
.topbar div{margin:auto}
`,
    });
    const found = violations.filter((violation) => violation.rule === "global-selector-in-component");
    assert.equal(found.length, 1);
    assert.match(found[0].message, /main/);
  });

  test("令牌块豁免只认整条规则恰为 :root/html[...]", () => {
    for (const selector of ["html body .panel", 'html[data-theme="dark"] .panel', ":root,.panel"]) {
      const violations = rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Token.vue": `<template><p>文本</p></template>
<style scoped>${selector}{font-size:15px}</style>
`,
      });
      const found = violations.filter((violation) => violation.rule === "raw-visual-value");
      assert.equal(found.length, 1, `期望 ${selector} 仍被判定为裸视觉值：${JSON.stringify(violations)}`);
    }
  });

  test(":root 与 html[...] 令牌块仍被豁免（含多段全为令牌块）", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": `:root{--font-label:13px;font-size:13px}html[data-theme="dark"]{--font-label:14px;font-size:14px}:root,html[data-theme="light"]{--font-label:15px;font-size:15px}`,
      "src/components/Token.vue": `<template><p>文本</p></template>
<style scoped>.panel{font-size:var(--font-label)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("图标尺寸（宽度家族）与高度家族同等判定", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Icon.vue": `<template><p>文本</p></template>
<style scoped>.icon{width:18px;min-width:20px;max-width:22px;height:18px;min-height:20px;max-height:22px;border-radius:6px}</style>
`,
    });
    assert.deepEqual(
      violations.map((violation) => violation.message.replace(/^.*?：/, "")),
      ["width:18px", "min-width:20px", "max-width:22px", "height:18px", "min-height:20px", "max-height:22px", "border-radius:6px"],
    );
  });

  test("@media/@container 的 max-width 前奏不被当成声明", () => {
    // 刻意放在全局业务样式表并写裸值：
    // - 裸值确保内层真的被扫到（扫不到就是检查器漏扫，本测试必须变红）；
    // - 非 scoped 上下文确保前奏一旦被当成规则，就会以 `裸全局选择器` 形式把
    //   `@media (max-width:900px)` 写进消息，从而被下面的前奏断言钉住。
    const violations = rawViolations({
      "src/styles/tokens.css": `${TOKENS_CSS}
@media (max-width:900px){.panel{font-size:15px}}
@container value-body (max-width:511px){.panel{line-height:15px}}
@media (min-width:600px) and (max-width:900px){.panel{height:15px}}
`,
    });
    // 正向控制：三条内层裸值都必须命中。
    assert.deepEqual(
      violations.filter((violation) => violation.rule === "raw-visual-value").map((violation) => violation.message.replace(/^.*?：/, "")),
      ["font-size:15px", "line-height:15px", "height:15px"],
    );
    // 前奏里的断点不是声明：任何违规都不得把 900px/511px/600px 当成属性值或选择器。
    const preludeMentions = violations
      .filter((violation) => /900px|511px|600px/.test(violation.message))
      .map((violation) => `${violation.rule}: ${violation.message}`);
    assert.deepEqual(preludeMentions, []);
    // 钉住「不多不少」：该夹具的违规集合必须恰好是这 3 条裸视觉值，
    // 冒出规则外的额外违规（如 `undefined-css-variable`）同样必须判错。
    assert.deepEqual(rulesOf(violations), ["raw-visual-value", "raw-visual-value", "raw-visual-value"]);
  });

  test("@keyframes 的 from/to/百分比关键帧不作为规则参与判定", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Toast.vue": `<template><p>文本</p></template>
<style>
@keyframes toast-in{from{height:0;opacity:0}0%{opacity:.2}100%{height:10px;opacity:1}to{height:10px}}
</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });
});

describe("字体资产与样式入口门禁（Task 2 Step 7）", () => {
  const FONT_DIR = "src/assets/fonts";
  const asset = (bytes) => "x".repeat(bytes);

  test("字体引用的本地文件不存在被拒绝", () => {
    const violation = only(
      rawViolations({"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Missing.woff2")}`}),
      "missing-font-asset",
    );
    assert.equal(violation.file, "src/styles/tokens.css");
    assert.match(violation.message, /字体文件不存在：\.\.\/assets\/fonts\/Missing\.woff2/);
  });

  test("字体引用的本地文件存在时通过", () => {
    const violations = rawViolations({
      [`${FONT_DIR}/InterLatin.woff2`]: asset(1024),
      "src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/InterLatin.woff2")}`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("字体引用远程 URL 被拒绝：带 scheme 与协议相对都算", () => {
    for (const url of ["https://cdn.example.com/Inter.woff2", "//cdn.example.com/Inter.woff2"]) {
      const violation = only(
        rawViolations({"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", url)}`}),
        "remote-font-url",
      );
      assert.match(violation.message, /字体不得引用远程 URL/);
      assert.ok(violation.message.includes(url), violation.message);
    }
  });

  test("本地相对路径与工作区根路径都不算远程", () => {
    // `../` 相对样式表所在目录解析，`/` 相对工作区根解析；两者都是本地资产。
    const violations = rawViolations({
      [`${FONT_DIR}/InterLatin.woff2`]: asset(1024),
      "assets/fonts/IBMPlexMonoLatin.woff2": asset(2048),
      "src/styles/tokens.css":
        TOKENS_CSS +
        fontFace("Inter", "../assets/fonts/InterLatin.woff2") +
        fontFace("IBM Plex Mono", "/assets/fonts/IBMPlexMonoLatin.woff2"),
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("本地字体资产合计超预算被拒绝", () => {
    const violation = only(
      rawViolations({
        [`${FONT_DIR}/Big.woff2`]: asset(256001),
        "src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Big.woff2")}`,
      }),
      "font-budget-exceeded",
    );
    assert.match(violation.message, /合计 256001 字节，超过预算 256000 字节/);
    // 报在第一条被引用的资产上：超预算是整批资产的事实，不是某一条 @font-face 的错。
    assert.equal(violation.file, "src/styles/tokens.css");
  });

  test("多套资产合计恰好等于预算时通过（边界）", () => {
    const violations = rawViolations({
      [`${FONT_DIR}/A.woff2`]: asset(200000),
      [`${FONT_DIR}/B.woff2`]: asset(56000),
      "src/styles/tokens.css":
        TOKENS_CSS +
        fontFace("Inter", "../assets/fonts/A.woff2") +
        fontFace("IBM Plex Mono", "../assets/fonts/B.woff2"),
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("合法样式入口（层顺序 + 四个导入 + 注释空行）通过", () => {
    assert.deepEqual(rulesOf(rawViolations({"src/style.css": ENTRY_CSS})), []);
  });

  test("样式入口承载样式规则被拒绝", () => {
    const violation = only(
      rawViolations({"src/style.css": `${ENTRY_CSS}\n.panel{color:red}\n`}),
      "entry-stylesheet-not-import-only",
    );
    assert.match(violation.message, /样式入口不得承载样式规则：\.panel/);
  });

  test("样式入口缺少层顺序声明被拒绝", () => {
    const violation = only(
      rawViolations({"src/style.css": ENTRY_CSS.replace("@layer tokens, reset, primitives, legacy;\n", "")}),
      "entry-stylesheet-not-import-only",
    );
    assert.match(violation.message, /缺少层顺序声明/);
  });

  test("样式入口层顺序不符被拒绝", () => {
    const violation = only(
      rawViolations({"src/style.css": ENTRY_CSS.replace("tokens, reset, primitives, legacy", "tokens, primitives, legacy")}),
      "entry-stylesheet-not-import-only",
    );
    assert.match(violation.message, /层顺序必须为/);
  });

  test("样式入口漏导入分层样式表被拒绝", () => {
    const violation = only(
      rawViolations({"src/style.css": ENTRY_CSS.replace('@import "./styles/legacy.css";\n', "")}),
      "entry-stylesheet-not-import-only",
    );
    assert.match(violation.message, /必须导入四个分层样式表/);
  });

  test("硬门禁规则清单固定为四条", () => {
    assert.deepEqual([...NON_EXEMPTIBLE_RULES].sort(), [
      "entry-stylesheet-not-import-only",
      "font-budget-exceeded",
      "missing-font-asset",
      "remote-font-url",
    ]);
  });

  test("四条资产事实规则一律不允许登记例外", () => {
    for (const rule of NON_EXEMPTIBLE_RULES) {
      const violations = collectUiContractViolations({
        root: fixture({"src/styles/tokens.css": TOKENS_CSS}),
        exceptions: {
          exceptions: [
            {
              rule,
              file: "src/styles/tokens.css",
              fingerprint: `${rule}|src/styles/tokens.css|尝试登记|1`,
              reason: "尝试把硬门禁加白",
              expiresWith: "PLAN-DM-029 Task 9",
            },
          ],
          dynamicVariables: [],
        },
      });
      const violation = only(violations, "invalid-exception-entry");
      assert.match(violation.message, /硬门禁规则不允许登记例外/);
      assert.ok(violation.message.includes(rule), violation.message);
    }
  });

  test("硬门禁规则的真实违规不因例外条目而放行", () => {
    const files = {"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Missing.woff2")}`};
    const missing = only(rawViolations(files), "missing-font-asset");
    const violations = collectUiContractViolations({
      root: fixture(files),
      exceptions: {
        exceptions: [
          {
            rule: missing.rule,
            file: missing.file,
            fingerprint: missing.fingerprint,
            reason: "尝试把硬门禁加白",
            expiresWith: "PLAN-DM-029 Task 9",
          },
        ],
        dynamicVariables: [],
      },
    });
    only(violations, "invalid-exception-entry");
    // 关键：登记条目被拒绝后，真实违规仍然存在，白名单没有把它吃掉。
    assert.equal(only(violations, "missing-font-asset").fingerprint, missing.fingerprint);
  });
});

describe("棘轮：例外登记与陈旧例外", () => {
  const files = {
    "src/styles/tokens.css": TOKENS_CSS,
    "src/components/Legacy.vue": `<template><button @click="go">前往</button></template>
<style scoped>.a{font-size:15px}</style>
`,
  };

  test("未登记违规被报告", () => {
    const violations = rawViolations(files);
    assert.deepEqual(rulesOf(violations).sort(), ["explicit-button-type", "raw-visual-value"]);
  });

  test("逐条登记的例外使检查通过", () => {
    const raw = rawViolations(files);
    const exceptions = {
      exceptions: raw.map((violation) => ({
        rule: violation.rule,
        file: violation.file,
        fingerprint: violation.fingerprint,
        reason: "迁移前既有债务",
        expiresWith: "PLAN-DM-029 Task 9",
      })),
      dynamicVariables: [],
    };
    const violations = collectUiContractViolations({root: fixture(files), exceptions});
    assert.deepEqual(rulesOf(violations), []);
  });

  test("已不再命中的例外被拒绝", () => {
    const violations = collectUiContractViolations({
      root: fixture({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Legacy.vue": `<template><button type="button">前往</button></template>
`,
      }),
      exceptions: {
        exceptions: [
          {
            rule: "explicit-button-type",
            file: "src/components/Legacy.vue",
            fingerprint: "explicit-button-type|src/components/Legacy.vue|前往|1",
            reason: "迁移前既有债务",
            expiresWith: "PLAN-DM-029 Task 9",
          },
        ],
        dynamicVariables: [],
      },
    });
    const violation = only(violations, "stale-exception");
    assert.match(violation.message, /explicit-button-type/);
  });

  test("重复指纹的例外条目被拒绝", () => {
    const raw = rawViolations(files);
    const entry = {
      rule: raw[0].rule,
      file: raw[0].file,
      fingerprint: raw[0].fingerprint,
      reason: "迁移前既有债务",
      expiresWith: "PLAN-DM-029 Task 9",
    };
    const violations = collectUiContractViolations({
      root: fixture(files),
      exceptions: {exceptions: [entry, {...entry}], dynamicVariables: []},
    });
    const violation = only(violations, "invalid-exception-entry");
    assert.match(violation.message, /重复登记/);
  });

  test("缺少 reason 或 expiresWith 的例外条目被拒绝", () => {
    const violations = collectUiContractViolations({
      root: fixture(files),
      exceptions: {
        exceptions: [{rule: "explicit-button-type", file: "src/components/Legacy.vue", fingerprint: "x"}],
        dynamicVariables: [],
      },
    });
    const violation = only(violations, "invalid-exception-entry");
    assert.match(violation.message, /reason/);
  });

  test("指纹含规则、文件与稳定语义，不含行号", () => {
    const compact = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Finger.vue": `<template><button @click="go">前往</button></template>
`,
    });
    const shifted = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Finger.vue": `

<template>
  <button @click="go">前往</button>
</template>
`,
    });
    assert.equal(compact[0].fingerprint, shifted[0].fingerprint);
    assert.ok(compact[0].fingerprint.includes("explicit-button-type"));
    assert.ok(compact[0].fingerprint.includes("src/components/Finger.vue"));
    assert.ok(compact[0].fingerprint.includes("前往"));
    assert.notEqual(compact[0].line, shifted[0].line);
  });

  test("同一文件内同语义的重复违规各有独立指纹", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Repeat.vue": `<template><button @click="go">前往</button><button @click="go">前往</button></template>
`,
    });
    assert.equal(violations.length, 2);
    assert.notEqual(violations[0].fingerprint, violations[1].fingerprint);
  });
});

describe("CLI 契约", () => {
  test("无违规时退出 0 且不输出", () => {
    const root = fixture({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Clean.vue": `<template><button type="button">保存</button></template>
`,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
    });
    const result = runCli([`--root=${root}`]);
    assert.equal(result.exitCode, 0, result.stderr + result.stdout);
    assert.equal(result.stdout.trim(), "");
  });

  test("有违规时按 file:line:column [rule] message 输出并退出 1", () => {
    const root = fixture({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Dirty.vue": `<template><button @click="go">前往</button></template>
`,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
    });
    const result = runCli([`--root=${root}`]);
    assert.equal(result.exitCode, 1);
    const line = result.stdout.trim().split("\n")[0];
    assert.match(line, /^src\/components\/Dirty\.vue:1:\d+ \[explicit-button-type\] /);
  });

  test("例外文件缺失时明确失败而不是静默通过", () => {
    const root = fixture({"src/styles/tokens.css": TOKENS_CSS});
    const result = runCli([`--root=${root}`]);
    assert.equal(result.exitCode, 2);
    assert.match(result.stderr, /ui-contract-exceptions\.json/);
  });

  test("源码根目录不可读时明确失败而不是静默通过", () => {
    const root = fixture({
      "src/styles/tokens.css": TOKENS_CSS,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
    });
    // 把 src 换成同名文件，模拟扫描根目录读不进来（ENOTDIR）。
    rmSync(join(root, "src"), {recursive: true, force: true});
    writeFileSync(join(root, "src"), "不是目录", "utf8");
    const result = runCli([`--root=${root}`]);
    assert.equal(result.exitCode, 2, result.stdout + result.stderr);
    assert.match(result.stderr, /无法读取目录/);
  });

  test("formatViolation 输出可点击定位", () => {
    assert.equal(
      formatViolation({rule: "raw-hex-color", file: "src/a.vue", line: 3, column: 9, message: "未登记的十六进制颜色：#123456"}),
      "src/a.vue:3:9 [raw-hex-color] 未登记的十六进制颜色：#123456",
    );
  });
});

describe("变异证据：每类违规都使 CLI 退出 1", () => {
  const clean = {
    "src/styles/tokens.css": TOKENS_CSS,
    "src/components/Clean.vue": `<template>
  <label for="name">名称</label><input id="name" v-model="name" />
  <button type="button" :aria-label="label" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button>
</template>
<style scoped>.panel{font-size:var(--font-label);color:var(--color-text-primary);border:1px solid var(--color-border-subtle)}</style>
`,
  };

  const mutations = [
    {
      step1Class: "未定义变量",
      name: "未定义变量",
      rule: "undefined-css-variable",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--font-label)", "var(--font-nope)")},
    },
    {
      step1Class: "嵌套 fallback 未定义",
      name: "嵌套 fallback 中未定义的变量",
      rule: "undefined-css-variable",
      files: {
        "src/components/Clean.vue": clean["src/components/Clean.vue"].replace(
          "var(--font-label)",
          "var(--color-text-primary,var(--font-nope))",
        ),
      },
    },
    {
      step1Class: "循环引用",
      name: "循环引用",
      rule: "circular-css-variable",
      files: {"src/styles/tokens.css": `${TOKENS_CSS}:root{--loop-a:var(--loop-b);--loop-b:var(--loop-a)}`},
    },
    {
      step1Class: "动态变量缺生产者",
      name: "动态变量缺少生产者",
      rule: "dynamic-variable-not-registered",
      files: {
        "src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--font-label)", "var(--tree-width)"),
        "scripts/ui-contract-exceptions.json": JSON.stringify({
          exceptions: [],
          dynamicVariables: [{variable: "--tree-width", consumer: "src/components/Clean.vue", reason: "运行时写入", expiresWith: "PLAN-DM-029 Task 7"}],
        }),
      },
    },
    {
      step1Class: "按钮无 type",
      name: "按钮缺 type",
      rule: "explicit-button-type",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace('type="button" ', "")},
    },
    {
      step1Class: "搜索输入无可见 label",
      name: "输入缺可见 label",
      rule: "visible-input-label",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace('<label for="name">名称</label>', "")},
    },
    {
      step1Class: "图标按钮无可读名称",
      name: "图标按钮缺可读名称",
      rule: "icon-button-name",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace(':aria-label="label" ', "")},
    },
    {
      step1Class: "Unicode 结构图标",
      name: "Unicode 结构图标",
      rule: "unicode-structure-icon",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace(">名称<", ">▸<")},
    },
    {
      step1Class: "裸全局选择器",
      name: "组件内裸全局选择器",
      rule: "global-selector-in-component",
      files: {
        "src/components/Clean.vue": clean["src/components/Clean.vue"].replace("<style scoped>", "<style>").replace("</style>", "button{background:none}</style>"),
      },
    },
    {
      step1Class: "未登记十六进制色",
      name: "裸十六进制色",
      rule: "raw-hex-color",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--color-text-primary)", "#17203333")},
    },
    {
      step1Class: "裸视觉值",
      name: "裸字号",
      rule: "raw-visual-value",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--font-label)", "15px")},
    },
    {
      step1Class: "裸视觉值",
      name: "图标尺寸（宽度家族）裸值",
      rule: "raw-visual-value",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("</style>", ".icon{width:18px;height:18px}</style>")},
    },
    {
      step1Class: "字体资产缺失",
      name: "字体引用的本地文件不存在",
      rule: "missing-font-asset",
      files: {"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Missing.woff2")}`},
    },
    {
      step1Class: "远程字体 URL",
      name: "字体引用远程 URL",
      rule: "remote-font-url",
      files: {"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "https://cdn.example.com/Inter.woff2")}`},
    },
    {
      step1Class: "字体体积超预算",
      name: "本地字体资产合计超预算",
      rule: "font-budget-exceeded",
      files: {
        "src/assets/fonts/Big.woff2": "x".repeat(256001),
        "src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Big.woff2")}`,
      },
    },
    {
      // 在入口追加规则块：类选择器不属于裸全局选择器，因此这条注入只命中入口结构规则。
      step1Class: "样式入口承载规则",
      name: "样式入口承载样式规则",
      rule: "entry-stylesheet-not-import-only",
      files: {"src/style.css": `${ENTRY_CSS}\n.panel{color:red}\n`},
    },
  ];

  /** Task 1 Step 1 的十一类判定。 */
  const STEP1_CLASSES = [
    "未定义变量",
    "嵌套 fallback 未定义",
    "循环引用",
    "动态变量缺生产者",
    "按钮无 type",
    "搜索输入无可见 label",
    "图标按钮无可读名称",
    "Unicode 结构图标",
    "裸全局选择器",
    "未登记十六进制色",
    "裸视觉值",
  ];
  /** Task 2 Step 7 新增的四类资产事实与入口结构判定。 */
  const TASK2_CLASSES = ["字体资产缺失", "远程字体 URL", "字体体积超预算", "样式入口承载规则"];

  function runFixture(files) {
    const root = fixture({
      ...clean,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
      ...files,
    });
    return spawnSync(process.execPath, [CLI_PATH, `--root=${root}`], {encoding: "utf8"});
  }

  test("每类判定都有 CLI 级变异证据（Step 1 十一类 + Task 2 四条）", () => {
    // 裸视觉值一类在 brief 里是一个分类，这里拆成字号与图标尺寸两条注入。
    const classes = new Set(mutations.map((mutation) => mutation.step1Class));
    for (const name of [...STEP1_CLASSES, ...TASK2_CLASSES]) {
      assert.ok(classes.has(name), `缺少「${name}」的 CLI 级变异证据`);
    }
    // 分类集合必须恰好是这两组，不允许默默少测或凭空多出未归类的注入。
    assert.deepEqual([...classes].filter((name) => !STEP1_CLASSES.includes(name)).sort(), [...TASK2_CLASSES].sort());
    assert.equal(classes.size, 15, [...classes].join("、"));
    assert.equal(mutations.length, 16);
    assert.equal(new Set(mutations.map((mutation) => mutation.name)).size, 16);
    assert.deepEqual([...new Set(mutations.map((mutation) => mutation.rule))].sort(), [
      "circular-css-variable",
      "dynamic-variable-not-registered",
      "entry-stylesheet-not-import-only",
      "explicit-button-type",
      "font-budget-exceeded",
      "global-selector-in-component",
      "icon-button-name",
      "missing-font-asset",
      "raw-hex-color",
      "raw-visual-value",
      "remote-font-url",
      "undefined-css-variable",
      "unicode-structure-icon",
      "visible-input-label",
    ]);
  });

  test("合法夹具退出 0", () => {
    const result = runFixture({});
    assert.equal(result.status, 0, result.stdout + result.stderr);
  });

  for (const mutation of mutations) {
    test(`注入${mutation.name}后退出 1`, () => {
      const result = runFixture(mutation.files);
      assert.equal(result.status, 1, `期望${mutation.name}使 CLI 失败，实际输出：${result.stdout}${result.stderr}`);
      assert.match(result.stdout, new RegExp(`\\[${mutation.rule}\\]`));
    });
  }

  test("恢复夹具后重新退出 0", () => {
    const result = runFixture({});
    assert.equal(result.status, 0, result.stdout + result.stderr);
  });
});
