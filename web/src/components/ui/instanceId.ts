// 未传 `id` 时的兜底 DOM id 生成器（PLAN-DM-029 Task 3 首轮评审修复）。
//
// 计数器必须是**模块作用域**：写在组件 `<script setup>` 里属于实例作用域，每个实例都会从 1
// 重新开始，同一页面上两个未传 `id` 的 `FormField`/`UiInput`/`UiSelect` 会渲染出同一个 DOM
// id —— `label[for]` 会解析到第一个控件（点第二个 label 却聚焦第一个输入），
// `aria-describedby` 的目标也随之歧义。
//
// 按前缀各记一份，id 形如 `form-field-1` / `ui-input-1`，既保证同页唯一，也让调试点到具体原语。
const counters = new Map<string, number>();

/** 生成同页唯一的兜底 id；同一组件实例只应调用一次（结果必须稳定）。 */
export function nextInstanceId(prefix: string): string {
  const next = (counters.get(prefix) ?? 0) + 1;
  counters.set(prefix, next);
  return `${prefix}-${next}`;
}
