import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

const memoryStorage: Storage = (() => {
  const store = new Map<string, string>();
  return {
    getItem: (name: string) => store.get(name) ?? null,
    setItem: (name: string, value: string) => {
      store.set(name, value);
    },
    removeItem: (name: string) => {
      store.delete(name);
    },
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
})();

const storage = createJSONStorage(() => {
  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage;
  }
  return memoryStorage;
});

export interface EditorFocusRequest {
  fileId: string;
  line: number;
  requestId: number;
}

export type ExecutionTarget = 'local' | 'device';

interface UiStoreState {
  showAnnotations: boolean;
  executionTarget: ExecutionTarget;
  timelineCursor: number;
  timelineMode: 'steps' | 'trace';
  memoryViewMode: 'live' | 'timeline';
  breakpointsByFileId: Record<string, number[]>;
  watchExpressions: string[];
  minimalMode: boolean;
  dictionaryQuery: string;
  dictionaryFilterType: 'all' | 'primitive' | 'compiled' | 'constant' | 'variable' | 'value';
  dictionaryArityFilter?: {
    inputs: number;
    outputs: number;
  };
  editorFocus?: EditorFocusRequest;
  setShowAnnotations: (value: boolean) => void;
  setExecutionTarget: (value: ExecutionTarget) => void;
  setTimelineCursor: (value: number) => void;
  setTimelineMode: (value: UiStoreState['timelineMode']) => void;
  setMemoryViewMode: (value: UiStoreState['memoryViewMode']) => void;
  toggleBreakpointLine: (fileId: string, line: number) => void;
  clearBreakpointLines: (fileId?: string) => void;
  requestEditorFocus: (fileId: string, line: number) => void;
  clearEditorFocus: () => void;
  addWatchExpression: (expression: string) => void;
  updateWatchExpression: (index: number, expression: string) => void;
  removeWatchExpression: (index: number) => void;
  setMinimalMode: (value: boolean) => void;
  setDictionaryQuery: (query: string) => void;
  setDictionaryTypeFilter: (value: UiStoreState['dictionaryFilterType']) => void;
  setDictionaryArityFilter: (value?: { inputs: number; outputs: number }) => void;
}

export const useUiStore = create<UiStoreState>()(
  persist(
    (set) => ({
      showAnnotations: true,
      executionTarget: 'local',
      timelineCursor: 0,
      timelineMode: 'steps',
      memoryViewMode: 'timeline',
      breakpointsByFileId: {},
      watchExpressions: [],
      minimalMode: false,
      dictionaryQuery: '',
      dictionaryFilterType: 'all',
      dictionaryArityFilter: undefined,
      editorFocus: undefined,

      setShowAnnotations: (value) => {
        set({ showAnnotations: value });
      },

      setExecutionTarget: (value) => {
        set({ executionTarget: value });
      },

      setTimelineCursor: (value) => {
        set({ timelineCursor: value });
      },

      setTimelineMode: (value) => {
        set({ timelineMode: value });
      },

      setMemoryViewMode: (value) => {
        set({ memoryViewMode: value });
      },

      toggleBreakpointLine: (fileId, line) => {
        set((state) => {
          if (line < 1) {
            return state;
          }

          const existing = state.breakpointsByFileId[fileId] ?? [];
          const has = existing.includes(line);
          const nextLines = has
            ? existing.filter((value) => value !== line)
            : [...existing, line].sort((a, b) => a - b);

          return {
            breakpointsByFileId: {
              ...state.breakpointsByFileId,
              [fileId]: nextLines,
            },
          };
        });
      },

      clearBreakpointLines: (fileId) => {
        set((state) => {
          if (!fileId) {
            return { breakpointsByFileId: {} };
          }
          if (!state.breakpointsByFileId[fileId]) {
            return state;
          }
          const next = { ...state.breakpointsByFileId };
          delete next[fileId];
          return { breakpointsByFileId: next };
        });
      },

      requestEditorFocus: (fileId, line) => {
        set((state) => ({
          editorFocus: {
            fileId,
            line,
            requestId: (state.editorFocus?.requestId ?? 0) + 1,
          },
        }));
      },

      clearEditorFocus: () => {
        set({ editorFocus: undefined });
      },

      addWatchExpression: (expression) => {
        const trimmed = expression.trim();
        if (!trimmed) {
          return;
        }
        set((state) => ({
          watchExpressions: [...state.watchExpressions, trimmed],
        }));
      },

      updateWatchExpression: (index, expression) => {
        set((state) => {
          if (index < 0 || index >= state.watchExpressions.length) {
            return state;
          }
          const next = [...state.watchExpressions];
          next[index] = expression;
          return { watchExpressions: next };
        });
      },

      removeWatchExpression: (index) => {
        set((state) => ({
          watchExpressions: state.watchExpressions.filter((_, idx) => idx !== index),
        }));
      },

      setMinimalMode: (value) => {
        set({ minimalMode: value });
      },

      setDictionaryQuery: (query) => {
        set({ dictionaryQuery: query });
      },

      setDictionaryTypeFilter: (value) => {
        set({ dictionaryFilterType: value });
      },

      setDictionaryArityFilter: (value) => {
        set({ dictionaryArityFilter: value });
      },
    }),
    {
      name: 'bedrock-web-editor-ui',
      version: 1,
      storage,
      partialize: (state) => ({
        showAnnotations: state.showAnnotations,
        executionTarget: state.executionTarget,
        timelineMode: state.timelineMode,
        memoryViewMode: state.memoryViewMode,
        breakpointsByFileId: state.breakpointsByFileId,
        watchExpressions: state.watchExpressions,
        minimalMode: state.minimalMode,
        dictionaryQuery: state.dictionaryQuery,
        dictionaryFilterType: state.dictionaryFilterType,
        dictionaryArityFilter: state.dictionaryArityFilter,
      }),
    }
  )
);
