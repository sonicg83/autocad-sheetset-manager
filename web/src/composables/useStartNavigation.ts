// 应用级起始面导航（PLAN-DM-035 Task 7）。
// 无工作区时的三个应用级表面：欢迎页（打开 DST 为唯一主任务）、标准管理、
// 从标准创建图纸集（PLAN-DM-036 编译期占位）。导航是纯应用状态——标准管理
// 不进工作区标签栏，切换表面不创建/关闭任何工作区。
import {ref} from "vue";
import type {StartSurface} from "../features/standards/types";

export function useStartNavigation() {
  const surface = ref<StartSurface>("welcome");
  return {
    surface,
    openStandards(): void {
      surface.value = "standards";
    },
    openCreateSheetset(): void {
      surface.value = "create-sheetset";
    },
    goWelcome(): void {
      surface.value = "welcome";
    },
  };
}
