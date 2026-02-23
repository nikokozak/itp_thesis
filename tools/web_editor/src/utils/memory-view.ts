export interface RuntimeMemoryView {
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  here: number;
  base: number;
  loopI?: number;
  loopJ?: number;
  loopDepth: number;
}

export interface TimelineMemoryPoint {
  sequenceNumber: number;
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  here?: number;
  base?: number;
  loopI?: number;
  loopJ?: number;
  loopDepth?: number;
}

export interface ResolvedMemoryView {
  source: 'live' | 'timeline';
  sequenceNumber?: number;
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  here: number;
  base: number;
  loopI?: number;
  loopJ?: number;
  loopDepth: number;
}

export function resolveMemoryView(
  runtime: RuntimeMemoryView,
  activePoint: TimelineMemoryPoint | undefined,
  mode: 'live' | 'timeline'
): ResolvedMemoryView {
  const useTimeline = mode === 'timeline' && activePoint !== undefined;
  if (!useTimeline) {
    return {
      source: 'live',
      dataStack: runtime.dataStack,
      returnStack: runtime.returnStack,
      floatStack: runtime.floatStack,
      here: runtime.here,
      base: runtime.base,
      loopI: runtime.loopI,
      loopJ: runtime.loopJ,
      loopDepth: runtime.loopDepth,
    };
  }

  return {
    source: 'timeline',
    sequenceNumber: activePoint.sequenceNumber,
    dataStack: activePoint.dataStack,
    returnStack: activePoint.returnStack,
    floatStack: activePoint.floatStack,
    here: activePoint.here ?? runtime.here,
    base: activePoint.base ?? runtime.base,
    loopI: activePoint.loopI,
    loopJ: activePoint.loopJ,
    loopDepth: activePoint.loopDepth ?? runtime.loopDepth,
  };
}
