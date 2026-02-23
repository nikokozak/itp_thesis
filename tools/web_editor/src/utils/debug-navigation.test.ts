import { describe, expect, it } from 'vitest';
import { findBreakpointIndex, findCursorLineIndex, findDistinctSourceLineIndex } from './debug-navigation';

describe('findBreakpointIndex', () => {
  const timeline = [
    { eventType: 'input', sourceLine: undefined },
    { eventType: 'execute', sourceLine: 2 },
    { eventType: 'push', sourceLine: 2 },
    { eventType: 'execute', sourceLine: 3 },
    { eventType: 'error', sourceLine: 8 },
  ] as const;

  it('finds the next breakpoint from the start index', () => {
    const breakpoints = new Set([3]);
    expect(findBreakpointIndex(timeline, breakpoints, 0, 'forward')).toBe(3);
  });

  it('skips non execute/error events when searching breakpoints', () => {
    const breakpoints = new Set([2]);
    expect(findBreakpointIndex(timeline, breakpoints, 0, 'forward')).toBe(1);
  });

  it('searches backwards correctly', () => {
    const breakpoints = new Set([2, 3]);
    expect(findBreakpointIndex(timeline, breakpoints, 4, 'backward')).toBe(3);
    expect(findBreakpointIndex(timeline, breakpoints, 2, 'backward')).toBe(1);
  });

  it('returns -1 when no matching breakpoint exists', () => {
    const breakpoints = new Set([99]);
    expect(findBreakpointIndex(timeline, breakpoints, 0, 'forward')).toBe(-1);
  });
});

describe('findDistinctSourceLineIndex', () => {
  const timeline = [
    { sourceLine: 1 },
    { sourceLine: 1 },
    { sourceLine: 2 },
    { sourceLine: 2 },
    { sourceLine: 4 },
  ] as const;

  it('finds the next different source line', () => {
    expect(findDistinctSourceLineIndex(timeline, 0, 'forward')).toBe(2);
    expect(findDistinctSourceLineIndex(timeline, 2, 'forward')).toBe(4);
  });

  it('finds the previous different source line', () => {
    expect(findDistinctSourceLineIndex(timeline, 4, 'backward')).toBe(3);
    expect(findDistinctSourceLineIndex(timeline, 2, 'backward')).toBe(1);
  });

  it('returns -1 when no jump target exists', () => {
    expect(findDistinctSourceLineIndex(timeline, 4, 'forward')).toBe(-1);
    expect(findDistinctSourceLineIndex(timeline, 0, 'backward')).toBe(-1);
  });
});

describe('findCursorLineIndex', () => {
  const timeline = [
    { sourceLine: 1 },
    { sourceLine: 3 },
    { sourceLine: 5 },
    { sourceLine: 3 },
  ] as const;

  it('searches forward from the current cursor first', () => {
    expect(findCursorLineIndex(timeline, 0, 3)).toBe(1);
    expect(findCursorLineIndex(timeline, 1, 3)).toBe(3);
  });

  it('wraps to the beginning when no forward hit exists', () => {
    expect(findCursorLineIndex(timeline, 3, 1)).toBe(0);
  });

  it('returns -1 when the line does not exist', () => {
    expect(findCursorLineIndex(timeline, 2, 99)).toBe(-1);
  });
});
