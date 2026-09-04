// 权威结构投影适配（PLAN-DM-015 任务 1）：把服务端 execution_intent.derived_document
// 映射为前端只读显示副本。图号、派生标题、范围、文件/布局派生名与自定义属性全部取
// 服务端响应，浏览器不重新派生命名；不把显示副本写回 baseWorkspace，新增对象不填造
// 真实 Handle 或 resolved_path。
import type {ChangeCommand, Preview, Subset, Workspace} from "../../api/contracts";

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

// 混合批次显示合成（任务 5）：结构派生文档只反映结构变化、不含属性值编辑合成，
// 命令簿中的元数据命令（update_sheet_properties/update_sheet_set/属性定义增删）叠加到
// 派生结果显示，避免既有图纸的属性值编辑被回退；只叠加不写入 base、不称已保存。
export function applyCommandOverlay(projected: Workspace, commands: ChangeCommand[]): Workspace {
  const result: Workspace = JSON.parse(JSON.stringify(projected));
  for (const command of commands) {
    switch (command.type) {
      case "update_sheet_properties": {
        const sheet = result.sheet_set.subsets.flatMap((subset) => subset.sheets).find((item) => item.id === command.sheet_id);
        if (sheet) sheet.custom_properties = {...command.custom_properties};
        break;
      }
      case "update_sheet_set":
        if (command.name !== undefined && command.name !== null) result.sheet_set.name = command.name;
        if (command.custom_properties !== undefined && command.custom_properties !== null) {
          result.sheet_set.custom_properties = {...command.custom_properties};
        }
        break;
      case "add_custom_property":
        if (!result.sheet_set.property_definitions.some(
          (item) => item.type === command.property_type && item.name.toLocaleLowerCase() === command.name.toLocaleLowerCase(),
        )) {
          result.sheet_set.property_definitions.push({type: command.property_type, name: command.name, default_value: command.default_value});
        }
        break;
      case "delete_custom_property":
        result.sheet_set.property_definitions = result.sheet_set.property_definitions.filter(
          (item) => !(item.type === command.property_type && item.name.toLocaleLowerCase() === command.name.toLocaleLowerCase()),
        );
        break;
    }
  }
  return result;
}
