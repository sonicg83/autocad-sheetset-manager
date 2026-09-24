// 应用级起始面导航（PLAN-DM-035 Task 7；PLAN-DM-039 Task 1 增加一次性进入意图；
// PLAN-DM-036 Task 8 增加创建标准的固定身份）。
// 无工作区时的三个应用级表面：欢迎页（打开 DST 为唯一主任务）、标准管理、
// 从标准创建图纸集。导航是纯应用状态——标准管理不进工作区标签栏，切换表面不创建/关闭
// 任何工作区。
//
// 进入意图只决定“进入标准管理后是否直接打开既有导入对话框”，不复制导入状态：
// 对话框本身、导入请求与错误仍由 `StandardsView` 唯一持有。意图是**一次性**的，
// 回到欢迎页即清除，避免下次从「管理图纸标准」进入时误开对话框。
// 创建意图同理：标准详情「用于创建」固定 `standard_id` 与发布版本后进入向导第二阶段，
// 欢迎页入口不带身份（从第一阶段开始选标准），回到欢迎页即清除。
import {ref} from "vue";
import type {StartSurface, StandardIdentity} from "../features/standards/types";

/** 进入标准管理的意图：只浏览标准库，或直接打开既有导入对话框。 */
export type StandardsEntryIntent = "browse" | "import-package";

export function useStartNavigation() {
  const surface = ref<StartSurface>("welcome");
  const standardsEntryIntent = ref<StandardsEntryIntent>("browse");
  // 创建入口的固定标准身份：null 表示从欢迎页进入（第一阶段自选标准）
  const createSheetsetIdentity = ref<StandardIdentity | null>(null);
  return {
    surface,
    standardsEntryIntent,
    createSheetsetIdentity,
    openStandards(intent: StandardsEntryIntent = "browse"): void {
      standardsEntryIntent.value = intent;
      surface.value = "standards";
    },
    openCreateSheetset(identity: StandardIdentity | null = null): void {
      createSheetsetIdentity.value = identity;
      surface.value = "create-sheetset";
    },
    goWelcome(): void {
      standardsEntryIntent.value = "browse";
      createSheetsetIdentity.value = null;
      surface.value = "welcome";
    },
  };
}
