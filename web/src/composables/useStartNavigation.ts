// 应用级起始面导航（PLAN-DM-035 Task 7；PLAN-DM-039 Task 1 增加一次性进入意图）。
// 无工作区时的三个应用级表面：欢迎页（打开 DST 为唯一主任务）、标准管理、
// 从标准创建图纸集（PLAN-DM-036 编译期占位）。导航是纯应用状态——标准管理
// 不进工作区标签栏，切换表面不创建/关闭任何工作区。
//
// 进入意图只决定“进入标准管理后是否直接打开既有导入对话框”，不复制导入状态：
// 对话框本身、导入请求与错误仍由 `StandardsView` 唯一持有。意图是**一次性**的，
// 回到欢迎页即清除，避免下次从「管理图纸标准」进入时误开对话框。
import {ref} from "vue";
import type {StartSurface} from "../features/standards/types";

/** 进入标准管理的意图：只浏览标准库，或直接打开既有导入对话框。 */
export type StandardsEntryIntent = "browse" | "import-package";

export function useStartNavigation() {
  const surface = ref<StartSurface>("welcome");
  const standardsEntryIntent = ref<StandardsEntryIntent>("browse");
  return {
    surface,
    standardsEntryIntent,
    openStandards(intent: StandardsEntryIntent = "browse"): void {
      standardsEntryIntent.value = intent;
      surface.value = "standards";
    },
    openCreateSheetset(): void {
      surface.value = "create-sheetset";
    },
    goWelcome(): void {
      standardsEntryIntent.value = "browse";
      surface.value = "welcome";
    },
  };
}
