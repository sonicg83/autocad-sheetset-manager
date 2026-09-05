// 属性页三基准模型（PLAN-DM-016 任务 1 / SPEC-DM-010 §5.2、§5.3）。
// 无副作用纯函数：三基准比较（正式基准/草稿投影/当前输入）、搜索过滤与命令构造。
// 不依赖 Vue DOM；只消费 Workspace 与 ChangeCommand。
import type {ChangeCommand, PropertyDefinition, Workspace} from "../../api/contracts";
import type {PropertyBuffer, PropertySearchMode, ValueKey, ValueStatus} from "./types";

/** 从工作区建立名称与完整自定义属性值的快照副本；不引用原映射，避免直接修改 props。 */
export function createPropertyBuffer(workspace: Workspace): PropertyBuffer {
  return {
    name: workspace.sheet_set.name,
    values: {...workspace.sheet_set.custom_properties},
  };
}

/** 按字段身份读取缓冲值：`@name` 读取名称，`sheetset:<名称>` 读取对应属性值。 */
function readValue(buffer: PropertyBuffer, key: ValueKey): string | undefined {
  if (key === "@name") return buffer.name;
  return buffer.values[key.slice("sheetset:".length)];
}

/**
 * 三基准比较：
 * - 未加入草稿（dirty）：当前输入 ≠ 草稿投影；
 * - 待写入（pending）：草稿投影 ≠ 正式基准；
 * - 失效（invalid）：字段不在可信基准中，此时不制造基准差异（pending 恒为 false），
 *   但输入相对草稿的本地编辑状态仍保留（错误边框优先、修改文字仍保留）。
 * 比较一律使用严格字符串相等：不 trim、不转换类型，空串、空格与前导零原样参与比较。
 */
export function valueStatus(
  base: PropertyBuffer,
  draft: PropertyBuffer,
  input: PropertyBuffer,
  key: ValueKey,
  invalid: ReadonlySet<ValueKey>,
): ValueStatus {
  const dirty = readValue(input, key) !== readValue(draft, key);
  if (invalid.has(key)) return {dirty, pending: false, invalid: true};
  return {dirty, pending: readValue(draft, key) !== readValue(base, key), invalid: false};
}

/**
 * 值搜索过滤：仅遍历当前缓冲中实际存在的自定义属性键（保持读取顺序，不排序、不补造）。
 * 文本包含匹配只使用 toLocaleLowerCase().includes()，英文不区分大小写，不支持正则。
 * changedOnly 时仅保留 dirty 或 pending 的字段，并与搜索结果取交集。
 * 图纸集名称（@name）独立展示，不参与自定义属性搜索。
 */
export function filterValueKeys(
  input: PropertyBuffer,
  query: string,
  mode: PropertySearchMode,
  changedOnly: boolean,
  statusOf: (key: ValueKey) => ValueStatus,
): ValueKey[] {
  const needle = query.toLocaleLowerCase();
  const matched: ValueKey[] = [];
  for (const name of Object.keys(input.values)) {
    const key: ValueKey = `sheetset:${name}`;
    if (changedOnly) {
      const status = statusOf(key);
      if (!status.dirty && !status.pending) continue;
    }
    const nameHit = name.toLocaleLowerCase().includes(needle);
    const valueHit = (input.values[name] ?? "").toLocaleLowerCase().includes(needle);
    const hit = mode === "name" ? nameHit : mode === "value" ? valueHit : nameHit || valueHit;
    if (hit) matched.push(key);
  }
  return matched;
}

/**
 * 构造一次完整提交的 update_sheet_set 命令：名称 + 完整值映射副本。
 * 任一失效字段存在时抛出 PROPERTY_BUFFER_STALE，阻断提交，避免把值写入已删除/不可信字段。
 */
export function buildSheetSetCommand(
  input: PropertyBuffer,
  invalid: ReadonlySet<ValueKey>,
): ChangeCommand {
  if (invalid.size > 0) {
    throw new Error(`PROPERTY_BUFFER_STALE:${[...invalid].join(",")}`);
  }
  return {type: "update_sheet_set", name: input.name, custom_properties: {...input.values}};
}

// —— 字段定义查询与分页（PLAN-DM-016 任务 4 / SPEC-DM-010 §4.1）——
// 字段身份始终是 type + name；同名跨作用域独立，键用 toLocaleLowerCase 归一。

/** 每页固定六条：字段定义以分页控制高度，不采用无限纵向长表。 */
export const DEFINITIONS_PAGE_SIZE = 6;

export type DefinitionScopeFilter = "all" | "sheetset" | "sheet";

/** 字段定义身份键：`${type}:${name.toLocaleLowerCase()}`，同名跨作用域不合并。 */
export function definitionKey(definition: PropertyDefinition): string {
  return `${definition.type}:${definition.name.toLocaleLowerCase()}`;
}

/** 字段定义是否命中当前查询与作用域筛选：字段名/默认值文本包含（英文不区分大小写），保持输入顺序。 */
export function definitionMatches(
  definition: PropertyDefinition,
  query: string,
  scope: DefinitionScopeFilter,
): boolean {
  if (scope !== "all" && definition.type !== scope) return false;
  const needle = query.toLocaleLowerCase();
  if (!needle) return true;
  return definition.name.toLocaleLowerCase().includes(needle)
    || (definition.default_value ?? "").toLocaleLowerCase().includes(needle);
}

/** 过滤字段定义：仅按当前查询与作用域筛选，不排序、不补造、不合并同名定义。 */
export function filterDefinitions(
  definitions: PropertyDefinition[],
  query: string,
  scope: DefinitionScopeFilter,
): PropertyDefinition[] {
  return definitions.filter((definition) => definitionMatches(definition, query, scope));
}
