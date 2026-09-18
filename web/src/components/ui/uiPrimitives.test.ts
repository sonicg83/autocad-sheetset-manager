// @vitest-environment happy-dom
// 公共视觉原语契约（PLAN-DM-029 Task 3 Step 2）：按钮 variant/size/禁用/加载、图标按钮的
// 可访问名称、图标注册表封闭性、字段 label 与 hint/error 关联、选择框默认高度、
// 输入/选择框的 hover 状态（SPEC-DM-006 §232；Task 5 修复轮 Ruling 33 补）。
//
// happy-dom 不解析样式表与 CSS 自定义属性链，故「默认高度 38px」只能按「样式块声明消费的
// 令牌 + 令牌链最终值」断言：先证明实现消费 `--input-height`，再沿
// `--input-height → --control-height-form → --height-38` 解出 38px。这**不能**证明该声明
// 挂在活选择器上，更不能证明浏览器算出的高度：本任务的新原语当前没有任何页面消费，
// `web/tests/e2e/properties-definitions.spec.ts` 量的是 `.definition-panel` 里的遗留控件，
// 与本任务无关。真实计算高度（输入 38px、按钮 36px）须在 Task 4 接入壳层后新增计算样式断言。
import {describe,expect,it,vi} from "vitest";
import {mount} from "@vue/test-utils";
import {defineComponent,h} from "vue";
import {readFileSync} from "node:fs";
import UiButton from "./UiButton.vue";
import UiIcon from "./UiIcon.vue";
import UiIconButton from "./UiIconButton.vue";
import UiInput from "./UiInput.vue";
import UiSelect from "./UiSelect.vue";
import FormField from "./FormField.vue";
import {UI_ICONS} from "./icons";

// Task 3 Step 4 固定的首批图标名：注册表是封闭联合类型，改名单必须同步改契约测试。
const FIRST_BATCH = [
  "theme", "settings", "close", "chevron-left", "chevron-right", "chevron-up", "chevron-down",
  "status-dot", "search", "folder", "copy",
];

const readSource = (relative: string) => readFileSync(new URL(relative, import.meta.url), "utf8");

function scopedStyle(source: string) {
  const match = /<style scoped>([\s\S]*?)<\/style>/.exec(source);
  if (match === null) throw new Error("组件缺少 scoped 样式块");
  return match[1];
}

/** 剥掉注释后的源码：用于「不得出现某指令」一类硬约束断言，避免把说明文字判成用法。 */
function stripComments(source: string) {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

/** 解析 CSS 里的自定义属性声明（测试只解析令牌文件，不实现完整 CSS 语法）。 */
function tokenDeclarations(css: string) {
  const declarations = new Map<string, string>();
  for (const match of css.matchAll(/(--[\w-]+)\s*:\s*([^;{}]+);/g)) declarations.set(match[1], match[2].trim());
  return declarations;
}

/** 沿 `var(--x)` 链解析令牌的最终值，最多 5 跳。 */
function resolveToken(declarations: Map<string, string>, name: string) {
  let value = declarations.get(name) ?? "";
  for (let hop = 0; hop < 5; hop += 1) {
    const inner = /^var\((--[\w-]+)\)$/.exec(value);
    if (inner === null) break;
    value = declarations.get(inner[1]) ?? "";
  }
  return value;
}

const TOKENS = tokenDeclarations(readSource("../../styles/tokens.css"));

describe("UiButton", () => {
  it("默认显式声明 type=button，并使用 secondary/default 档", () => {
    const wrapper = mount(UiButton, {slots: {default: () => "确定"}});
    expect(wrapper.element.tagName).toBe("BUTTON");
    expect(wrapper.attributes("type")).toBe("button");
    expect(wrapper.classes()).toContain("ui-button--secondary");
    expect(wrapper.classes()).toContain("ui-button--default");
  });

  it("四种 variant 与两种 size 映射到稳定类名", () => {
    for (const variant of ["primary", "secondary", "danger", "link"] as const) {
      expect(mount(UiButton, {props: {variant}}).classes()).toContain(`ui-button--${variant}`);
    }
    expect(mount(UiButton, {props: {size: "compact"}}).classes()).toContain("ui-button--compact");
    expect(mount(UiButton, {props: {size: "default"}}).classes()).toContain("ui-button--default");
  });

  it("disabled 与 loading 都落到原生 disabled 上，loading 额外暴露 aria-busy 并保留文案", () => {
    const disabled = mount(UiButton, {props: {disabled: true}, slots: {default: () => "保存"}});
    expect(disabled.attributes("disabled")).toBeDefined();
    expect((disabled.element as HTMLButtonElement).disabled).toBe(true);

    const loading = mount(UiButton, {props: {loading: true}, slots: {default: () => "保存"}});
    expect((loading.element as HTMLButtonElement).disabled).toBe(true);
    expect(loading.attributes("aria-busy")).toBe("true");
    expect(loading.text()).toContain("保存");
  });

  it("submit 只能由调用方显式声明", () => {
    expect(mount(UiButton, {props: {type: "submit"}}).attributes("type")).toBe("submit");
  });

  it("label 映射到 aria-label，未提供时不写该属性", () => {
    // 插槽里的可见文案在静态门禁看来不可见，label 是给「插槽无可见文案」的用法提供的名称源。
    expect(mount(UiButton, {props: {label: "关闭"}}).attributes("aria-label")).toBe("关闭");
    expect(mount(UiButton, {slots: {default: () => "确定"}}).attributes("aria-label")).toBeUndefined();
  });

  it("ariaDisabled 保持可聚焦：不写原生 disabled，输出 aria-disabled 与统一禁用类", () => {
    // 可聚焦语义禁用（PLAN-DM-034）：按钮必须仍能进入 Tab 顺序并被读屏播报「禁用」，
    // 所以只落 `aria-disabled` 与统一类，绝不写原生 `disabled`（原生 disabled 不可聚焦）。
    const wrapper = mount(UiButton, {props: {ariaDisabled: true}, slots: {default: () => "保存"}});
    expect(wrapper.element.tagName).toBe("BUTTON");
    expect((wrapper.element as HTMLButtonElement).disabled).toBe(false);
    expect(wrapper.attributes("disabled")).toBeUndefined();
    expect(wrapper.attributes("aria-disabled")).toBe("true");
    expect(wrapper.classes()).toContain("ui-button--aria-disabled");
  });

  it("ariaDisabled 拦截原生 click：父监听器与组件 click emit 计数均为 0，且事件被 preventDefault", async () => {
    // 原生 button 的 Enter/Space/程序化 .click() 最终都汇聚到根按钮的 click 事件，
    // 故只需在根按钮上派发一次原生 click 即覆盖全部触发路径。
    const onClick = vi.fn();
    const wrapper = mount(UiButton, {props: {ariaDisabled: true}, attrs: {onClick}, slots: {default: () => "保存"}});
    const event = new MouseEvent("click", {bubbles: true, cancelable: true});
    wrapper.element.dispatchEvent(event);
    await wrapper.vm.$nextTick();
    expect(event.defaultPrevented).toBe(true);
    expect(onClick).toHaveBeenCalledTimes(0);
    expect(wrapper.emitted("click")).toBeUndefined();
  });

  it("loading 与 disabled 仍走原生 disabled，不受 ariaDisabled 途径影响", () => {
    const loading = mount(UiButton, {props: {loading: true, ariaDisabled: true}, slots: {default: () => "保存"}});
    const disabled = mount(UiButton, {props: {disabled: true}, slots: {default: () => "保存"}});
    expect((loading.element as HTMLButtonElement).disabled).toBe(true);
    expect((disabled.element as HTMLButtonElement).disabled).toBe(true);
  });

  it("ariaDisabled=false 不输出多余属性，点击仍正常 emit", async () => {
    const onClick = vi.fn();
    const wrapper = mount(UiButton, {attrs: {onClick}, slots: {default: () => "保存"}});
    expect(wrapper.attributes("aria-disabled")).toBeUndefined();
    expect(wrapper.classes()).not.toContain("ui-button--aria-disabled");
    await wrapper.trigger("click");
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted("click")).toHaveLength(1);
  });

  it("hover/active 外观排除两种禁用态，禁用光标同时命中 :disabled 与统一禁用类，且不设 pointer-events:none", () => {
    // 源文本断言（与 UiInput/UiSelect 的 hover 契约同一写法）：aria-disabled 按钮没有原生
    // `:disabled` 伪类可依赖，hover/active 必须显式排除统一禁用类，否则会盖过禁用外观；
    // 禁用光标则要同时命中两种禁用态。`pointer-events:none` 是硬约束：设了它鼠标反馈和
    // 事件守卫测试都会失效。
    const style = scopedStyle(readSource("./UiButton.vue"));
    expect(style).toContain(":hover:not(:disabled):not(.ui-button--aria-disabled)");
    expect(style).toContain(":active:not(:disabled):not(.ui-button--aria-disabled)");
    expect(style).toContain(".ui-button:disabled,.ui-button--aria-disabled{cursor:not-allowed}");
    expect(style).not.toContain("pointer-events:none");
  });
});

describe("UiIconButton", () => {
  it("用 label 提供可访问名称，图标本身对读屏隐藏", () => {
    const wrapper = mount(UiIconButton, {props: {label: "关闭", icon: "close"}});
    expect(wrapper.element.tagName).toBe("BUTTON");
    expect(wrapper.attributes("type")).toBe("button");
    expect(wrapper.attributes("aria-label")).toBe("关闭");
    const svg = wrapper.find("svg");
    expect(svg.attributes("aria-hidden")).toBe("true");
    expect(svg.attributes("focusable")).toBe("false");
  });

  it("缺少 label 时类型与运行期都失败", () => {
    // @ts-expect-error label 是必填的可访问名称：缺省必须在编译期就报错
    const mountWithoutLabel = () => mount(UiIconButton, {props: {icon: "close"}});
    expect(mountWithoutLabel).toThrow(/label/);
    expect(() => mount(UiIconButton, {props: {label: "  ", icon: "close"}})).toThrow(/label/);
  });

  it("点击事件经由根元素透传给调用方", async () => {
    const onClick = vi.fn();
    const wrapper = mount(UiIconButton, {props: {label: "关闭", icon: "close"}, attrs: {onClick}});
    await wrapper.trigger("click");
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("UiIcon 与图标注册表", () => {
  it("只从封闭注册表渲染本地 SVG，不注入任意 HTML", () => {
    const wrapper = mount(UiIcon, {props: {name: "close"}});
    expect(wrapper.element.tagName).toBe("svg");
    expect(wrapper.attributes("viewBox")).toBe("0 0 24 24");
    expect(wrapper.attributes("aria-hidden")).toBe("true");
    expect(wrapper.attributes("focusable")).toBe("false");
    expect(wrapper.findAll("path").length).toBeGreaterThan(0);
    // `v-html` 与 `innerHTML` 是硬约束（静态门禁把任意 HTML 注入视作风险）：注释里可以
    // 提到它们，源码的有效部分不得出现，故先剥注释再断言。
    const code = stripComments(readSource("./UiIcon.vue"));
    for (const forbidden of ["v-html", "innerHTML"]) expect(code).not.toContain(forbidden);
  });

  it("注册表键集合等于 Step 4 固定的首批图标", () => {
    expect(Object.keys(UI_ICONS).sort()).toEqual([...FIRST_BATCH].sort());
  });

  it("每个图标的几何数据都在 24×24 视窗内且不含标记字符", () => {
    for (const [name, definition] of Object.entries(UI_ICONS)) {
      expect(definition.shapes.length, name).toBeGreaterThan(0);
      for (const shape of definition.shapes) {
        if (shape.kind === "path") {
          expect(shape.d, name).toMatch(/^[MmLlHhVvCcSsQqTtAaZz0-9.,\s-]+$/);
          continue;
        }
        const coordinates = shape.kind === "circle" ? [shape.cx, shape.cy, shape.r] : [shape.x, shape.y, shape.width, shape.height, shape.rx];
        for (const value of coordinates) expect(value, `${name} 坐标越界`).toBeGreaterThanOrEqual(0);
        for (const value of coordinates) expect(value, `${name} 坐标越界`).toBeLessThanOrEqual(24);
      }
    }
  });

  it("status-dot 以填充圆渲染，其余图标保持描边", () => {
    const dot = mount(UiIcon, {props: {name: "status-dot"}});
    expect(dot.findAll("circle").length).toBe(1);
    expect(dot.attributes("fill")).toBe("currentColor");
    expect(dot.attributes("stroke")).toBe("none");
    expect(mount(UiIcon, {props: {name: "search"}}).attributes("fill")).toBe("none");
  });

  it("尺寸档位映射到稳定类名", () => {
    expect(mount(UiIcon, {props: {name: "search"}}).classes()).toContain("ui-icon--md");
    expect(mount(UiIcon, {props: {name: "search", size: "sm"}}).classes()).toContain("ui-icon--sm");
    expect(mount(UiIcon, {props: {name: "search", size: "lg"}}).classes()).toContain("ui-icon--lg");
  });
});

describe("UiInput", () => {
  it("自带 label 时用 label[for] 关联到控件 id", () => {
    const wrapper = mount(UiInput, {props: {label: "搜索", id: "search-1"}});
    expect(wrapper.find("label").text()).toBe("搜索");
    expect(wrapper.find("label").attributes("for")).toBe("search-1");
    expect(wrapper.find("input").attributes("id")).toBe("search-1");
  });

  it("省略 label 时不渲染 label 元素，但控件仍有唯一 id 供 FormField 关联", () => {
    const wrapper = mount(UiInput);
    expect(wrapper.find("label").exists()).toBe(false);
    expect(wrapper.find("input").attributes("id")).toMatch(/^ui-input-/);
  });

  it("透传 v-model、错误态与 aria-describedby 关联", async () => {
    const wrapper = mount(UiInput, {props: {modelValue: "旧值", id: "field-1", describedBy: "field-1-hint", invalid: true}});
    const input = wrapper.find("input");
    expect((input.element as HTMLInputElement).value).toBe("旧值");
    expect(input.attributes("aria-describedby")).toBe("field-1-hint");
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(wrapper.classes()).toContain("ui-input--invalid");
    await input.setValue("新值");
    expect(wrapper.emitted("update:modelValue")).toEqual([["新值"]]);
  });

  it("未声明错误态时不写 aria-invalid", () => {
    expect(mount(UiInput).find("input").attributes("aria-invalid")).toBeUndefined();
  });

  it("控件字号消费组件令牌 --input-font-size，令牌链最终为 14px", () => {
    // 用组件令牌而不是依赖 reset 层的 `font:inherit`：控件排版不随重置层变动，
    // 且 14px 与正文同档（SPEC-DM-006 字号阶梯 12/13/14/16/20/24）。
    expect(scopedStyle(readSource("./UiInput.vue"))).toContain("font-size:var(--input-font-size)");
    expect(scopedStyle(readSource("./UiSelect.vue"))).toContain("font-size:var(--input-font-size)");
    expect(resolveToken(TOKENS, "--input-font-size")).toBe("14px");
  });

  it("提供 SPEC-DM-006 §232 要求的 hover 状态，且挂在控件类上而不是根元素上", () => {
    // 根元素是 `<span class="ui-input">`、真正的控件是内部 `<input class="ui-input__control">`：
    // scoped 的 `data-v-*` 只追加到子组件根元素，所以页面侧写 `.value-item input:hover` 永不命中
    // （Task 5 修复轮 Ruling 33）。hover 因此只能由原语自己提供，且必须挂在控件类上。
    // `:not(.ui-input--invalid)` 守卫是 Ruling 35：`.ui-input__control:hover:not(:disabled)` 特异度 (0,3,0)
    // 会压过 `.ui-input--invalid .ui-input__control` 的 (0,2,0)（特异性优先于源顺序），
    // 从而用瞬时可供性反馈遮蔽持久错误态。故 hover 只能作用于非无效控件。
    // 注意：本条是源文本断言，拓不到「声明写了但不命中」——那个由
    // `tests/e2e/properties-visual-evidence.spec.ts` 的真实 hover 计算样式断言负责。
    expect(scopedStyle(readSource("./UiInput.vue")))
      .toContain(".ui-input:not(.ui-input--invalid) .ui-input__control:hover:not(:disabled){border-color:var(--color-accent)}");
    expect(resolveToken(TOKENS, "--color-accent")).toMatch(/^#[0-9A-F]{6}$/i);
  });
});

describe("UiSelect", () => {
  it("默认高度消费 --input-height，令牌链最终为 38px", () => {
    expect(scopedStyle(readSource("./UiSelect.vue"))).toContain("height:var(--input-height)");
    expect(resolveToken(TOKENS, "--input-height")).toBe("38px");
    expect(resolveToken(TOKENS, "--control-height-form")).toBe("38px");
    expect(TOKENS.get("--height-38")).toBe("38px");
  });

  it("同样提供 SPEC-DM-006 §232 要求的 hover 状态", () => {
    // 同 `UiInput`：`:not(.ui-select--invalid)` 守卫确保错误态优先于 hover（Ruling 35）。
    expect(scopedStyle(readSource("./UiSelect.vue")))
      .toContain(".ui-select:not(.ui-select--invalid) .ui-select__control:hover:not(:disabled){border-color:var(--color-accent)}");
  });

  it("渲染默认插槽提供的 option，并透传 v-model", async () => {
    const wrapper = mount(UiSelect, {
      props: {modelValue: "name", id: "scope-1", label: "搜索范围"},
      slots: {default: () => [h("option", {value: "name"}, "名称"), h("option", {value: "value"}, "值")]},
    });
    expect(wrapper.findAll("option").length).toBe(2);
    expect(wrapper.find("label").attributes("for")).toBe("scope-1");
    expect((wrapper.find("select").element as HTMLSelectElement).value).toBe("name");
    await wrapper.find("select").setValue("value");
    expect(wrapper.emitted("update:modelValue")).toEqual([["value"]]);
  });
});

describe("FormField", () => {
  it("渲染可见 label，并把 id 与错误态下发给插槽控件", () => {
    const wrapper = mount(FormField, {
      props: {label: "图纸集名称", id: "field-1", error: "名称不能为空"},
      slots: {default: (slotProps: {id: string; describedBy?: string; invalid: boolean}) => h(UiInput, {...slotProps})},
    });
    expect(wrapper.findAll("label").length).toBe(1);
    expect(wrapper.find("label").text()).toBe("图纸集名称");
    expect(wrapper.find("label").attributes("for")).toBe("field-1");
    expect(wrapper.find("input").attributes("id")).toBe("field-1");
    expect(wrapper.find("input").attributes("aria-invalid")).toBe("true");
    expect(wrapper.classes()).toContain("form-field--invalid");
  });

  it("hint/error 的 id 按出现情况聚合进 aria-describedby", () => {
    const both = mount(FormField, {
      props: {label: "名称", id: "field-2", hint: "最多 255 字符", error: "重复"},
      slots: {default: (slotProps: {id: string; describedBy?: string}) => h(UiInput, {...slotProps})},
    });
    expect(both.find(".form-field__hint").attributes("id")).toBe("field-2-hint");
    expect(both.find(".form-field__error").attributes("id")).toBe("field-2-error");
    expect(both.find("input").attributes("aria-describedby")).toBe("field-2-hint field-2-error");

    const hintOnly = mount(FormField, {
      props: {label: "名称", id: "field-3", hint: "最多 255 字符"},
      slots: {default: (slotProps: {id: string; describedBy?: string}) => h(UiInput, {...slotProps})},
    });
    expect(hintOnly.find("input").attributes("aria-describedby")).toBe("field-3-hint");
    expect(hintOnly.find(".form-field__error").exists()).toBe(false);

    const plain = mount(FormField, {
      props: {label: "名称", id: "field-4"},
      slots: {default: (slotProps: {id: string; describedBy?: string}) => h(UiInput, {...slotProps})},
    });
    expect(plain.find("input").attributes("aria-describedby")).toBeUndefined();
  });

  it("未提供 id 时自行生成控件 id，并与 label[for] 保持一致", () => {
    const wrapper = mount(FormField, {props: {label: "名称"}, slots: {default: (slotProps: {id: string}) => h(UiSelect, {...slotProps})}});
    const forId = wrapper.find("label").attributes("for");
    expect(forId).toMatch(/^form-field-/);
    expect(wrapper.find("select").attributes("id")).toBe(forId);
  });
});

// 兜底 id 必须在**同一页面**内唯一。@vue/test-utils 每次 `mount()` 都是新的 app，
// 所以「挂两次再比 id」既可能放过「app 内唯一」的实现、也可能误判正确实现；
// 这两条用例在同一个 app 里挂多个未传 `id` 的实例，断言各自成对关联。
describe("实例标识（同页多实例）", () => {
  it("同一 app 内的两个 FormField 各自生成不同 id，label[for] 与 aria-describedby 都指向自己", () => {
    const slot = (slotProps: {id: string; describedBy?: string; invalid: boolean}) => h(UiInput, {...slotProps});
    const wrapper = mount(defineComponent({
      render: () => h("div", [
        h(FormField, {label: "第一个", hint: "提示一", error: "错误一"}, {default: slot}),
        h(FormField, {label: "第二个", hint: "提示二", error: "错误二"}, {default: slot}),
      ]),
    }));
    const fields = wrapper.findAll(".form-field");
    expect(fields.length).toBe(2);
    const ids = fields.map((field) => field.find("input").attributes("id"));
    expect(ids[0]).toMatch(/^form-field-/);
    expect(ids[0]).not.toBe(ids[1]);
    fields.forEach((field, index) => {
      expect(field.find("label").attributes("for")).toBe(ids[index]);
      expect(field.find(".form-field__hint").attributes("id")).toBe(`${ids[index]}-hint`);
      expect(field.find(".form-field__error").attributes("id")).toBe(`${ids[index]}-error`);
      expect(field.find("input").attributes("aria-describedby")).toBe(`${ids[index]}-hint ${ids[index]}-error`);
    });
  });

  it("同一 app 内的两个 UiInput 与两个 UiSelect 各自生成不同 id，label[for] 指向自己的控件", () => {
    const wrapper = mount(defineComponent({
      render: () => h("div", [
        h(UiInput, {label: "搜索"}),
        h(UiInput, {label: "替换"}),
        h(UiSelect, {label: "范围"}, {default: () => h("option", {value: "a"}, "A")}),
        h(UiSelect, {label: "排序"}, {default: () => h("option", {value: "b"}, "B")}),
      ]),
    }));
    const controls = [...wrapper.findAll("input"), ...wrapper.findAll("select")];
    const ids = controls.map((control) => control.attributes("id"));
    expect(ids.length).toBe(4);
    expect(new Set(ids).size).toBe(4);
    expect(ids[0]).toMatch(/^ui-input-/);
    expect(ids[2]).toMatch(/^ui-select-/);
    wrapper.findAll("label").forEach((label, index) => {
      expect(label.attributes("for")).toBe(ids[index]);
    });
  });
});
