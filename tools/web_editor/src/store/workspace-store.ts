import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { StackEffect } from '../analysis/types';

export interface WorkspaceFile {
  id: string;
  name: string;
  content: string;
}

export interface ExternalWordSpec {
  word: string;
  effect: Pick<StackEffect, 'inputs' | 'outputs' | 'inputLabels' | 'outputLabels'>;
}

export interface WorkspaceExportV1 {
  version: 1;
  files: Array<Pick<WorkspaceFile, 'name' | 'content'>>;
  activeFileName?: string;
  docsByWordUpper: Record<string, string>;
  externalWords: ExternalWordSpec[];
}

interface WorkspaceStoreState {
  version: number;
  files: WorkspaceFile[];
  activeFileId: string;
  docsByWordUpper: Record<string, string>;
  externalWords: Record<string, ExternalWordSpec>;
  setActiveFile: (fileId: string) => void;
  setFileContent: (fileId: string, content: string) => void;
  createFile: (name?: string) => string;
  renameFile: (fileId: string, nextName: string) => void;
  deleteFile: (fileId: string) => void;
  moveFile: (fileId: string, direction: 'up' | 'down') => void;
  setDocumentation: (word: string, doc: string) => void;
  upsertExternalWord: (spec: ExternalWordSpec) => void;
  removeExternalWord: (word: string) => void;
  exportWorkspace: () => WorkspaceExportV1;
  importWorkspace: (data: WorkspaceExportV1) => { ok: boolean; error?: string };
  resetWorkspace: () => void;
}

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

function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `w_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;
}

function normalizeWord(word: string): string {
  return word.trim().toUpperCase();
}

const DEFAULT_FILES: WorkspaceFile[] = [
  {
    id: createId(),
    name: 'lib.fth',
    content: `\\\\ Shared helpers.\n\n: SQUARE ( x -- x2 ) DUP * ;\n`,
  },
  {
    id: createId(),
    name: 'main.fth',
    content: `\\\\ Project entrypoint.\n\\\\ Try: 3 4 HYPOTENUSE .S\n\n: HYPOTENUSE ( x y -- dist )\n  SQUARE\n  SWAP\n  SQUARE\n  +\n;\n`,
  },
];

function createInitialState() {
  return {
    version: 1,
    files: DEFAULT_FILES,
    activeFileId: DEFAULT_FILES[1]?.id ?? DEFAULT_FILES[0]!.id,
    docsByWordUpper: {},
    externalWords: {},
  };
}

export const useWorkspaceStore = create<WorkspaceStoreState>()(
  persist(
    (set, get) => ({
      ...createInitialState(),

      setActiveFile: (fileId) => {
        const exists = get().files.some((file) => file.id === fileId);
        if (!exists) {
          return;
        }
        set({ activeFileId: fileId });
      },

      setFileContent: (fileId, content) => {
        set((state) => ({
          version: state.version + 1,
          files: state.files.map((file) => (file.id === fileId ? { ...file, content } : file)),
        }));
      },

      createFile: (name) => {
        const id = createId();
        const baseName = (name ?? 'untitled.fth').trim() || 'untitled.fth';
        const existingNames = new Set(get().files.map((file) => file.name.toLowerCase()));
        let nextName = baseName;
        let suffix = 2;
        while (existingNames.has(nextName.toLowerCase())) {
          const dot = baseName.lastIndexOf('.');
          if (dot > 0) {
            nextName = `${baseName.slice(0, dot)}-${suffix}${baseName.slice(dot)}`;
          } else {
            nextName = `${baseName}-${suffix}`;
          }
          suffix += 1;
        }

        const file: WorkspaceFile = {
          id,
          name: nextName,
          content: `\\\\ ${nextName}\n\n`,
        };

        set((state) => ({
          version: state.version + 1,
          files: [...state.files, file],
          activeFileId: id,
        }));

        return id;
      },

      renameFile: (fileId, nextName) => {
        const trimmed = nextName.trim();
        if (!trimmed) {
          return;
        }

        set((state) => ({
          version: state.version + 1,
          files: state.files.map((file) => (file.id === fileId ? { ...file, name: trimmed } : file)),
        }));
      },

      deleteFile: (fileId) => {
        set((state) => {
          const remaining = state.files.filter((file) => file.id !== fileId);
          if (remaining.length === state.files.length) {
            return state;
          }
          if (remaining.length === 0) {
            return {
              ...createInitialState(),
              version: state.version + 1,
            };
          }
          const nextActive = state.activeFileId === fileId ? remaining[0]!.id : state.activeFileId;
          return {
            version: state.version + 1,
            files: remaining,
            activeFileId: nextActive,
            docsByWordUpper: state.docsByWordUpper,
            externalWords: state.externalWords,
          };
        });
      },

      moveFile: (fileId, direction) => {
        set((state) => {
          const index = state.files.findIndex((file) => file.id === fileId);
          if (index === -1) {
            return state;
          }
          const nextIndex = direction === 'up' ? index - 1 : index + 1;
          if (nextIndex < 0 || nextIndex >= state.files.length) {
            return state;
          }
          const nextFiles = [...state.files];
          const [moved] = nextFiles.splice(index, 1);
          nextFiles.splice(nextIndex, 0, moved);
          return {
            ...state,
            version: state.version + 1,
            files: nextFiles,
          };
        });
      },

      setDocumentation: (word, doc) => {
        const upper = normalizeWord(word);
        if (!upper) {
          return;
        }

        set((state) => ({
          version: state.version + 1,
          docsByWordUpper: {
            ...state.docsByWordUpper,
            [upper]: doc,
          },
        }));
      },

      upsertExternalWord: (spec) => {
        const upper = normalizeWord(spec.word);
        if (!upper) {
          return;
        }

        set((state) => ({
          version: state.version + 1,
          externalWords: {
            ...state.externalWords,
            [upper]: {
              word: upper,
              effect: spec.effect,
            },
          },
        }));
      },

      removeExternalWord: (word) => {
        const upper = normalizeWord(word);
        if (!upper) {
          return;
        }

        set((state) => {
          if (!state.externalWords[upper]) {
            return state;
          }

          const next = { ...state.externalWords };
          delete next[upper];
          return {
            ...state,
            version: state.version + 1,
            externalWords: next,
          };
        });
      },

      exportWorkspace: () => {
        const state = get();
        const active = state.files.find((file) => file.id === state.activeFileId);
        return {
          version: 1,
          files: state.files.map((file) => ({ name: file.name, content: file.content })),
          activeFileName: active?.name,
          docsByWordUpper: state.docsByWordUpper,
          externalWords: Object.values(state.externalWords),
        };
      },

      importWorkspace: (data) => {
        if (!data || data.version !== 1 || !Array.isArray(data.files)) {
          return { ok: false, error: 'Unsupported workspace format' };
        }

        const nextFiles: WorkspaceFile[] = data.files
          .map((file) => {
            const name = typeof file?.name === 'string' ? file.name.trim() : '';
            const content = typeof file?.content === 'string' ? file.content : '';
            if (!name) {
              return undefined;
            }
            return { id: createId(), name, content } satisfies WorkspaceFile;
          })
          .filter(Boolean) as WorkspaceFile[];

        if (nextFiles.length === 0) {
          return { ok: false, error: 'Workspace has no files' };
        }

        const active =
          typeof data.activeFileName === 'string'
            ? nextFiles.find((file) => file.name === data.activeFileName)
            : undefined;
        const externalWords: Record<string, ExternalWordSpec> = {};
        for (const spec of Array.isArray(data.externalWords) ? data.externalWords : []) {
          const upper = normalizeWord(spec.word);
          if (!upper) {
            continue;
          }
          externalWords[upper] = {
            word: upper,
            effect: {
              inputs: Number(spec.effect?.inputs ?? 0),
              outputs: Number(spec.effect?.outputs ?? 0),
              inputLabels: Array.isArray(spec.effect?.inputLabels) ? spec.effect.inputLabels : undefined,
              outputLabels: Array.isArray(spec.effect?.outputLabels) ? spec.effect.outputLabels : undefined,
            },
          };
        }

        set((state) => ({
          version: state.version + 1,
          files: nextFiles,
          activeFileId: active?.id ?? nextFiles[0]!.id,
          docsByWordUpper: typeof data.docsByWordUpper === 'object' && data.docsByWordUpper ? data.docsByWordUpper : {},
          externalWords,
        }));

        return { ok: true };
      },

      resetWorkspace: () => {
        set((state) => ({
          ...createInitialState(),
          version: state.version + 1,
        }));
      },
    }),
    {
      name: 'bedrock-web-editor-workspace',
      version: 1,
      storage,
      partialize: (state) => ({
        files: state.files,
        activeFileId: state.activeFileId,
        docsByWordUpper: state.docsByWordUpper,
        externalWords: state.externalWords,
      }),
    }
  )
);
