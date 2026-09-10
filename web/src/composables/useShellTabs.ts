// 标签栏状态组合式函数：roving tabindex 激活态 + 方向键键盘模型（SPEC-DM-006 §7.2）。
// PLAN-DM-020 Task 10：标签列表可动态变化（扩展页面追加/移除）——固定列表直接传数组，
// 动态列表传 ComputedRef；激活项被移除时安全校正回 fallback（核心首个标签），方向键
// 始终在当前列表内循环。
import {computed,isRef,ref,watch} from "vue";
import type {Ref} from "vue";

// 标签描述符：核心标签与扩展页面共用的标签栏视图模型；label 为已本地化文本
//（由 App 经宿主 i18n 渲染，扩展标签取清单 name_key 的译文），number 仅核心标签使用
export interface TabDescriptor{id:string;label:string;number?:string;disabled?:boolean;source:"core"|"extension"}

export function useShellTabs<T extends string>(ids:readonly T[]|Ref<readonly T[]>,initial:T,fallback:T=initial):{active:Ref<T>;select(id:T):void;onKeydown(e:KeyboardEvent):void}{
  const source=computed<readonly T[]>(()=>isRef(ids)?ids.value:ids);
  // T 约束为字符串原始类型，UnwrapRef<T> 即 T，故此处 as 断言安全
  const active=ref<T>(initial) as Ref<T>;
  // 动态列表安全校正：激活标签被移除（如停用当前扩展页）时回退到 fallback，
  // 绝不停留在列表中不存在的激活项上
  watch(source,value=>{if(!value.includes(active.value))active.value=fallback});
  function select(id:T){if(source.value.includes(id))active.value=id}
  function onKeydown(e:KeyboardEvent){
    const current=source.value;
    const i=current.indexOf(active.value);if(i<0)return;
    let next=-1;
    if(e.key==="ArrowRight")next=(i+1)%current.length;
    else if(e.key==="ArrowLeft")next=(i-1+current.length)%current.length;
    else if(e.key==="Home")next=0;
    else if(e.key==="End")next=current.length-1;
    if(next>=0){e.preventDefault();active.value=current[next]}
  }
  return {active,select,onKeydown};
}
