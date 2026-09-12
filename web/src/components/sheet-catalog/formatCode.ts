// 图纸目录字段引用的数字格式码（SPEC-DM-012 §4.2/§5.4；PLAN-DM-026 Task 3）。
// 纯字符串变换：只把 `{sheet.number}` 变成 `{sheet.number:0000}` 这类引用文本，
// 不做求值、不接触 DST；求值语义在宿主后端 format_value（§5.4）执行。
/** 图纸目录字段引用的数字格式码（SPEC-DM-012 §5.4）：宽度 = 0 的个数。 */
export const NUMBER_FORMAT_WIDTHS = [2, 3, 4, 5, 6] as const;
export const STRIP_ZEROS_WIDTH = 0;

export function applyNumberFormat(reference: string, width: number): string {
  // 开发态护栏：UI 只传 NUMBER_FORMAT_WIDTHS 与 STRIP_ZEROS_WIDTH，不会触发。
  // 消息用英文（同 useSettings.ts 的“开发态诊断，非界面文案”），否则被 check:i18n
  // 的“web/src 无硬编码中文”门禁拦截。
  if (!Number.isInteger(width) || width < STRIP_ZEROS_WIDTH || width > 16) {
    throw new Error(`Number format width out of range: ${width}`);
  }
  if (!reference.endsWith("}")) {
    throw new Error(`Field reference is not closed: ${reference}`);
  }
  return `${reference.slice(0, -1)}:${"0".repeat(Math.max(width, 1))}}`;
}
