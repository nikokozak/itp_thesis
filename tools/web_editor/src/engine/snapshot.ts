import type { ForthSnapshot, SerializedWordEntry, WordEntry } from './types';

export function serializeWord(word: WordEntry): SerializedWordEntry {
  return {
    name: word.name,
    upperName: word.upperName,
    immediate: word.immediate,
    type: word.type,
    primitiveName: word.primitiveName,
    instructions: word.instructions ? structuredClone(word.instructions) : undefined,
    sourceTokens: word.sourceTokens ? [...word.sourceTokens] : undefined,
    stackEffect: word.stackEffect ? structuredClone(word.stackEffect) : undefined,
    documentation: word.documentation,
    definitionOrder: word.definitionOrder,
    callCount: word.callCount,
    runtimeValue: word.runtimeValue,
    address: word.address,
    opaque: word.opaque,
  };
}

export function cloneSnapshot(snapshot: ForthSnapshot): ForthSnapshot {
  return {
    dataStack: [...snapshot.dataStack],
    returnStack: [...snapshot.returnStack],
    floatStack: [...snapshot.floatStack],
    loopFrames: structuredClone(snapshot.loopFrames),
    memory: [...snapshot.memory],
    here: snapshot.here,
    base: snapshot.base,
    compileMode: snapshot.compileMode,
    currentWordName: snapshot.currentWordName,
    currentInstructions: snapshot.currentInstructions
      ? structuredClone(snapshot.currentInstructions)
      : undefined,
    currentSourceTokens: snapshot.currentSourceTokens
      ? [...snapshot.currentSourceTokens]
      : undefined,
    pendingControl: snapshot.pendingControl
      ? structuredClone(snapshot.pendingControl)
      : undefined,
    dictionary: snapshot.dictionary.map((entry) => ({
      ...entry,
      instructions: entry.instructions ? structuredClone(entry.instructions) : undefined,
      sourceTokens: entry.sourceTokens ? [...entry.sourceTokens] : undefined,
      stackEffect: entry.stackEffect ? structuredClone(entry.stackEffect) : undefined,
    })),
    sequenceNumber: snapshot.sequenceNumber,
  };
}
