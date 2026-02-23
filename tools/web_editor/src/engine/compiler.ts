import type { ControlFrame, Instruction } from './types';

interface CompileMeta {
  sourceLine?: number;
  sourceToken?: string;
  sourceDefinition?: string;
}

export function compileCall(instructions: Instruction[], name: string, meta: CompileMeta = {}): void {
  instructions.push({ kind: 'call', name, ...meta });
}

export function compileLiteral(instructions: Instruction[], value: number, meta: CompileMeta = {}): void {
  instructions.push({ kind: 'push', value, ...meta });
}

export function compileStringLiteral(instructions: Instruction[], value: string, meta: CompileMeta = {}): void {
  instructions.push({ kind: 'pushString', value, ...meta });
}

export function compileDotQuote(instructions: Instruction[], value: string, meta: CompileMeta = {}): void {
  instructions.push({ kind: 'printString', value, ...meta });
}

export function patchTarget(instructions: Instruction[], index: number, target: number): void {
  const instruction = instructions[index];
  if (!instruction) {
    throw new Error(`Cannot patch missing instruction at index ${index}`);
  }

  if (instruction.kind === 'branchIfZero' || instruction.kind === 'branch') {
    instruction.target = target;
    return;
  }

  if (instruction.kind === 'leave') {
    instruction.target = target;
    return;
  }

  if (instruction.kind === 'do') {
    instruction.leaveTarget = target;
    return;
  }

  throw new Error(`Instruction at index ${index} does not support target patching`);
}

export function findLatestControl(controlStack: ControlFrame[], kinds: ControlFrame['kind'][]): number {
  for (let i = controlStack.length - 1; i >= 0; i -= 1) {
    if (kinds.includes(controlStack[i].kind)) {
      return i;
    }
  }
  return -1;
}
