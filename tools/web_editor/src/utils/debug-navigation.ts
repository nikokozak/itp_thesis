export interface BreakpointTimelinePoint {
  sourceLine?: number;
  eventType: string;
}

export interface LineTimelinePoint {
  sourceLine?: number;
}

function isBreakpointEvent(point: BreakpointTimelinePoint): boolean {
  return point.eventType === 'execute' || point.eventType === 'error';
}

export function findBreakpointIndex(
  timeline: readonly BreakpointTimelinePoint[],
  breakpoints: Set<number>,
  startIndex: number,
  direction: 'forward' | 'backward' = 'forward'
): number {
  if (timeline.length === 0 || breakpoints.size === 0) {
    return -1;
  }

  if (direction === 'forward') {
    const from = Math.max(0, startIndex);
    for (let i = from; i < timeline.length; i += 1) {
      const point = timeline[i];
      if (!isBreakpointEvent(point)) {
        continue;
      }
      if (point.sourceLine !== undefined && breakpoints.has(point.sourceLine)) {
        return i;
      }
    }
    return -1;
  }

  const from = Math.min(timeline.length - 1, startIndex);
  for (let i = from; i >= 0; i -= 1) {
    const point = timeline[i];
    if (!isBreakpointEvent(point)) {
      continue;
    }
    if (point.sourceLine !== undefined && breakpoints.has(point.sourceLine)) {
      return i;
    }
  }

  return -1;
}

export function findDistinctSourceLineIndex(
  timeline: readonly LineTimelinePoint[],
  startIndex: number,
  direction: 'forward' | 'backward'
): number {
  if (timeline.length === 0) {
    return -1;
  }

  const clamped = Math.max(0, Math.min(timeline.length - 1, startIndex));
  const currentLine = timeline[clamped]?.sourceLine;

  if (direction === 'forward') {
    for (let i = clamped + 1; i < timeline.length; i += 1) {
      const line = timeline[i].sourceLine;
      if (line !== undefined && line !== currentLine) {
        return i;
      }
    }
    return -1;
  }

  for (let i = clamped - 1; i >= 0; i -= 1) {
    const line = timeline[i].sourceLine;
    if (line !== undefined && line !== currentLine) {
      return i;
    }
  }

  return -1;
}

export function findCursorLineIndex(
  timeline: readonly LineTimelinePoint[],
  startIndex: number,
  cursorLine: number
): number {
  if (timeline.length === 0) {
    return -1;
  }

  const clamped = Math.max(0, Math.min(timeline.length - 1, startIndex));
  for (let i = clamped + 1; i < timeline.length; i += 1) {
    if (timeline[i].sourceLine === cursorLine) {
      return i;
    }
  }

  for (let i = 0; i <= clamped; i += 1) {
    if (timeline[i].sourceLine === cursorLine) {
      return i;
    }
  }

  return -1;
}
