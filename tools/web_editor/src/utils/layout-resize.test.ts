import { describe, expect, it } from 'vitest';
import { clampValue, computeDockHeight, computeSidebarWidth } from './layout-resize';

describe('layout resize math', () => {
  it('clamps values in range', () => {
    expect(clampValue(5, 0, 10)).toBe(5);
    expect(clampValue(-1, 0, 10)).toBe(0);
    expect(clampValue(12, 0, 10)).toBe(10);
  });

  it('computes sidebar width with container and min main constraints', () => {
    const width = computeSidebarWidth({
      containerWidth: 1200,
      pointerOffsetX: 900,
      minSidebarWidth: 280,
      maxSidebarWidth: 520,
      minMainWidth: 420,
      splitterWidth: 8,
    });
    expect(width).toBe(296);

    const clampedLarge = computeSidebarWidth({
      containerWidth: 900,
      pointerOffsetX: 100,
      minSidebarWidth: 280,
      maxSidebarWidth: 520,
      minMainWidth: 420,
      splitterWidth: 8,
    });
    expect(clampedLarge).toBe(472);
  });

  it('computes dock height with container and min editor constraints', () => {
    const height = computeDockHeight({
      containerHeight: 700,
      pointerOffsetY: 500,
      minDockHeight: 120,
      maxDockHeight: 420,
      minEditorHeight: 180,
      splitterHeight: 8,
    });
    expect(height).toBe(196);

    const clampedSmall = computeDockHeight({
      containerHeight: 320,
      pointerOffsetY: 310,
      minDockHeight: 120,
      maxDockHeight: 420,
      minEditorHeight: 180,
      splitterHeight: 8,
    });
    expect(clampedSmall).toBe(120);
  });
});
