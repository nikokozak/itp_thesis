import type { ForthToken } from '../utils/forth-parser';

export interface StackEffect {
  inputs: number;
  outputs: number;
  inputLabels?: string[];
  outputLabels?: string[];
  verified: boolean;
  opaque: boolean;
}

export interface DefinitionStep {
  token: ForthToken;
  depthBefore: number;
  depthAfter: number;
  minDepth: number;
  consumed: number;
  produced: number;
  opaque?: boolean;
}

export interface DefinitionAnalysis {
  name: string;
  startLine: number;
  endLine: number;
  declaredEffect?: string;
  effect: StackEffect;
  steps: DefinitionStep[];
  errors: string[];
  warnings: string[];
  source: string;
  opaqueTokens: string[];
}

export interface StackEffectDatabase {
  [wordUpper: string]: StackEffect;
}

export interface LabelStep {
  token: ForthToken;
  before: string[];
  after: string[];
}

export interface LabelPropagationResult {
  word: string;
  startLine: number;
  endLine: number;
  steps: LabelStep[];
  finalLabels: string[];
  tempNames: Record<string, string>;
}

export interface XRefEntry {
  word: string;
  callers: string[];
  callees: string[];
  definedAt: number;
  documentation?: string;
  stackEffect?: StackEffect;
  source?: string;
  declaredEffect?: string;
}
