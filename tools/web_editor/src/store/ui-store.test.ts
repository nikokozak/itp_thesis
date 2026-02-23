import { beforeEach, describe, expect, it } from 'vitest';
import { useUiStore } from './ui-store';

describe('ui-store breakpoints', () => {
  beforeEach(() => {
    useUiStore.setState({
      breakpointsByFileId: {},
      watchExpressions: [],
      timelineCursor: 0,
      timelineMode: 'steps',
      memoryViewMode: 'timeline',
    });
  });

  it('toggles breakpoint lines and keeps them sorted', () => {
    const state = useUiStore.getState();
    const fileId = 'file-1';

    state.toggleBreakpointLine(fileId, 10);
    state.toggleBreakpointLine(fileId, 4);
    state.toggleBreakpointLine(fileId, 7);

    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual([4, 7, 10]);

    state.toggleBreakpointLine(fileId, 7);
    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual([4, 10]);
  });

  it('ignores invalid lines and clears breakpoints', () => {
    const state = useUiStore.getState();
    const fileId = 'file-1';

    state.toggleBreakpointLine(fileId, 0);
    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual(undefined);

    state.toggleBreakpointLine(fileId, 3);
    state.toggleBreakpointLine(fileId, 9);
    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual([3, 9]);

    state.clearBreakpointLines(fileId);
    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual(undefined);

    state.toggleBreakpointLine(fileId, 1);
    expect(useUiStore.getState().breakpointsByFileId[fileId]).toEqual([1]);
    state.clearBreakpointLines();
    expect(useUiStore.getState().breakpointsByFileId).toEqual({});
  });

  it('manages persistent watch expressions', () => {
    const state = useUiStore.getState();
    state.addWatchExpression('DUP');
    state.addWatchExpression('   ');
    state.addWatchExpression('I');

    expect(useUiStore.getState().watchExpressions).toEqual(['DUP', 'I']);

    state.updateWatchExpression(1, 'J');
    expect(useUiStore.getState().watchExpressions).toEqual(['DUP', 'J']);

    state.removeWatchExpression(0);
    expect(useUiStore.getState().watchExpressions).toEqual(['J']);
  });

  it('switches memory inspector view mode', () => {
    const state = useUiStore.getState();
    expect(state.memoryViewMode).toBe('timeline');
    state.setMemoryViewMode('live');
    expect(useUiStore.getState().memoryViewMode).toBe('live');
    state.setMemoryViewMode('timeline');
    expect(useUiStore.getState().memoryViewMode).toBe('timeline');
  });
});
