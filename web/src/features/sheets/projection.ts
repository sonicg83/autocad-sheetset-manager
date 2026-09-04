// 权威结构投影适配（PLAN-DM-015 任务 1）：把服务端 execution_intent.derived_document
// 映射为前端只读显示副本。图号、派生标题、范围、文件/布局派生名与自定义属性全部取
// 服务端响应，浏览器不重新派生命名；不把显示副本写回 baseWorkspace，新增对象不填造
// 真实 Handle 或 resolved_path。
import type {Preview, Subset, Workspace} from "../../api/contracts";

export function applyDerivedProjection(base: Workspace, preview: Preview): Workspace {
  const derived = preview.execution_intent?.derived_document;
  if (!derived) throw new Error("缺少结构投影，请重新预览");
  const projected: Workspace = JSON.parse(JSON.stringify(base));
  const subsets: Subset[] = derived.subsets.map((derivedSubset, index) => ({
    id: derivedSubset.acsm_id,
    name: derivedSubset.display_name,
    title: derivedSubset.title,
    number_range: derivedSubset.number_range,
    display_name: derivedSubset.display_name,
    order: index + 1,
    sheets: derivedSubset.sheets.map((derivedSheet) => ({
      id: derivedSheet.acsm_id,
      number: derivedSheet.number,
      title: derivedSheet.title,
      custom_properties: {...derivedSheet.custom_properties},
      layout: {...derivedSheet.layout},
    })),
  }));
  projected.sheet_set = {
    ...projected.sheet_set,
    subsets,
    sheet_count: subsets.reduce((count, subset) => count + subset.sheets.length, 0),
    subset_count: subsets.length,
  };
  return projected;
}
