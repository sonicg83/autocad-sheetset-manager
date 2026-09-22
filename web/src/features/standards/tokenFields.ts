// 令牌编辑器的字段清单（PLAN-DM-038 Task 8 / SPEC-DM-017 §5.3、§6.1）。
//
// 纯函数：把「可见字段 ID 列表」转成字段浏览器条目。字段可见性规则（作用域、组合不能引用
// 组合、DWG 命名只用 subset 系统字段与 sheetset 属性）由 `draftModel` 决定，本模块只负责
// 分组、显示名与示例取样，不重复实现可见性判断。
import {
  SHEET_SYSTEM_FIELDS,
  SUBSET_SYSTEM_FIELDS,
  compositionFields,
  dwgNamingFields,
  samplePropertyValue,
  type DraftDocument,
  type DraftPropertyScope,
} from "./draftModel";

/** 可插入字段：属性令牌用 `property_id`，系统字段令牌用 `system_field`。 */
export interface TokenField {
  id: string;
  system: boolean;
  group: "subset" | "sheet" | "property";
  label: string;
  sample: string;
  /** 受控补零格式（只有 `subset.sequence` 令牌可以携带）。 */
  format?: string;
}

export interface TokenFieldTexts {
  /** 系统字段显示名（键为系统字段名，由语言包提供）。 */
  systemLabels: Record<string, string>;
  /** 属性示例占位值（默认值、枚举首项与映射目标都为空时使用）。 */
  placeholder: string;
  /** `subset.sequence` 令牌的受控补零格式。 */
  sequenceFormat?: string;
}

const SUBSET_GROUP: readonly string[] = SUBSET_SYSTEM_FIELDS;
const SHEET_GROUP: readonly string[] = SHEET_SYSTEM_FIELDS;

function systemField(id: string, texts: TokenFieldTexts): TokenField {
  const field: TokenField = {
    id,
    system: true,
    group: SUBSET_GROUP.includes(id) ? "subset" : "sheet",
    label: texts.systemLabels[id] ?? id,
    sample: id === "subset.sequence" ? "1" : "",
  };
  if (id === "subset.sequence" && texts.sequenceFormat !== undefined) {
    field.format = texts.sequenceFormat;
  }
  return field;
}

function propertyField(
  document: DraftDocument,
  propertyId: string,
  texts: TokenFieldTexts,
): TokenField {
  const property = document.properties.find(item => item.property_id === propertyId);
  return {
    id: propertyId,
    system: false,
    group: "property",
    label: property?.name ?? propertyId,
    sample: property === undefined ? "" : samplePropertyValue(property, texts.placeholder),
  };
}

/** 组合属性的可见字段：作用域过滤 + sheet 组合的两个 Sheet 系统字段。 */
export function compositionTokenFields(
  document: DraftDocument,
  scope: DraftPropertyScope,
  texts: TokenFieldTexts,
): TokenField[] {
  const fields = compositionFields(document, scope).map(id =>
    SHEET_GROUP.includes(id) ? systemField(id, texts) : propertyField(document, id, texts),
  );
  return fields;
}

/** DWG 命名的可见字段：三个 subset 系统字段 + 全部 sheetset 属性。 */
export function dwgNamingTokenFields(
  document: DraftDocument,
  texts: TokenFieldTexts,
): TokenField[] {
  return dwgNamingFields(document).map(id =>
    SUBSET_GROUP.includes(id) ? systemField(id, texts) : propertyField(document, id, texts),
  );
}
