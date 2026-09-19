// 用户/协议字段可包含空格、冒号等字符；ARIA IDREF 以空白分词，不能直接拼接原值。
// encodeURIComponent 提供稳定、无空白且可逆的单段 token，供 id/for/aria-describedby 共用。
export function domIdToken(value: string): string {
  return encodeURIComponent(value);
}
