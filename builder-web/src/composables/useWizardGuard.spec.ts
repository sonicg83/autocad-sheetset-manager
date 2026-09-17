// 门禁状态机单元测试（PLAN-DB-001 Task 5；SPEC-DB-001 §2 前置门禁与恢复语义）：
// 未完成前置步骤不能进入后续步骤；已完成步骤可回访；恢复回到最后一个可进入步骤
// 且不能自动越过需用户确认的步骤 5。
import {describe, expect, it} from "vitest";
import {
  canEnterStep,
  createWizardGuard,
  maxEnterableStep,
  restoreTargetStep,
} from "./useWizardGuard";

type Completion = boolean[];

const NONE: Completion = [false, false, false, false, false, false, false];
const STEP1: Completion = [true, false, false, false, false, false, false];
const STEP1234: Completion = [true, true, true, true, false, false, false];
const ALL: Completion = [true, true, true, true, true, true, true];
// 第 1、3、4 步完成但第 2 步有缺口：
const GAP2: Completion = [true, false, true, true, false, false, false];

describe("maxEnterableStep", () => {
  it("无完成步骤时最大可进入步骤为 1", () => {
    expect(maxEnterableStep(NONE)).toBe(1);
  });

  it("前置全部完成时最大可进入步骤为 7", () => {
    expect(maxEnterableStep(ALL)).toBe(7);
  });

  it("完成到第 4 步时最大可进入步骤为 5", () => {
    expect(maxEnterableStep(STEP1234)).toBe(5);
  });

  it("中间缺口阻断推进，不越过未完成步骤", () => {
    expect(maxEnterableStep(GAP2)).toBe(2);
  });
});

describe("canEnterStep", () => {
  it("第 1 步总是可进入", () => {
    expect(canEnterStep(1, NONE)).toBe(true);
  });

  it("前置未完成时不能进入后续步骤", () => {
    expect(canEnterStep(2, NONE)).toBe(false);
    expect(canEnterStep(3, STEP1)).toBe(false);
    expect(canEnterStep(6, STEP1234)).toBe(false);
  });

  it("前置全部完成后开放后续步骤", () => {
    expect(canEnterStep(5, STEP1234)).toBe(true);
    expect(canEnterStep(7, ALL)).toBe(true);
  });

  it("已完成步骤可回访", () => {
    expect(canEnterStep(1, STEP1234)).toBe(true);
    expect(canEnterStep(3, STEP1234)).toBe(true);
    expect(canEnterStep(4, STEP1234)).toBe(true);
  });
});

describe("restoreTargetStep", () => {
  it("恢复不能自动越过需用户确认的步骤 5", () => {
    expect(restoreTargetStep(7, ALL)).toBe(5);
    expect(restoreTargetStep(6, ALL)).toBe(5);
  });

  it("回到保存时的最后可进入步骤", () => {
    expect(restoreTargetStep(4, STEP1234)).toBe(4);
    expect(restoreTargetStep(2, STEP1)).toBe(2);
  });

  it("保存步骤不可进入时回退到最后可进入步骤", () => {
    expect(restoreTargetStep(4, GAP2)).toBe(2);
    expect(restoreTargetStep(3, NONE)).toBe(1);
  });

  it("未初始化草稿恢复到第 1 步", () => {
    expect(restoreTargetStep(1, NONE)).toBe(1);
  });
});

describe("createWizardGuard", () => {
  it("visit 拒绝未开放的步骤，不改变当前步骤", () => {
    let completion: Completion = [...NONE];
    const guard = createWizardGuard({completion: () => completion});
    expect(guard.visit(3)).toBe(false);
    expect(guard.currentStep.value).toBe(1);
    completion = [...STEP1];
    expect(guard.visit(2)).toBe(true);
    expect(guard.currentStep.value).toBe(2);
  });

  it("已完成步骤可回访", () => {
    const guard = createWizardGuard({completion: () => STEP1234, initialStep: 5});
    expect(guard.visit(2)).toBe(true);
    expect(guard.currentStep.value).toBe(2);
  });

  it("advance 只在当前步骤完成后推进", () => {
    let completion: Completion = [...NONE];
    const guard = createWizardGuard({completion: () => completion});
    expect(guard.advance()).toBe(false);
    expect(guard.currentStep.value).toBe(1);
    completion = [...STEP1];
    expect(guard.advance()).toBe(true);
    expect(guard.currentStep.value).toBe(2);
  });

  it("goBack 返回上一步，第 1 步不再后退", () => {
    const guard = createWizardGuard({completion: () => STEP1234, initialStep: 4});
    expect(guard.goBack()).toBe(true);
    expect(guard.currentStep.value).toBe(3);
    const first = createWizardGuard({completion: () => STEP1234, initialStep: 1});
    expect(first.goBack()).toBe(false);
    expect(first.currentStep.value).toBe(1);
  });
});
