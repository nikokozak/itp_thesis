export function clampValue(value: number, min: number, max: number): number {
  if (min > max) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
}

interface SidebarResizeInput {
  containerWidth: number;
  pointerOffsetX: number;
  minSidebarWidth: number;
  maxSidebarWidth: number;
  minMainWidth: number;
  splitterWidth: number;
}

export function computeSidebarWidth(input: SidebarResizeInput): number {
  const { containerWidth, pointerOffsetX, minSidebarWidth, maxSidebarWidth, minMainWidth, splitterWidth } = input;
  const desired = containerWidth - pointerOffsetX - splitterWidth / 2;
  const maxAllowedByContainer = containerWidth - minMainWidth - splitterWidth;
  const effectiveMax = Math.max(minSidebarWidth, Math.min(maxSidebarWidth, maxAllowedByContainer));
  return clampValue(desired, minSidebarWidth, effectiveMax);
}

interface DockResizeInput {
  containerHeight: number;
  pointerOffsetY: number;
  minDockHeight: number;
  maxDockHeight: number;
  minEditorHeight: number;
  splitterHeight: number;
}

export function computeDockHeight(input: DockResizeInput): number {
  const { containerHeight, pointerOffsetY, minDockHeight, maxDockHeight, minEditorHeight, splitterHeight } = input;
  const desired = containerHeight - pointerOffsetY - splitterHeight / 2;
  const maxAllowedByContainer = containerHeight - minEditorHeight - splitterHeight;
  const effectiveMax = Math.max(minDockHeight, Math.min(maxDockHeight, maxAllowedByContainer));
  return clampValue(desired, minDockHeight, effectiveMax);
}
