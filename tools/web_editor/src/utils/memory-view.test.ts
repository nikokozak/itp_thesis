import { describe, expect, it } from 'vitest';
import { resolveMemoryView } from './memory-view';

describe('resolveMemoryView', () => {
  const runtime = {
    dataStack: [1, 2],
    returnStack: [9],
    floatStack: [3],
    here: 40,
    base: 10,
    loopI: 4,
    loopJ: 2,
    loopDepth: 2,
  };

  it('uses live runtime state in live mode', () => {
    const view = resolveMemoryView(runtime, {
      sequenceNumber: 99,
      dataStack: [7],
      returnStack: [],
      floatStack: [],
      here: 16,
      base: 16,
      loopI: 1,
      loopJ: 0,
      loopDepth: 1,
    }, 'live');

    expect(view.source).toBe('live');
    expect(view.dataStack).toEqual([1, 2]);
    expect(view.base).toBe(10);
    expect(view.sequenceNumber).toBeUndefined();
  });

  it('uses selected timeline point in timeline mode', () => {
    const view = resolveMemoryView(runtime, {
      sequenceNumber: 8,
      dataStack: [5],
      returnStack: [11],
      floatStack: [13],
      here: 80,
      base: 16,
      loopI: 7,
      loopJ: 3,
      loopDepth: 2,
    }, 'timeline');

    expect(view.source).toBe('timeline');
    expect(view.sequenceNumber).toBe(8);
    expect(view.dataStack).toEqual([5]);
    expect(view.returnStack).toEqual([11]);
    expect(view.floatStack).toEqual([13]);
    expect(view.here).toBe(80);
    expect(view.base).toBe(16);
    expect(view.loopI).toBe(7);
    expect(view.loopJ).toBe(3);
    expect(view.loopDepth).toBe(2);
  });

  it('falls back to runtime values when timeline point omits register metadata', () => {
    const view = resolveMemoryView(runtime, {
      sequenceNumber: 21,
      dataStack: [9],
      returnStack: [1],
      floatStack: [],
    }, 'timeline');

    expect(view.source).toBe('timeline');
    expect(view.here).toBe(40);
    expect(view.base).toBe(10);
    expect(view.loopDepth).toBe(2);
  });

  it('falls back to live mode when timeline mode has no selected point', () => {
    const view = resolveMemoryView(runtime, undefined, 'timeline');
    expect(view.source).toBe('live');
    expect(view.dataStack).toEqual([1, 2]);
  });
});
