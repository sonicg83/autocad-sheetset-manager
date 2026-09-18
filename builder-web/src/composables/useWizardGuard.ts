// 六步门禁状态机（SPEC-DB-001 §2 / ARCH-DB-001 §7）：
// PROJECT → RULES → SHEETS → TEMPLATES → PREFLIGHT → BUILD。
// 纯函数便于单测；createWizardGuard 提供 Vue 响应式封装。
import {computed, ref, type ComputedRef, type Ref} from "vue";

export const TOTAL_STEPS = 6;
/** 步骤 5（构建前检查）需要用户显式确认；恢复不能自动越过它。 */
export const PREFLIGHT_STEP = 5;

/** completion[i] 表示第 i+1 步是否已完成（下标 0 起）。 */
export type StepCompletion = readonly boolean[];

/** 最大可进入步骤：连续完成前缀之后的下一步，封顶 TOTAL_STEPS。 */
export function maxEnterableStep(completion: StepCompletion): number {
  let step = 1;
  while (step <= TOTAL_STEPS && completion[step - 1]) {
    step += 1;
  }
  return Math.min(step, TOTAL_STEPS);
}

/** 进入第 step 步要求其全部前置步骤已完成；第 1 步总是可进入。 */
export function canEnterStep(step: number, completion: StepCompletion): boolean {
  if (step < 1 || step > TOTAL_STEPS) {
    return false;
  }
  return completion.slice(0, step - 1).every(Boolean);
}

/** 恢复目标步骤：不超过需确认的步骤 5，且回退到最后一个可进入步骤。 */
export function restoreTargetStep(savedStep: number, completion: StepCompletion): number {
  let step = Math.min(Math.max(savedStep, 1), PREFLIGHT_STEP);
  while (step > 1 && !canEnterStep(step, completion)) {
    step -= 1;
  }
  return step;
}

export interface WizardGuard {
  currentStep: Ref<number>;
  maxEnterableStep: ComputedRef<number>;
  canEnter: (step: number) => boolean;
  visit: (step: number) => boolean;
  advance: () => boolean;
  goBack: () => boolean;
}

export function createWizardGuard(options: {
  completion: () => StepCompletion;
  initialStep?: number;
}): WizardGuard {
  const currentStep = ref(options.initialStep ?? 1);
  const canEnter = (step: number) => canEnterStep(step, options.completion());
  const maxStep = computed(() => maxEnterableStep(options.completion()));

  return {
    currentStep,
    maxEnterableStep: maxStep,
    canEnter,
    visit: (step: number) => {
      if (!canEnter(step)) {
        return false;
      }
      currentStep.value = step;
      return true;
    },
    advance: () => {
      const next = currentStep.value + 1;
      if (!canEnter(next)) {
        return false;
      }
      currentStep.value = next;
      return true;
    },
    goBack: () => {
      if (currentStep.value <= 1) {
        return false;
      }
      currentStep.value -= 1;
      return true;
    },
  };
}
