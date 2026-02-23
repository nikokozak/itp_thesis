import { create } from 'zustand';
import { propagateLabelsForSource } from '../analysis/annotations';
import { collectControlFlowDiagnostics } from '../analysis/control-flow';
import {
  analyzeSourceStackEffects,
  createInitialEffectDatabase,
  parseDeclaredEffect,
} from '../analysis/stack-effect';
import { buildCrossReference } from '../analysis/xref';
import type {
  DefinitionAnalysis,
  LabelPropagationResult,
  StackEffect,
  StackEffectDatabase,
  XRefEntry,
} from '../analysis/types';
import type { WordEntry } from '../engine/types';
import { useEngineStore } from './engine-store';
import { useWorkspaceStore } from './workspace-store';
import { buildWorkspaceSourceMap } from '../utils/workspace-source';

interface AnalysisStoreState {
  combinedSource: string;
  sourceMap?: ReturnType<typeof buildWorkspaceSourceMap>;
  effects: StackEffectDatabase;
  analyses: DefinitionAnalysis[];
  labels: LabelPropagationResult[];
  xref: Record<string, XRefEntry>;
  diagnostics: ReturnType<typeof collectControlFlowDiagnostics>;
  selectedWord?: string;
  recompute: () => void;
  setSelectedWord: (word?: string) => void;
}

function fromWordEntry(word: WordEntry): StackEffect | undefined {
  if (word.stackEffect?.inputs || word.stackEffect?.outputs) {
    return {
      inputs: word.stackEffect.inputs?.length ?? 0,
      outputs: word.stackEffect.outputs?.length ?? 0,
      inputLabels: word.stackEffect.inputs,
      outputLabels: word.stackEffect.outputs,
      verified: true,
      opaque: Boolean(word.opaque),
    };
  }

  if (word.type === 'constant' || word.type === 'variable' || word.type === 'value') {
    return {
      inputs: 0,
      outputs: 1,
      verified: true,
      opaque: false,
    };
  }

  if (word.type === 'compiled' && word.sourceTokens) {
    const declared = parseDeclaredEffect(word.sourceTokens.join(' '));
    if (declared) {
      return {
        inputs: declared.inputs.length,
        outputs: declared.outputs.length,
        inputLabels: declared.inputs,
        outputLabels: declared.outputs,
        verified: false,
        opaque: true,
      };
    }
  }

  return undefined;
}

function seedEffectDatabase(dictionary: WordEntry[]): StackEffectDatabase {
  const seed = createInitialEffectDatabase();
  for (const word of dictionary) {
    const effect = fromWordEntry(word);
    if (effect) {
      seed[word.name.toUpperCase()] = effect;
    }
  }
  return seed;
}

export const useAnalysisStore = create<AnalysisStoreState>((set) => ({
  combinedSource: '',
  sourceMap: undefined,
  effects: createInitialEffectDatabase(),
  analyses: [],
  labels: [],
  xref: {},
  diagnostics: [],
  selectedWord: undefined,

  recompute: () => {
    const workspace = useWorkspaceStore.getState();
    const sourceMap = buildWorkspaceSourceMap(workspace.files);
    const dictionary = useEngineStore.getState().dictionary;
    const seedDb = seedEffectDatabase(dictionary);
    for (const external of Object.values(workspace.externalWords)) {
      seedDb[external.word.toUpperCase()] = {
        inputs: external.effect.inputs,
        outputs: external.effect.outputs,
        inputLabels: external.effect.inputLabels,
        outputLabels: external.effect.outputLabels,
        verified: false,
        opaque: false,
      };
    }
    const stackResult = analyzeSourceStackEffects(sourceMap.source, seedDb);
    const labels = propagateLabelsForSource(sourceMap.source, stackResult.effectDb);
    const xref = buildCrossReference(sourceMap.source, stackResult.effectDb, workspace.docsByWordUpper);
    const diagnostics = collectControlFlowDiagnostics(stackResult.definitions);

    set({
      combinedSource: sourceMap.source,
      sourceMap,
      effects: stackResult.effectDb,
      analyses: stackResult.definitions,
      labels,
      xref,
      diagnostics,
    });
  },

  setSelectedWord: (word) => {
    set({ selectedWord: word });
  },
}));
