// UI 静态契约检查器的契约测试（PLAN-DM-029 Task 1）。
//
// 本文件是所有规则的可执行契约：夹具全部写在系统临时目录里，通过
// `collectUiContractViolations({root, exceptions})` 与真实 CLI 子进程验证。
//
// 变异证据套件（Step 8）向合法夹具逐类注入违规并断言真实 CLI 子进程退出 1；它只在
// 检查器、规则或例外格式变化时要求重跑。整套用例实测 5.7～13.6 秒（四次运行 5.7 s /
// 9.0 s / 9.7 s / 13.6 s，随机器负载波动），其中 14 次 CLI 子进程启动各占 0.52～0.62 秒，
// 因此新增 CLI 级变异用例时按「每次 spawn 约 0.6 秒」估算预算。

import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdirSync, mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, describe, test} from "node:test";

import {collectUiContractViolations, DEFAULT_EXCEPTIONS_FILE, formatViolation, runCli} from "./check-ui-contracts.mjs";
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

/**
 * 在临时目录里创建一套工作区夹具；返回工作区根目录。
 *
 * 默认补上一个合法的 `src/style.css` 入口：Task 2 起「入口文件必须存在且只做导入」本身
 * 就是硬门禁，缺入口的夹具就是一个违规工作区（详见「样式入口缺失」用例）。需要验证入口
 * 内容的用例自己传入 `src/style.css` 覆盖默认值；需要验证「入口缺失」的用例在夹具建好后
 * 删掉它。
 */
function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), "ui-contracts-"));
  roots.push(root);
  const withEntry = "src/style.css" in files ? files : {"src/style.css": ENTRY_CSS, ...files};
  for (const [relative, content] of Object.entries(withEntry)) {
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

  test("组件化输入：自带非空 label 的 UiInput 通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Search.vue": `<template>
  <UiInput type="search" :label="$t('search.label')" :model-value="query" @update:model-value="setQuery" />
  <UiSelect :label="静态也行" :model-value="mode"><option value="all">全部</option></UiSelect>
</template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("组件化输入：无 label 的 UiInput / UiSelect 被拒绝（aria-label 不解除）", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Search.vue": `<template>
  <UiInput :model-value="query" aria-label="搜索" @update:model-value="setQuery" />
  <UiSelect :model-value="mode"><option value="all">全部</option></UiSelect>
</template>
`,
    });
    assert.deepEqual(rulesOf(violations), ["visible-input-label", "visible-input-label"]);
  });

  test("组件化输入：空字符串 label 不算可见标签", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template><UiInput label="" :model-value="query" /></template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /组件化输入/);
  });

  test("组件化输入：FormField 默认插槽提供 label 时通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Search.vue": `<template>
  <FormField label="名称"><UiInput :model-value="name" @update:model-value="setName" /></FormField>
</template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("组件化输入：FormField 缺少非空 label 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template><FormField><UiInput :model-value="name" /></FormField></template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /FormField/);
  });

  test("组件化输入：FormField 具名插槽内的控件不算被 FormField 覆盖", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template>
  <FormField label="名称"><template #hint><UiInput :model-value="name" /></template></FormField>
</template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /组件化输入/);
  });

  test("组件化输入：外部可见 label[for] 与控件 id 表达式一致时通过", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Search.vue": `<template>
  <label :for="fieldId(key)">{{ labelOf(key) }}</label>
  <UiInput :id="fieldId(key)" :model-value="read(key)" @update:model-value="value => onInput(key, value)" />
</template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("组件化输入：外部 label 表达式与控件 id 不一致被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template>
  <label :for="fieldId(other)">{{ labelOf(other) }}</label>
  <UiInput :id="fieldId(key)" :model-value="read(key)" />
</template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /组件化输入/);
  });

  test("组件化输入：外部 label 缺少可见文字不算关联", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TOKENS_CSS,
        "src/components/Search.vue": `<template>
  <label :for="fieldId(key)"></label>
  <UiInput :id="fieldId(key)" :model-value="read(key)" />
</template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /组件化输入/);
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

  // 责任 X：模板区用 maskHtmlComments 剥了 HTML 注释，但样式区原先直接取原文，
  // 于是「只出现在 CSS 注释里的装饰性箭头」被误判为结构图标（同一字符写在模板注释
  // 或脚本注释里都不会）。修复后必须两侧都不报，同时**不得**把样式里真实的图标一起吞掉。
  test("CSS 注释里的装饰性箭头不算结构图标", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Comment.vue": `<template><span class="ok">已复制</span></template>
<style scoped>
/* 注释里的 → 不是图标 */
.ok{color:inherit}
</style>
`,
    });
    assert.equal(violations.filter((v) => v.rule === "unicode-structure-icon").length, 0);
  });

  test("遮蔽 CSS 注释不得吞掉样式区里真实的 Unicode 图标", () => {
    const violations = rawViolations({
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Real.vue": `<template><span class="ok">已复制</span></template>
<style scoped>
/* 注释里的 → 不算 */
.ok::before{content:"▸"}
</style>
`,
    });
    assert.equal(violations.filter((v) => v.rule === "unicode-structure-icon").length, 1);
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

  test("例外条目的 rule 与指纹首段不一致时被拒绝，且底层违规不被掩盖", () => {
    const files = {"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Missing.woff2")}`};
    const missing = only(rawViolations(files), "missing-font-asset");
    const violations = collectUiContractViolations({
      root: fixture(files),
      exceptions: {
        exceptions: [
          {
            // 只把 rule 换成可豁免的规则名，指纹仍指向真实的硬门禁违规。掩盖只看指纹，
            // 因此这里必须由一致性校验挡住，否则整条硬门禁会被一个字段改写吃掉。
            rule: "raw-visual-value",
            file: missing.file,
            fingerprint: missing.fingerprint,
            reason: "尝试把硬门禁改写成可豁免的规则名",
            expiresWith: "PLAN-DM-029 Task 9",
          },
        ],
        dynamicVariables: [],
      },
    });
    assert.match(only(violations, "invalid-exception-entry").message, /rule 与指纹首段不一致/);
    // 关键：条目被拒绝后指纹没有进入登记表，底层硬门禁违规仍然报出来。
    assert.equal(only(violations, "missing-font-asset").fingerprint, missing.fingerprint);
  });

  test("例外条目的 rule 写成大小写别名同样被拒绝", () => {
    const files = {"src/styles/tokens.css": `${TOKENS_CSS}${fontFace("Inter", "../assets/fonts/Missing.woff2")}`};
    const missing = only(rawViolations(files), "missing-font-asset");
    const violations = collectUiContractViolations({
      root: fixture(files),
      exceptions: {
        exceptions: [
          {
            rule: "Missing-Font-Asset",
            file: missing.file,
            fingerprint: missing.fingerprint,
            reason: "用大小写别名绕过硬门禁清单",
            expiresWith: "PLAN-DM-029 Task 9",
          },
        ],
        dynamicVariables: [],
      },
    });
    assert.match(only(violations, "invalid-exception-entry").message, /rule 与指纹首段不一致/);
    assert.equal(only(violations, "missing-font-asset").fingerprint, missing.fingerprint);
  });

  test("样式入口缺失时被拒绝，而不是静默通过", () => {
    const root = fixture({"src/styles/tokens.css": TOKENS_CSS});
    // 夹具默认带合法入口：删掉它以后，入口门禁必须显式报缺失（逐文件循环一条都不走
    // 等于把「入口只能是入口」这条约束删掉）。
    rmSync(join(root, "src/style.css"), {force: true});
    const violation = only(collectUiContractViolations({root, exceptions: emptyExceptions()}), "entry-stylesheet-not-import-only");
    assert.equal(violation.file, "src/style.css");
    assert.match(violation.message, /样式入口文件不存在/);
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

  test("例外条目不得豁免例外文件自身的配置错误（否则棘轮无法自我纠错）", () => {
    const files = {
      "src/styles/tokens.css": TOKENS_CSS,
      "src/components/Legacy.vue": `<template><button @click="go">前往</button></template>\n`,
    };
    const root = fixture(files);
    // ① 先制造一个真实的配置类违规：缺 reason/expiresWith 的条目。
    const broken = {rule: "explicit-button-type", file: "src/components/Legacy.vue", fingerprint: "x"};
    const first = collectUiContractViolations({root, exceptions: {exceptions: [broken], dynamicVariables: []}});
    const target = first.find((violation) => violation.rule === "invalid-exception-entry");
    assert.ok(target, "夹具应产出配置类违规");
    // 前提：配置类违规的 `file` 恒为例外文件自身——正因如此，它才可能被一条例外吃掉。
    assert.equal(target.file, DEFAULT_EXCEPTIONS_FILE);
    // ② 用该配置违规自己的指纹登记一条"豁免自身配置错误"的条目（字段全填，只差被拒绝）。
    const selfExemption = {
      rule: target.rule,
      file: target.file,
      fingerprint: target.fingerprint,
      reason: "尝试把例外表自身的配置错误加白",
      expiresWith: "PLAN-DM-029 Task 12",
    };
    const second = collectUiContractViolations({
      root,
      exceptions: {exceptions: [broken, selfExemption], dynamicVariables: []},
    });
    // ③ 该条目必须被拒绝……
    const messages = second.filter((violation) => violation.rule === "invalid-exception-entry").map((violation) => violation.message);
    assert.ok(messages.some((message) => /例外文件自身/.test(message)), `应拒绝豁免例外文件自身的条目，实际消息：${messages.join(" / ")}`);
    // ④ ……且底层配置违规没有被掩盖（条目被拒后指纹没有进登记表）。
    assert.ok(
      second.some((violation) => violation.fingerprint === target.fingerprint),
      "底层配置违规必须仍然报出",
    );
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

describe("表格单元格对齐与 padding 契约", () => {
  // 令牌夹具额外补齐单元格 padding 会消费的间距令牌；缺一个都会变成 undefined-css-variable 噪声。
  const TABLE_TOKENS = `${TOKENS_CSS}:root{--space-1:4px;--space-4:16px}`;
  /** 合法的普通单行表：单档令牌化 padding + 显式中部对齐。 */
  const CLEAN_TABLE = `<template><table><thead><tr><th>名称</th></tr></thead><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>th,td{padding:var(--space-2);vertical-align:middle}</style>
`;
  /** 跨列结构行的外层：零 padding 由 STRUCTURAL_CELL_PAIRS 放行。 */
  const EDIT_ROW_OUTER = `<template><table><tbody><tr class="sheet-editor-row"><td>面板</td></tr></tbody></table></template>
<style scoped>.sheet-editor-row>td{height:auto;padding:0;vertical-align:middle}</style>
`;
  /** 跨列结构行的内层容器：零 padding 的前提是它自己消费间距令牌。 */
  const EDIT_ROW_INNER = `<template><div class="sheet-property-editor">面板</div></template>
<style scoped>.sheet-property-editor{padding:var(--space-4)}</style>
`;
  const tableViolations = (violations) => violations.filter((item) => item.rule.startsWith("table-cell-"));

  test("普通单元格缺 vertical-align 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>.ordinary-table th,.ordinary-table td{padding:var(--space-1)}</style>
`,
      }),
      "table-cell-vertical-align",
    );
    assert.match(violation.message, /vertical-align/);
    assert.match(violation.message, /\.ordinary-table/);
    assert.equal(typeof violation.line, "number");
  });

  test("vertical-align 取值超出 middle/top 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>th,td{padding:var(--space-2);vertical-align:baseline}</style>
`,
      }),
      "table-cell-vertical-align",
    );
    assert.match(violation.message, /baseline/);
  });

  test("多行长文本单元格取 top 通过", () => {
    const violations = tableViolations(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>说明</td></tr></tbody></table></template>
<style scoped>td.col-default{padding:var(--space-2);vertical-align:top}</style>
`,
      }),
    );
    assert.deepEqual(violations, []);
  });

  test("裸非零 padding 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>th,td{padding:10px 8px;vertical-align:middle}</style>
`,
      }),
      "table-cell-padding",
    );
    assert.match(violation.message, /10px 8px/);
  });

  test("令牌化单档 padding 通过", () => {
    const violations = tableViolations(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": CLEAN_TABLE,
      }),
    );
    assert.deepEqual(violations, []);
  });

  test("同一张表的普通格出现两档 padding 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>th,td{padding:var(--space-2);vertical-align:middle}
th{padding:var(--space-1);vertical-align:middle}</style>
`,
      }),
      "table-cell-padding",
    );
    assert.match(violation.message, /--space-2/);
    assert.match(violation.message, /--space-1/);
  });

  test("普通数据格 padding:0 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>.values-table td{padding:0;vertical-align:middle}</style>
`,
      }),
      "table-cell-padding",
    );
    assert.match(violation.message, /STRUCTURAL_CELL_PAIRS/);
  });

  test("伪造通用 colspan 零 padding 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/Table.vue": `<template><table><tbody><tr><td colspan="2">说明</td></tr></tbody></table></template>
<style scoped>td[colspan]{padding:0;vertical-align:middle}</style>
`,
      }),
      "table-cell-padding",
    );
    assert.match(violation.message, /STRUCTURAL_CELL_PAIRS/);
  });

  test("结构配对：外层零 padding 且内层消费间距令牌时通过", () => {
    const violations = tableViolations(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/SheetTable.vue": EDIT_ROW_OUTER,
        "src/components/sheets/SheetPropertyEditor.vue": EDIT_ROW_INNER,
      }),
    );
    assert.deepEqual(violations, []);
  });

  test("结构配对：内层丢失间距令牌后失败", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/SheetTable.vue": EDIT_ROW_OUTER,
        "src/components/sheets/SheetPropertyEditor.vue": EDIT_ROW_INNER.replace("var(--space-4)", "16px"),
      }),
      "table-cell-padding",
    );
    assert.match(violation.file, /SheetPropertyEditor\.vue$/);
    assert.match(violation.message, /--space-4/);
  });

  test("结构配对：内层组件缺失时失败", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/SheetTable.vue": EDIT_ROW_OUTER,
      }),
      "table-cell-padding",
    );
    assert.match(violation.message, /SheetPropertyEditor\.vue/);
  });

  test("结构配对：同样的选择器出现在其它文件仍被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/styles/tokens.css": TABLE_TOKENS,
        "src/components/SheetTable.vue": EDIT_ROW_OUTER,
        "src/components/sheets/SheetPropertyEditor.vue": EDIT_ROW_INNER,
        "src/components/OtherPanel.vue": EDIT_ROW_OUTER,
      }),
      "table-cell-padding",
    );
    assert.match(violation.file, /OtherPanel\.vue$/);
  });

  test("选择器出现在注释或字符串里不触发", () => {
    const violations = tableViolations(
      rawViolations({
        "src/styles/tokens.css": `${TABLE_TOKENS}/* td{padding:0} */\n`,
        "src/components/Text.vue": `<template><p>td{padding:0}</p></template>
<style scoped>.hint{content:"td{padding:0}"}</style>
`,
      }),
    );
    assert.deepEqual(violations, []);
  });
});

describe("变异证据：每类违规都使 CLI 退出 1", () => {
  const clean = {
    "src/styles/tokens.css": TOKENS_CSS,
    "src/components/Clean.vue": `<template>
  <label for="name">名称</label><input id="name" v-model="name" />
  <UiInput :label="name" :model-value="name" />
  <button type="button" :aria-label="label" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button>
</template>
<style scoped>.panel{font-size:var(--font-label);color:var(--color-text-primary);border:1px solid var(--color-border-subtle)}</style>
`,
  };

  /** 表格单元格变异夹具的令牌：补齐 `--space-1`/`--space-4`，避免夹杂未定义变量噪声。 */
  const TABLE_TOKENS = `${TOKENS_CSS}:root{--space-1:4px;--space-4:16px}`;
  /** 合法的表体组件：每条表格变异只改这一处选择器或声明。 */
  const TABLE_COMPONENT = `<template><table><thead><tr><th>名称</th></tr></thead><tbody><tr><td>值</td></tr></tbody></table></template>
<style scoped>th,td{padding:var(--space-2);vertical-align:middle}</style>
`;

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
      // 审查 I3（责任 U）：组件化输入的 label 在原语内部条件渲染，调用点缺失必须仍被 CLI 拒绝。
      step1Class: "搜索输入无可见 label",
      name: "组件化输入调用点缺可见 label",
      rule: "visible-input-label",
      files: {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace(':label="name" ', "")},
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
    {
      step1Class: "表格单元格缺 vertical-align",
      name: "表格单元格缺 vertical-align",
      rule: "table-cell-vertical-align",
      files: {"src/components/Clean.vue": TABLE_COMPONENT.replace(";vertical-align:middle", ""), "src/styles/tokens.css": TABLE_TOKENS},
    },
    {
      step1Class: "表格单元格裸 padding",
      name: "表格单元格裸 padding",
      rule: "table-cell-padding",
      files: {
        "src/components/Clean.vue": TABLE_COMPONENT.replace("padding:var(--space-2)", "padding:10px 8px"),
        "src/styles/tokens.css": TABLE_TOKENS,
      },
    },
    {
      step1Class: "同表普通格两档 padding",
      name: "同表普通格两档 padding",
      rule: "table-cell-padding",
      files: {
        "src/components/Clean.vue": TABLE_COMPONENT.replace(
          "</style>",
          "th{padding:var(--space-1);vertical-align:middle}</style>",
        ),
        "src/styles/tokens.css": TABLE_TOKENS,
      },
    },
    {
      step1Class: "普通单元格零 padding",
      name: "普通单元格零 padding",
      rule: "table-cell-padding",
      files: {
        "src/components/Clean.vue": TABLE_COMPONENT.replace("padding:var(--space-2)", "padding:0"),
        "src/styles/tokens.css": TABLE_TOKENS,
      },
    },
    {
      step1Class: "伪造 colspan 零 padding",
      name: "伪造 colspan 零 padding",
      rule: "table-cell-padding",
      files: {
        "src/components/Clean.vue": TABLE_COMPONENT.replace(
          "</style>",
          "td[colspan]{padding:0;vertical-align:middle}</style>",
        ),
        "src/styles/tokens.css": TABLE_TOKENS,
      },
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
  /** PLAN-DM-043 Task 1 新增的五类表格单元格判定。 */
  const TABLE_CLASSES = [
    "表格单元格缺 vertical-align",
    "表格单元格裸 padding",
    "同表普通格两档 padding",
    "普通单元格零 padding",
    "伪造 colspan 零 padding",
  ];

  function runFixture(files) {
    const root = fixture({
      ...clean,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
      ...files,
    });
    return spawnSync(process.execPath, [CLI_PATH, `--root=${root}`], {encoding: "utf8"});
  }

  test("每类判定都有 CLI 级变异证据（Step 1 十一类 + Task 2 四条 + PLAN-DM-043 五类）", () => {
    // 裸视觉值一类在 brief 里是一个分类，这里拆成字号与图标尺寸两条注入。
    const classes = new Set(mutations.map((mutation) => mutation.step1Class));
    const knownClasses = [...STEP1_CLASSES, ...TASK2_CLASSES, ...TABLE_CLASSES];
    for (const name of knownClasses) {
      assert.ok(classes.has(name), `缺少「${name}」的 CLI 级变异证据`);
    }
    // 分类集合必须恰好是这三组，不允许默默少测或凭空多出未归类的注入。
    assert.deepEqual([...classes].filter((name) => !knownClasses.includes(name)).sort(), []);
    assert.equal(classes.size, knownClasses.length, [...classes].join("、"));
    assert.equal(mutations.length, 22);
    assert.equal(new Set(mutations.map((mutation) => mutation.name)).size, 22);
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
      "table-cell-padding",
      "table-cell-vertical-align",
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
