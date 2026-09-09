// 日期/数字本地化（PLAN-DM-021 Task 8，I18N-08；Task 5 遗留项落地）。
// 唯一 i18n 实例提供生效语言，Intl 按语言区域格式化；非法输入回退原值（协议数据保持原样）。
import {i18n} from "./index";

const DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {dateStyle: "medium", timeStyle: "medium"};

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(i18n.global.locale.value, DATE_TIME_OPTIONS).format(date);
}
