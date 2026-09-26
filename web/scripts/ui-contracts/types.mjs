// UI 静态契约的共享类型与指纹规则（PLAN-DM-029 Task 1）。
//
// `Violation` 是检查器与 CLI 之间唯一的输出结构，字段固定为
// `{rule, file, line, column, message, fingerprint}`；`file` 一律使用相对
// `web/` 的 POSIX 路径，便于在 CI 日志里直接点击定位。
//
// 指纹是棘轮机制的键：它必须包含规则、文件和稳定语义，不能退化为行号，
// 否则任何一次无关的行位移都会让整份例外清单失效。

/** 规则标识（对外契约，例外文件按同一拼写登记）。 */
export const RULE = {
  undefinedCssVariable: "undefined-css-variable",
  circularCssVariable: "circular-css-variable",
  dynamicVariableNotRegistered: "dynamic-variable-not-registered",
  explicitButtonType: "explicit-button-type",
  visibleInputLabel: "visible-input-label",
  iconButtonName: "icon-button-name",
  unicodeStructureIcon: "unicode-structure-icon",
  globalSelectorInComponent: "global-selector-in-component",
  rawHexColor: "raw-hex-color",
  rawVisualValue: "raw-visual-value",
  tableCellVerticalAlign: "table-cell-vertical-align",
  tableCellPadding: "table-cell-padding",
  missingFontAsset: "missing-font-asset",
  remoteFontUrl: "remote-font-url",
  fontBudgetExceeded: "font-budget-exceeded",
  entryStylesheetNotImportOnly: "entry-stylesheet-not-import-only",
  invalidExceptionEntry: "invalid-exception-entry",
  staleException: "stale-exception",
};

/**
 * 不允许登记例外的硬门禁规则（PLAN-DM-029 Task 2 Step 7）。
 *
 * 这四条判定的是资产事实与入口结构：字体文件是否存在、是否引用远程 URL、本地字体合计
 * 是否超预算、样式入口是否仍只是入口。一旦允许它们进白名单，离线约束与体积预算就形同
 * 虚设，因此检查器显式拒绝针对这些规则的例外条目（见 `check-ui-contracts.mjs`）。
 */
export const NON_EXEMPTIBLE_RULES = Object.freeze([
  RULE.missingFontAsset,
  RULE.remoteFontUrl,
  RULE.fontBudgetExceeded,
  RULE.entryStylesheetNotImportOnly,
]);

/**
 * 构造指纹：`<rule>|<file>|<semantic>|<occurrence>`。
 *
 * `occurrence` 是同一文件内同语义违规的 1 基序号，用来区分重复项，使「新增一条
 * 与既有债务完全相同的违规」也能被棘轮拒绝；代价是删掉其中一条时后续序号会前移，
 * 必须同步更新例外登记，这正是「迁移即清退」要求的显式账目。
 */
export function buildFingerprint(rule, file, semantic, occurrence) {
  return [rule, file, semantic, occurrence].join("|");
}

/** 统一的违规构造口，保证字段顺序与类型一致。 */
export function violation({rule, file, line, column, message, semantic, occurrence}) {
  return {
    rule,
    file,
    line,
    column,
    message,
    fingerprint: buildFingerprint(rule, file, semantic, occurrence),
  };
}

/** CLI 输出格式：`file:line:column [rule] message`。 */
export function formatViolation(item) {
  return `${item.file}:${item.line}:${item.column} [${item.rule}] ${item.message}`;
}

/** 稳定排序，保证 CLI 输出与生成基线的顺序可复现。 */
export function compareViolations(left, right) {
  return (
    left.file.localeCompare(right.file, "en") ||
    left.line - right.line ||
    left.column - right.column ||
    left.rule.localeCompare(right.rule, "en") ||
    left.fingerprint.localeCompare(right.fingerprint, "en")
  );
}
