import type { TimelinePoint } from '../store/engine-store';

export interface RuntimeStacks {
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
}

export interface StackHudState {
  source: 'live' | 'timeline';
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  sequenceNumber?: number;
  stepIndex?: number;
  totalSteps?: number;
}

export function resolveStackHudState(
  runtime: RuntimeStacks,
  activePoint: TimelinePoint | undefined,
  followTimeline: boolean,
  selectedIndex: number,
  totalSteps: number
): StackHudState {
  if (!followTimeline || !activePoint) {
    return {
      source: 'live',
      dataStack: runtime.dataStack,
      returnStack: runtime.returnStack,
      floatStack: runtime.floatStack,
    };
  }

  return {
    source: 'timeline',
    dataStack: activePoint.dataStack,
    returnStack: activePoint.returnStack,
    floatStack: activePoint.floatStack,
    sequenceNumber: activePoint.sequenceNumber,
    stepIndex: selectedIndex + 1,
    totalSteps,
  };
}
