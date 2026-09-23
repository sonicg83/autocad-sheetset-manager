// 应用级起始面导航（PLAN-DM-035 Task 7）：欢迎页/标准管理/创建图纸集三面切换。
// 导航是纯状态：不创建工作区、不触碰工作区标签栏——标准管理是无工作区时的应用级页面。
import {describe, expect, it} from "vitest";
import {useStartNavigation} from "./useStartNavigation";

describe("useStartNavigation", () => {
  it("returns from standards without creating a workspace", () => {
    const navigation = useStartNavigation();
    expect(navigation.surface.value).toBe("welcome");
    navigation.openStandards();
    expect(navigation.surface.value).toBe("standards");
    navigation.goWelcome();
    expect(navigation.surface.value).toBe("welcome");
  });

  // PLAN-DM-039 Task 1：标准管理入口携带一次性意图——欢迎页「导入标准包」要直接打开既有
  // 导入对话框，而「管理图纸标准」只进入标准库。意图随回到欢迎页清除，避免下次进入误开对话框。
  it("records and clears the one-shot standards entry intent", () => {
    const navigation = useStartNavigation();
    navigation.openStandards("import-package");
    expect(navigation.surface.value).toBe("standards");
    expect(navigation.standardsEntryIntent.value).toBe("import-package");
    navigation.goWelcome();
    expect(navigation.surface.value).toBe("welcome");
    expect(navigation.standardsEntryIntent.value).toBe("browse");
  });

  it("keeps the create-sheetset entry as an explicit not-yet-available surface", () => {
    const navigation = useStartNavigation();
    navigation.openCreateSheetset();
    expect(navigation.surface.value).toBe("create-sheetset");
    navigation.goWelcome();
    expect(navigation.surface.value).toBe("welcome");
  });
});
