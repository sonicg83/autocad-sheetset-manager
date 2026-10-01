/** 按读屏定位优先级合并控件描述 ID，并移除空项及重复项。 */
export function mergeDescriptionIds(
  errorId?: string,
  hintId?: string,
  sharedIds?: string,
): string | undefined {
  const orderedIds = [errorId, hintId, sharedIds]
    .flatMap((value) => value?.split(/\s+/) ?? [])
    .filter(Boolean);
  const uniqueIds = [...new Set(orderedIds)];
  return uniqueIds.length > 0 ? uniqueIds.join(" ") : undefined;
}
