// @vitest-environment happy-dom
import {afterEach, describe, expect, it} from "vitest";
import {mount} from "@vue/test-utils";
import ToastHost from "./ToastHost.vue";
import type {Toast} from "../../composables/useToast";

let wrapper: ReturnType<typeof mount> | undefined;
afterEach(() => { wrapper?.unmount(); wrapper = undefined; });
const failure = (id: number): Toast => ({id, type: "fail", title: `失败 ${id}`, body: "保留恢复信息"});

function mountHost() {
  wrapper = mount(ToastHost, {
    attachTo: document.body,
    props: {toasts: [failure(1), failure(2)]},
    global: {mocks: {$t: (key: string) => key}},
  });
  const host = wrapper.element as HTMLElement;
  // happy-dom 不做几何布局；只替换浏览器提供的内容高度，组件逻辑和焦点仍真实执行。
  Object.defineProperty(host, "scrollHeight", {value: 800, configurable: true});
  host.scrollTop = 20;
  return {view: wrapper, host};
}

describe("ToastHost 阅读位置", () => {
  it("新通知到达时显示列表末尾", async () => {
    const {view, host} = mountHost();
    await view.setProps({toasts: [failure(1), failure(2), failure(3)]});
    expect(host.scrollTop).toBe(800);
  });

  it("关闭末尾通知时不跳转阅读位置", async () => {
    const {view, host} = mountHost();
    await view.setProps({toasts: [failure(1)]});
    expect(host.scrollTop).toBe(20);
  });

  it("用户聚焦既有通知时，新通知不滚走当前焦点", async () => {
    const {view, host} = mountHost();
    const button = view.find("button").element as HTMLButtonElement;
    button.focus();
    await view.setProps({toasts: [failure(1), failure(2), failure(3)]});
    expect(document.activeElement).toBe(button);
    expect(host.scrollTop).toBe(20);
  });
});
