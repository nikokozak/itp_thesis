import { create } from 'zustand';
import { ForthEngine } from '../engine/forth';
import type { ForthEvent, ForthSnapshot, WordEntry } from '../engine/types';

interface ReplResult {
  ok: boolean;
  error?: string;
}

interface WatchEvalResult {
  ok: boolean;
  top?: number;
  stack?: number[];
  error?: string;
}

interface ExecuteSourceOptions {
  resetTimeline?: boolean;
  resetStacks?: boolean;
  clearOutput?: boolean;
}

export interface TimelinePoint {
  sequenceNumber: number;
  here?: number;
  base?: number;
  loopI?: number;
  loopJ?: number;
  loopDepth?: number;
  word?: string;
  callStack?: string[];
  eventType: ForthEvent['type'];
  stack?: ForthEvent['stack'];
  value?: number;
  text?: string;
  definitionName?: string;
  errorMessage?: string;
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  runId: number;
  sourceLabel?: string;
  sourceText?: string;
  sourceLine?: number;
  sourceToken?: string;
  sourceDefinition?: string;
}

interface EngineStoreState {
  engine: ForthEngine;
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  outputLog: string[];
  lastError?: string;
  events: ForthEvent[];
  timeline: TimelinePoint[];
  dictionary: WordEntry[];
  snapshots: ForthSnapshot[];
  futureSnapshots: ForthSnapshot[];
  isInitialized: boolean;
  analysisVersion: number;
  initialize: () => void;
  runReplLine: (line: string) => ReplResult;
  executeSource: (source: string, label?: string, options?: ExecuteSourceOptions) => ReplResult;
  evaluateWatchExpression: (expression: string) => WatchEvalResult;
  undoRuntime: () => boolean;
  redoRuntime: () => boolean;
  clearOutput: () => void;
  clearTimeline: () => void;
  resetRuntime: () => void;
  exportRuntimeSnapshot: () => ForthSnapshot;
  importRuntimeSnapshot: (snapshot: ForthSnapshot) => void;
}

const MAX_EVENTS = 1500;
const MAX_TIMELINE = 2500;
const MAX_SNAPSHOTS = 200;

const engine = new ForthEngine();

function compareTail(actual: number[], expected: number[]): boolean {
  if (expected.length > actual.length) {
    return false;
  }

  const offset = actual.length - expected.length;
  for (let i = 0; i < expected.length; i += 1) {
    if (actual[offset + i] !== expected[i]) {
      return false;
    }
  }
  return true;
}

function parseAssertion(line: string): { code: string; expected: number[] } | undefined {
  const match = line.match(/^TEST\{([\s\S]+)\}TEST$/i);
  if (!match) {
    return undefined;
  }

  const body = match[1].trim();
  const parts = body.split(/\s+->\s+/);
  if (parts.length !== 2) {
    return undefined;
  }

  const expected = parts[1]
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => Number(token))
    .filter((value) => Number.isFinite(value));

  return {
    code: parts[0].trim(),
    expected,
  };
}

export const useEngineStore = create<EngineStoreState>((set, get) => ({
  engine,
  dataStack: [],
  returnStack: [],
  floatStack: [],
  outputLog: [],
  events: [],
  timeline: [],
  dictionary: engine.getLatestWords(),
  snapshots: [],
  futureSnapshots: [],
  isInitialized: false,
  analysisVersion: 0,

  initialize: () => {
    if (get().isInitialized) {
      return;
    }

    let activeInputText = '';
    let activeSourceLabel: string | undefined;
    let activeRunId = 0;

    engine.onEvent((event) => {
      if (event.type === 'input') {
        activeInputText = event.text ?? '';
        activeSourceLabel = event.sourceLabel;
        activeRunId += 1;
      }

      set((state) => {
        const events = [...state.events, event];
        if (events.length > MAX_EVENTS) {
          events.splice(0, events.length - MAX_EVENTS);
        }

        const timeline = [...state.timeline];
        timeline.push({
          sequenceNumber: event.sequenceNumber,
          here: event.here,
          base: event.base,
          loopI: event.loopI,
          loopJ: event.loopJ,
          loopDepth: event.loopDepth,
          word: event.word,
          callStack: event.callStack ? [...event.callStack] : undefined,
          eventType: event.type,
          stack: event.stack,
          value: event.value,
          text: event.text,
          definitionName: event.definition?.name,
          errorMessage: event.error?.message,
          dataStack: [...event.dataStack],
          returnStack: [...event.returnStack],
          floatStack: [...event.floatStack],
          runId: activeRunId,
          sourceLabel: activeSourceLabel,
          sourceText: activeInputText,
          sourceLine: event.sourceLine,
          sourceToken: event.sourceToken,
          sourceDefinition: event.sourceDefinition,
        });
        if (timeline.length > MAX_TIMELINE) {
          timeline.splice(0, timeline.length - MAX_TIMELINE);
        }

        const outputLog = [...state.outputLog];
        if (event.type === 'output' && event.text !== undefined) {
          outputLog.push(event.text);
        }

        const next = {
          events,
          timeline,
          outputLog,
          dataStack: event.dataStack,
          returnStack: event.returnStack,
          floatStack: event.floatStack,
          dictionary: engine.getLatestWords(),
          lastError: event.type === 'error' ? event.error?.message : state.lastError,
          analysisVersion:
            event.type === 'define' || event.type === 'forget'
              ? state.analysisVersion + 1
              : state.analysisVersion,
        };

        return next;
      });
    });

    set({
      isInitialized: true,
      dataStack: engine.getDataStack(),
      returnStack: engine.getReturnStack(),
      dictionary: engine.getLatestWords(),
    });
  },

  runReplLine: (line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      return { ok: true };
    }

    const assertion = parseAssertion(trimmed);
    const state = get();

    if (assertion) {
      const snapshot = state.engine.createSnapshot();
      const result = state.engine.runWithRecovery(assertion.code, { recordInput: true, sourceLabel: 'repl-test' });
      if (!result.ok) {
        state.engine.restoreSnapshot(snapshot);
        return {
          ok: false,
          error: result.error?.message ?? 'Assertion execution failed',
        };
      }

      const actual = state.engine.getDataStack();
      const success = compareTail(actual, assertion.expected);
      state.engine.restoreSnapshot(snapshot);
      state.engine.writeOutput(
        success
          ? 'ok'
          : `ASSERT FAIL expected [${assertion.expected.join(' ')}] got [${actual.join(' ')}]`
      );
      return {
        ok: success,
        error: success ? undefined : 'Assertion failed',
      };
    }

    const before = state.engine.createSnapshot();
    const result = state.engine.runWithRecovery(trimmed, { recordInput: true, sourceLabel: 'repl' });
    if (!result.ok) {
      return {
        ok: false,
        error: result.error?.message ?? 'Execution failed',
      };
    }

    set((prev) => {
      const snapshots = [...prev.snapshots, before];
      if (snapshots.length > MAX_SNAPSHOTS) {
        snapshots.splice(0, snapshots.length - MAX_SNAPSHOTS);
      }
      return {
        snapshots,
        futureSnapshots: [],
        lastError: undefined,
      };
    });

    return { ok: true };
  },

  executeSource: (source, label = 'code', options = {}) => {
    const before = get().engine.createSnapshot();
    if (options.resetStacks) {
      get().engine.clearStacks();
    }
    if (options.clearOutput) {
      set({ outputLog: [] });
    }
    if (options.resetTimeline) {
      set({ timeline: [] });
    }

    const result = get().engine.runWithRecovery(source, { recordInput: true, sourceLabel: label });

    if (!result.ok) {
      get().engine.restoreSnapshot(before);
      return {
        ok: false,
        error: result.error?.message ?? 'Execution failed',
      };
    }

    set((state) => {
      const snapshots = [...state.snapshots, before];
      if (snapshots.length > MAX_SNAPSHOTS) {
        snapshots.splice(0, snapshots.length - MAX_SNAPSHOTS);
      }
      return {
        snapshots,
        futureSnapshots: [],
      };
    });

    return { ok: true };
  },

  evaluateWatchExpression: (expression) => {
    const trimmed = expression.trim();
    if (!trimmed) {
      return {
        ok: false,
        error: 'Expression is empty',
      };
    }

    const state = get();
    const before = state.engine.createSnapshot();
    try {
      state.engine.execute(trimmed, { recordInput: false, sourceLabel: 'watch', silent: true });
      const stack = state.engine.getDataStack();
      return {
        ok: true,
        top: stack.length > 0 ? stack[stack.length - 1] : undefined,
        stack,
      };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : 'Watch evaluation failed',
      };
    } finally {
      state.engine.restoreSnapshot(before);
    }
  },

  undoRuntime: () => {
    const state = get();
    if (state.snapshots.length === 0) {
      return false;
    }

    const snapshots = [...state.snapshots];
    const snapshot = snapshots.pop() as ForthSnapshot;
    const current = state.engine.createSnapshot();
    state.engine.restoreSnapshot(snapshot);

    set((prev) => ({
      snapshots,
      futureSnapshots: [...prev.futureSnapshots, current],
      dataStack: state.engine.getDataStack(),
      returnStack: state.engine.getReturnStack(),
      dictionary: state.engine.getLatestWords(),
      analysisVersion: prev.analysisVersion + 1,
    }));

    return true;
  },

  redoRuntime: () => {
    const state = get();
    if (state.futureSnapshots.length === 0) {
      return false;
    }

    const futureSnapshots = [...state.futureSnapshots];
    const snapshot = futureSnapshots.pop() as ForthSnapshot;
    const current = state.engine.createSnapshot();
    state.engine.restoreSnapshot(snapshot);

    set((prev) => ({
      futureSnapshots,
      snapshots: [...prev.snapshots, current],
      dataStack: state.engine.getDataStack(),
      returnStack: state.engine.getReturnStack(),
      dictionary: state.engine.getLatestWords(),
      analysisVersion: prev.analysisVersion + 1,
    }));

    return true;
  },

  clearOutput: () => {
    set({ outputLog: [] });
  },

  clearTimeline: () => {
    set({ timeline: [] });
  },

  resetRuntime: () => {
    get().engine.clearState();
    set((state) => ({
      dataStack: [],
      returnStack: [],
      floatStack: [],
      outputLog: [],
      lastError: undefined,
      events: [],
      timeline: [],
      dictionary: state.engine.getLatestWords(),
      snapshots: [],
      futureSnapshots: [],
      analysisVersion: state.analysisVersion + 1,
    }));
  },

  exportRuntimeSnapshot: () => {
    return get().engine.createSnapshot();
  },

  importRuntimeSnapshot: (snapshot) => {
    get().engine.restoreSnapshot(snapshot);
    set((state) => ({
      dataStack: state.engine.getDataStack(),
      returnStack: state.engine.getReturnStack(),
      dictionary: state.engine.getLatestWords(),
      analysisVersion: state.analysisVersion + 1,
    }));
  },
}));
