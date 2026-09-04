// 固定标签栏状态组合式函数：roving tabindex 激活态 + 方向键键盘模型（SPEC-DM-006 §7.2）
import {ref} from "vue";
import type {Ref} from "vue";

export function useShellTabs<T extends string>(ids: readonly T[], initial: T):{active:Ref<T>;select(id:T):void;onKeydown(e:KeyboardEvent):void}{
  // T 约束为字符串原始类型，UnwrapRef<T> 即 T，故此处 as 断言安全
  const active=ref<T>(initial) as Ref<T>;
  function select(id:T){active.value=id}
  function onKeydown(e:KeyboardEvent){
    const i=ids.indexOf(active.value);if(i<0)return;
    let next=-1;
    if(e.key==="ArrowRight")next=(i+1)%ids.length;
    else if(e.key==="ArrowLeft")next=(i-1+ids.length)%ids.length;
    else if(e.key==="Home")next=0;
    else if(e.key==="End")next=ids.length-1;
    if(next>=0){e.preventDefault();active.value=ids[next]}
  }
  return {active,select,onKeydown};
}
