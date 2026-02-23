import type { ForthToken } from '../utils/forth-parser';

export type StackName = 'data' | 'return' | 'float';

export interface ForthErrorContext {
  message: string;
  word?: string;
  stackBefore: number[];
}

export interface ForthEvent {
  type: 'execute' | 'push' | 'pop' | 'define' | 'forget' | 'error' | 'input' | 'output';
  sequenceNumber: number;
  here?: number;
  base?: number;
  loopI?: number;
  loopJ?: number;
  loopDepth?: number;
  word?: string;
  callStack?: string[];
  stack?: StackName;
  value?: number;
  text?: string;
  sourceLabel?: string;
  sourceLine?: number;
  sourceToken?: string;
  sourceDefinition?: string;
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  definition?: {
    name: string;
    body: string[];
    stackEffect?: string;
  };
  error?: ForthErrorContext;
}

export interface StackEffectDecl {
  raw?: string;
  inputs?: string[];
  outputs?: string[];
}

export type WordType =
  | 'primitive'
  | 'compiled'
  | 'constant'
  | 'variable'
  | 'value'
  | 'created';

export interface PrimitiveExecutionContext {
  sourceToken?: ForthToken;
}

export interface LoopFrame {
  index: number;
  limit: number;
  startIp: number;
  leaveTarget: number;
}

interface InstructionMeta {
  sourceLine?: number;
  sourceToken?: string;
  sourceDefinition?: string;
}

export type Instruction =
  | ({ kind: 'call'; name: string } & InstructionMeta)
  | ({ kind: 'push'; value: number } & InstructionMeta)
  | ({ kind: 'pushString'; value: string } & InstructionMeta)
  | ({ kind: 'printString'; value: string } & InstructionMeta)
  | ({ kind: 'branchIfZero'; target: number } & InstructionMeta)
  | ({ kind: 'branch'; target: number } & InstructionMeta)
  | ({ kind: 'do'; leaveTarget: number } & InstructionMeta)
  | ({ kind: 'loop'; target: number } & InstructionMeta)
  | ({ kind: 'plusLoop'; target: number } & InstructionMeta)
  | ({ kind: 'leave'; target: number } & InstructionMeta)
  | ({ kind: 'exit' } & InstructionMeta)
  | ({ kind: 'setValue'; name: string } & InstructionMeta);

export interface WordEntry {
  id: number;
  name: string;
  upperName: string;
  immediate: boolean;
  type: WordType;
  primitiveName?: string;
  primitive?: (ctx: PrimitiveExecutionContext) => void;
  instructions?: Instruction[];
  sourceTokens?: string[];
  stackEffect?: StackEffectDecl;
  documentation?: string;
  definitionOrder: number;
  callCount: number;
  runtimeValue?: number;
  address?: number;
  opaque?: boolean;
}

export interface SerializedWordEntry {
  name: string;
  upperName: string;
  immediate: boolean;
  type: WordType;
  primitiveName?: string;
  instructions?: Instruction[];
  sourceTokens?: string[];
  stackEffect?: StackEffectDecl;
  documentation?: string;
  definitionOrder: number;
  callCount: number;
  runtimeValue?: number;
  address?: number;
  opaque?: boolean;
}

export interface ForthSnapshot {
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  loopFrames: LoopFrame[];
  memory: number[];
  here: number;
  base: number;
  compileMode: boolean;
  currentWordName?: string;
  currentInstructions?: Instruction[];
  currentSourceTokens?: string[];
  pendingControl?: ControlFrame[];
  dictionary: SerializedWordEntry[];
  sequenceNumber: number;
}

export interface ControlFrame {
  kind: 'if' | 'else' | 'begin' | 'while' | 'do';
  origin: number;
  branchSlot?: number;
  leaveSlots?: number[];
  beginIndex?: number;
}

export interface EngineExecuteOptions {
  recordInput?: boolean;
  sourceLabel?: string;
  silent?: boolean;
}

export interface ForthRuntimeError extends Error {
  word?: string;
  stackBefore: number[];
}
