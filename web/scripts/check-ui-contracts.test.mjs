// UI 静态契约检查器的契约测试（PLAN-DM-029 Task 1）。
//
// 本文件是所有规则的可执行契约：夹具全部写在系统临时目录里，通过
// `collectUiContractViolations({root, exceptions})` 与真实 CLI 子进程验证。
//
// 变异证据套件（Step 8）向合法夹具逐类注入违规并断言真实 CLI 子进程退出 1；它只在
// 检查器、规则或例外格式变化时要求重跑。整套用例约 7.5 秒，其中单次 CLI 子进程
// 启动约 0.5 秒，因此新增 CLI 级变异用例时按「每次 spawn 约 0.5 秒」估算预算。

import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {mkdirSync, mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, describe, test} from "node:test";

import {collectUiContractViolations, formatViolation, runCli} from "./check-ui-contracts.mjs";

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
      "src/style.css": TOKENS_CSS,
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
        "src/style.css": TOKENS_CSS,
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
      "src/components/Good.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--color-text-primary);padding:var(--space-2,var(--font-label))}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("组件局部声明可解析自身引用", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Local.vue": `<template><p>文本</p></template>
<style scoped>.a{--local-gap:var(--space-2);gap:var(--local-gap)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("循环引用被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/style.css": `${TOKENS_CSS}:root{--loop-a:var(--loop-b);--loop-b:var(--loop-a)}`,
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
      "src/style.css": TOKENS_CSS,
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
      root: fixture({"src/style.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
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
      root: fixture({"src/style.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
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
      root: fixture({"src/style.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
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
        root: fixture({"src/style.css": TOKENS_CSS, "src/views/Sheets.vue": sheets}),
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
      "src/components/Buttons.vue": `<template><button type="button" @click="save">保存</button><button type="submit">提交</button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("搜索输入缺可见 label 被拒绝", () => {
    const violation = only(
      rawViolations({
        "src/style.css": TOKENS_CSS,
        "src/components/Search.vue": `<template><div class="search"><input v-model="query" :placeholder="hint" /></div></template>
`,
      }),
      "visible-input-label",
    );
    assert.match(violation.message, /label/);
  });

  test("label 包裹或 label[for] 关联的输入通过", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
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
        "src/style.css": TOKENS_CSS,
        "src/components/IconButton.vue": `<template><button type="button" class="icon" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button></template>
`,
      }),
      "icon-button-name",
    );
    assert.match(violation.message, /可读名称/);
  });

  test("有 aria-label 的图标按钮通过", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/IconButton.vue": `<template><button type="button" class="icon" :aria-label="label" @click="close"><svg viewBox="0 0 24 24"><path d="M6 6L18 18" /></svg></button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("Unicode 结构图标被拒绝", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Unicode.vue": `<template><span aria-hidden="true">▸</span><span aria-hidden="true">◐</span></template>
`,
    });
    assert.equal(violations.filter((v) => v.rule === "unicode-structure-icon").length, 2);
  });

  test("中文文案与普通标点不被当作结构图标", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Text.vue": `<template><p>保存（另存为）— 已复制，共 3 项；引用“目录”模板。</p></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("属性值里的 > 不截断标签：type 与可见文字仍被正确读取", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Operators.vue": `<template><button :disabled="count>=1" type="button">保存</button></template>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("属性值里的 > 之后仍能定位缺 type 的按钮", () => {
    const violation = only(
      rawViolations({
        "src/style.css": TOKENS_CSS,
        "src/components/Operators.vue": `<template><button :disabled="count>=1" @click="go">前往</button></template>
`,
      }),
      "explicit-button-type",
    );
    assert.equal(violation.fingerprint, "explicit-button-type|src/components/Operators.vue|前往|1");
  });

  test("图标在文字之前的按钮不误判为缺少可读名称", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
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
      rawViolations({"src/style.css": TOKENS_CSS, "src/components/Comment.vue": source}),
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
    const violations = rawViolations({"src/style.css": TOKENS_CSS, "src/components/Positions.vue": source});
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": `${TOKENS_CSS}.mask{background:rgba(16,24,40,.55)}`,
      "src/components/Color.vue": `<template><p>文本</p></template>
<style scoped>.a{color:var(--color-text-primary);background:rgba(16,24,40,.55)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("裸字号、高度与圆角被拒绝，令牌与合法常量通过", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
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
      "src/style.css": `${TOKENS_CSS}
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": `:root{--font-label:13px;font-size:13px}html[data-theme="dark"]{--font-label:14px;font-size:14px}:root,html[data-theme="light"]{--font-label:15px;font-size:15px}`,
      "src/components/Token.vue": `<template><p>文本</p></template>
<style scoped>.panel{font-size:var(--font-label)}</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("图标尺寸（宽度家族）与高度家族同等判定", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
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
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Query.vue": `<template><p>文本</p></template>
<style scoped>
@media (max-width:900px){.panel{font-size:var(--font-label)}}
@container value-body (max-width:511px){.panel{line-height:var(--font-label)}}
@media (min-width:600px) and (max-width:900px){.panel{height:var(--font-label)}}
</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });

  test("@keyframes 的 from/to/百分比关键帧不作为规则参与判定", () => {
    const violations = rawViolations({
      "src/style.css": TOKENS_CSS,
      "src/components/Toast.vue": `<template><p>文本</p></template>
<style>
@keyframes toast-in{from{height:0;opacity:0}0%{opacity:.2}100%{height:10px;opacity:1}to{height:10px}}
</style>
`,
    });
    assert.deepEqual(rulesOf(violations), []);
  });
});

describe("棘轮：例外登记与陈旧例外", () => {
  const files = {
    "src/style.css": TOKENS_CSS,
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
        "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
      "src/components/Finger.vue": `<template><button @click="go">前往</button></template>
`,
    });
    const shifted = rawViolations({
      "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
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
      "src/style.css": TOKENS_CSS,
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
    const root = fixture({"src/style.css": TOKENS_CSS});
    const result = runCli([`--root=${root}`]);
    assert.equal(result.exitCode, 2);
    assert.match(result.stderr, /ui-contract-exceptions\.json/);
  });

  test("源码根目录不可读时明确失败而不是静默通过", () => {
    const root = fixture({
      "src/style.css": TOKENS_CSS,
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
    "src/style.css": TOKENS_CSS,
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
      files: {"src/style.css": `${TOKENS_CSS}:root{--loop-a:var(--loop-b);--loop-b:var(--loop-a)}`},
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
  ];

  function runFixture(files) {
    const root = fixture({
      ...clean,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
      ...files,
    });
    return spawnSync(process.execPath, [CLI_PATH, `--root=${root}`], {encoding: "utf8"});
  }

  test("Step 1 的 11 类判定都有 CLI 级变异证据", () => {
    // 裸视觉值一类在 brief 里是一个分类，这里拆成字号与图标尺寸两条注入。
    const classes = new Set(mutations.map((mutation) => mutation.step1Class));
    assert.equal(classes.size, 11, [...classes].join("、"));
    assert.equal(mutations.length, 12);
    assert.equal(new Set(mutations.map((mutation) => mutation.name)).size, 12);
    assert.deepEqual([...new Set(mutations.map((mutation) => mutation.rule))].sort(), [
      "circular-css-variable",
      "dynamic-variable-not-registered",
      "explicit-button-type",
      "global-selector-in-component",
      "icon-button-name",
      "raw-hex-color",
      "raw-visual-value",
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
