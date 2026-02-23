import { describe, expect, it } from 'vitest';
import { resolveStackHudState } from './stack-hud';

describe('resolveStackHudState', () => {
  const runtime = {
    dataStack: [1, 2],
    returnStack: [9],
    floatStack: [3],
  };

  it('uses live stacks when not following timeline', () => {
    const state = resolveStackHudState(
      runtime,
      {
        sequenceNumber: 7,
        runId: 1,
        eventType: 'execute',
        dataStack: [99],
        returnStack: [],
        floatStack: [],
      },
      false,
      0,
      1
    );

    expect(state.source).toBe('live');
    expect(state.dataStack).toEqual([1, 2]);
    expect(state.returnStack).toEqual([9]);
    expect(state.floatStack).toEqual([3]);
    expect(state.sequenceNumber).toBeUndefined();
  });

  it('uses timeline stacks and metadata when following timeline', () => {
    const state = resolveStackHudState(
      runtime,
      {
        sequenceNumber: 11,
        runId: 2,
        eventType: 'execute',
        dataStack: [4],
        returnStack: [8],
        floatStack: [16],
      },
      true,
      2,
      10
    );

    expect(state.source).toBe('timeline');
    expect(state.dataStack).toEqual([4]);
    expect(state.returnStack).toEqual([8]);
    expect(state.floatStack).toEqual([16]);
    expect(state.sequenceNumber).toBe(11);
    expect(state.stepIndex).toBe(3);
    expect(state.totalSteps).toBe(10);
  });

  it('falls back to live stacks when timeline follow is on but no point is selected', () => {
    const state = resolveStackHudState(runtime, undefined, true, 0, 0);

    expect(state.source).toBe('live');
    expect(state.dataStack).toEqual([1, 2]);
  });
});
