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

  it("keeps the create-sheetset entry as an explicit not-yet-available surface", () => {
    const navigation = useStartNavigation();
    navigation.openCreateSheetset();
    expect(navigation.surface.value).toBe("create-sheetset");
    navigation.goWelcome();
    expect(navigation.surface.value).toBe("welcome");
  });
});
