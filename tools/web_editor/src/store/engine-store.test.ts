import { beforeEach, describe, expect, it } from 'vitest';
import { useEngineStore } from './engine-store';

describe('engine-store timeline controls', () => {
  beforeEach(() => {
    const state = useEngineStore.getState();
    state.initialize();
    state.resetRuntime();
    state.clearOutput();
    state.clearTimeline();
  });

  it('appends timeline for line execution and can clear it', () => {
    const state = useEngineStore.getState();

    const run = state.executeSource('1 2 +', 'selection');
    expect(run.ok).toBe(true);

    const withTimeline = useEngineStore.getState();
    expect(withTimeline.timeline.length).toBeGreaterThan(0);

    withTimeline.clearTimeline();
    expect(useEngineStore.getState().timeline).toEqual([]);
  });

  it('resets timeline and stacks for fresh buffer trace', () => {
    const state = useEngineStore.getState();

    state.executeSource('10 20 +', 'selection');
    expect(useEngineStore.getState().dataStack).toEqual([30]);

    const result = state.executeSource(': SQUARE DUP * ; 9 SQUARE', 'buffer', {
      resetTimeline: true,
      resetStacks: true,
    });

    expect(result.ok).toBe(true);

    const next = useEngineStore.getState();
    expect(next.dataStack).toEqual([81]);
    expect(next.timeline.length).toBeGreaterThan(0);
    expect(next.timeline.every((point) => point.sourceLabel === 'buffer')).toBe(true);
    expect(new Set(next.timeline.map((point) => point.runId)).size).toBe(1);
  });

  it('assigns increasing run ids across independent executions', () => {
    const state = useEngineStore.getState();

    state.executeSource('1 2 +', 'selection');
    const first = useEngineStore.getState().timeline.map((point) => point.runId);
    expect(first.length).toBeGreaterThan(0);

    state.executeSource('3 4 +', 'selection');
    const timeline = useEngineStore.getState().timeline;
    const runIds = timeline.map((point) => point.runId);
    const unique = Array.from(new Set(runIds));

    expect(unique.length).toBeGreaterThanOrEqual(2);
    for (let i = 1; i < unique.length; i += 1) {
      expect(unique[i]).toBeGreaterThan(unique[i - 1]);
    }
  });

  it('evaluates watch expressions without mutating runtime state or timeline', () => {
    const state = useEngineStore.getState();
    state.executeSource('5 2 +', 'selection');
    const before = useEngineStore.getState();

    const result = state.evaluateWatchExpression('DUP *');
    expect(result.ok).toBe(true);
    expect(result.top).toBe(49);
    expect(result.stack).toEqual([49]);

    const after = useEngineStore.getState();
    expect(after.dataStack).toEqual(before.dataStack);
    expect(after.timeline.length).toBe(before.timeline.length);
  });

  it('returns evaluation errors for invalid watch expressions', () => {
    const state = useEngineStore.getState();
    const result = state.evaluateWatchExpression('NO_SUCH_WORD');
    expect(result.ok).toBe(false);
    expect(result.error).toContain('Unknown word');
  });

  it('records loop pointer and float stack metadata in timeline points', () => {
    const state = useEngineStore.getState();
    const result = state.executeSource(': LOOPTEST 2 0 DO I LOOP ; LOOPTEST', 'buffer', {
      resetTimeline: true,
      resetStacks: true,
    });
    expect(result.ok).toBe(true);

    const iPoint = useEngineStore
      .getState()
      .timeline.find((point) => point.eventType === 'execute' && point.word === 'I');

    expect(iPoint).toBeDefined();
    expect(iPoint?.loopDepth).toBe(1);
    expect(iPoint?.loopI).toBe(0);
    expect(iPoint?.floatStack).toEqual([]);
  });
});
