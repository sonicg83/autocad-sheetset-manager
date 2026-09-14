// UI 静态契约检查器的契约测试（PLAN-DM-029 Task 1）。
//
// 本文件是所有规则的可执行契约：夹具全部写在系统临时目录里，通过
// `collectUiContractViolations({root, exceptions})` 与真实 CLI 子进程验证。
//
// 变异证据套件（Step 8）向合法夹具逐类注入违规并断言 CLI 退出 1；它只在检查器、
// 规则或例外格式变化时要求重跑，因此整体成本保持在十几毫秒级的子进程启动量级。

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
});

describe("视觉值规则", () => {
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

  const mutations = {
    "undefined-css-variable": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--font-label)", "var(--font-nope)")},
    "circular-css-variable": {"src/style.css": `${TOKENS_CSS}:root{--loop-a:var(--loop-b);--loop-b:var(--loop-a)}`},
    "explicit-button-type": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace('type="button" ', "")},
    "visible-input-label": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace('<label for="name">名称</label>', "")},
    "icon-button-name": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace(':aria-label="label" ', "")},
    "unicode-structure-icon": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace(">名称<", ">▸<")},
    "global-selector-in-component": {
      "src/components/Clean.vue": clean["src/components/Clean.vue"].replace("<style scoped>", "<style>").replace("</style>", "button{background:none}</style>"),
    },
    "raw-hex-color": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--color-text-primary)", "#17203333")},
    "raw-visual-value": {"src/components/Clean.vue": clean["src/components/Clean.vue"].replace("var(--font-label)", "15px")},
  };

  function runFixture(files) {
    const root = fixture({
      ...clean,
      ...files,
      "scripts/ui-contract-exceptions.json": JSON.stringify(emptyExceptions()),
    });
    return spawnSync(process.execPath, [CLI_PATH, `--root=${root}`], {encoding: "utf8"});
  }

  test("合法夹具退出 0", () => {
    const result = runFixture({});
    assert.equal(result.status, 0, result.stdout + result.stderr);
  });

  for (const [rule, files] of Object.entries(mutations)) {
    test(`注入 ${rule} 后退出 1`, () => {
      const result = runFixture(files);
      assert.equal(result.status, 1, `期望 ${rule} 使 CLI 失败，实际输出：${result.stdout}${result.stderr}`);
      assert.match(result.stdout, new RegExp(`\\[${rule}\\]`));
    });
  }

  test("恢复夹具后重新退出 0", () => {
    const result = runFixture({});
    assert.equal(result.status, 0, result.stdout + result.stderr);
  });
});
