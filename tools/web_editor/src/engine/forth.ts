import {
  compileCall,
  compileDotQuote,
  compileLiteral,
  compileStringLiteral,
  findLatestControl,
  patchTarget,
} from './compiler';
import { registerCorePrimitives } from './primitives';
import { cloneSnapshot, serializeWord } from './snapshot';
import type {
  ControlFrame,
  EngineExecuteOptions,
  ForthEvent,
  ForthRuntimeError,
  ForthSnapshot,
  Instruction,
  LoopFrame,
  StackEffectDecl,
  WordEntry,
  WordType,
} from './types';
import { tokenTextUpper, tokenizeForth } from '../utils/forth-parser';

interface PendingAction {
  kind: 'definitionName' | 'constantName' | 'variableName' | 'valueName' | 'toTarget' | 'tick' | 'see' | 'forget';
  value?: number;
}

export interface ForthEngineOptions {
  memoryBytes?: number;
}

interface ExecuteContext {
  activeWord?: string;
  sourceTokenText?: string;
  sourceLine?: number;
  sourceDefinition?: string;
}

function normalizeWordName(name: string): string {
  return name.toUpperCase();
}

function clampToCell(value: number): number {
  return value | 0;
}

function makeRuntimeError(message: string, stackBefore: number[], word?: string): ForthRuntimeError {
  const error = new Error(message) as ForthRuntimeError;
  error.stackBefore = [...stackBefore];
  error.word = word;
  return error;
}

export class ForthEngine {
  private dataStack: number[] = [];
  private returnStack: number[] = [];
  private floatStack: number[] = [];
  private loopFrames: LoopFrame[] = [];

  private memory: Int32Array;
  private memoryBytes: Uint8Array;
  private here = 0;

  private base = 10;
  private compileMode = false;

  private currentWordName?: string;
  private currentInstructions: Instruction[] = [];
  private currentSourceTokens: string[] = [];
  private controlStack: ControlFrame[] = [];

  private pendingAction?: PendingAction;

  private sequenceNumber = 0;
  private executionStack: string[] = [];
  private suppressedEventsDepth = 0;
  private listeners = new Set<(event: ForthEvent) => void>();

  private dictionaryByName = new Map<string, WordEntry[]>();
  private allWords: WordEntry[] = [];
  private builtins: WordEntry[] = [];
  private primitiveRegistry = new Map<string, WordEntry['primitive']>();
  private definitionOrder = 0;

  constructor(options: ForthEngineOptions = {}) {
    const memoryBytes = options.memoryBytes ?? 64 * 1024;
    this.memory = new Int32Array(memoryBytes / 4);
    this.memoryBytes = new Uint8Array(this.memory.buffer);
    registerCorePrimitives(this);
    this.builtins = this.getLatestWords().map((word) => ({ ...word }));
  }

  onEvent(listener: (event: ForthEvent) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  clearState(): void {
    this.dataStack = [];
    this.returnStack = [];
    this.floatStack = [];
    this.loopFrames = [];
    this.memory.fill(0);
    this.here = 0;
    this.base = 10;
    this.compileMode = false;
    this.currentWordName = undefined;
    this.currentInstructions = [];
    this.currentSourceTokens = [];
    this.controlStack = [];
    this.pendingAction = undefined;
    this.executionStack = [];
    this.suppressedEventsDepth = 0;

    this.dictionaryByName.clear();
    this.allWords = [];
    this.definitionOrder = 0;

    for (const builtin of this.builtins) {
      this.addWord({ ...builtin });
    }
  }

  execute(source: string, options: EngineExecuteOptions = {}): void {
    const silent = options.silent ?? false;
    if (silent) {
      this.suppressedEventsDepth += 1;
    }

    try {
      if (options.recordInput ?? true) {
        this.emitEvent({
          type: 'input',
          text: source,
          sourceLabel: options.sourceLabel,
        });
      }

      const tokens = tokenizeForth(source);
      const context: ExecuteContext = {
        sourceDefinition: options.sourceLabel,
      };

      for (const token of tokens) {
        context.sourceTokenText = token.text;
        context.sourceLine = token.line;
        this.handleToken(token.text, token.kind, token.value, token.line, context);
      }
    } finally {
      if (silent) {
        this.suppressedEventsDepth = Math.max(0, this.suppressedEventsDepth - 1);
      }
    }
  }

  executeWordByName(name: string, context: ExecuteContext = {}): void {
    const word = this.findWord(name);
    if (!word) {
      throw makeRuntimeError(`Unknown word: ${name}`, this.dataStack, context.activeWord);
    }

    if (this.applyWordRuntime(word)) {
      this.executionStack.push(word.name);
      try {
        word.callCount += 1;
        this.emitEvent({
          type: 'execute',
          word: word.name,
          sourceLine: context.sourceLine,
          sourceToken: context.sourceTokenText,
          sourceDefinition: context.sourceDefinition,
        });
      } finally {
        this.executionStack.pop();
      }
      return;
    }

    const previousWord = context.activeWord;
    context.activeWord = word.name;
    this.executionStack.push(word.name);

    try {
      if (word.type === 'primitive') {
        if (!word.primitive) {
          throw makeRuntimeError(`Primitive missing implementation: ${word.name}`, this.dataStack, word.name);
        }
        word.primitive({ sourceToken: undefined });
      } else {
        this.runCompiledWord(word, context);
      }
      word.callCount += 1;
      this.emitEvent({
        type: 'execute',
        word: word.name,
        sourceLine: context.sourceLine,
        sourceToken: context.sourceTokenText,
        sourceDefinition: context.sourceDefinition,
      });
    } finally {
      this.executionStack.pop();
      context.activeWord = previousWord;
    }
  }

  private runCompiledWord(word: WordEntry, context: ExecuteContext): void {
    if (!word.instructions) {
      return;
    }

    let ip = 0;
    while (ip < word.instructions.length) {
      const instruction = word.instructions[ip];
      const previousSourceLine = context.sourceLine;
      const previousSourceToken = context.sourceTokenText;
      const previousSourceDefinition = context.sourceDefinition;

      context.sourceLine = instruction.sourceLine;
      context.sourceTokenText = instruction.sourceToken;
      context.sourceDefinition = instruction.sourceDefinition ?? word.name;

      switch (instruction.kind) {
        case 'call': {
          this.executeWordByName(instruction.name, context);
          ip += 1;
          break;
        }
        case 'push': {
          this.pushData(instruction.value);
          ip += 1;
          break;
        }
        case 'pushString': {
          const { addr, len } = this.storeString(instruction.value);
          this.pushData(addr);
          this.pushData(len);
          ip += 1;
          break;
        }
        case 'printString': {
          this.writeOutput(instruction.value);
          ip += 1;
          break;
        }
        case 'branchIfZero': {
          const flag = this.popData(context.activeWord);
          ip = flag === 0 ? instruction.target : ip + 1;
          break;
        }
        case 'branch': {
          ip = instruction.target;
          break;
        }
        case 'do': {
          const start = this.popData(context.activeWord);
          const limit = this.popData(context.activeWord);

          if (start === limit) {
            ip = instruction.leaveTarget;
            break;
          }

          this.loopFrames.push({
            index: start,
            limit,
            startIp: ip + 1,
            leaveTarget: instruction.leaveTarget,
          });
          ip += 1;
          break;
        }
        case 'loop': {
          const frame = this.peekLoopFrame(context.activeWord);
          frame.index += 1;
          if (frame.index === frame.limit) {
            this.loopFrames.pop();
            ip += 1;
          } else {
            ip = instruction.target;
          }
          break;
        }
        case 'plusLoop': {
          const step = this.popData(context.activeWord);
          const frame = this.peekLoopFrame(context.activeWord);
          const next = frame.index + step;
          const crossed = step >= 0 ? next >= frame.limit : next < frame.limit;
          frame.index = next;
          if (crossed) {
            this.loopFrames.pop();
            ip += 1;
          } else {
            ip = instruction.target;
          }
          break;
        }
        case 'leave': {
          if (this.loopFrames.length > 0) {
            this.loopFrames.pop();
          }
          ip = instruction.target;
          break;
        }
        case 'setValue': {
          const value = this.popData(context.activeWord);
          this.setValueWord(instruction.name, value);
          ip += 1;
          break;
        }
        case 'exit': {
          return;
        }
        default: {
          ip += 1;
          break;
        }
      }

      context.sourceLine = previousSourceLine;
      context.sourceTokenText = previousSourceToken;
      context.sourceDefinition = previousSourceDefinition;
    }
  }

  private peekLoopFrame(word?: string): LoopFrame {
    const frame = this.loopFrames[this.loopFrames.length - 1];
    if (!frame) {
      throw makeRuntimeError('Loop stack underflow', this.dataStack, word);
    }
    return frame;
  }

  private handleToken(
    rawText: string,
    tokenKind: 'word' | 'number' | 'sQuote' | 'dotQuote',
    stringValue: string | undefined,
    tokenLine: number,
    context: ExecuteContext
  ): void {
    if (this.pendingAction) {
      if (tokenKind !== 'word') {
        throw makeRuntimeError(
          `Expected word token after ${this.pendingAction.kind}`,
          this.dataStack,
          context.activeWord
        );
      }
      this.consumePendingAction(rawText, context);
      return;
    }

    if (tokenKind === 'sQuote') {
      if (!stringValue) {
        return;
      }
      if (this.compileMode) {
        this.currentSourceTokens.push(`S" ${stringValue}"`);
        compileStringLiteral(this.currentInstructions, stringValue, this.currentCompileMeta(context, rawText));
      } else {
        const { addr, len } = this.storeString(stringValue);
        this.pushData(addr);
        this.pushData(len);
      }
      return;
    }

    if (tokenKind === 'dotQuote') {
      if (!stringValue) {
        return;
      }
      if (this.compileMode) {
        this.currentSourceTokens.push(`." ${stringValue}"`);
        compileDotQuote(this.currentInstructions, stringValue, this.currentCompileMeta(context, rawText));
      } else {
        this.writeOutput(stringValue);
      }
      return;
    }

    const upper = rawText.toUpperCase();
    context.sourceLine = tokenLine;
    context.sourceTokenText = rawText;

    if (this.compileMode) {
      this.currentSourceTokens.push(rawText);
    }

    switch (upper) {
      case ':': {
        if (this.compileMode) {
          throw makeRuntimeError('Nested definitions are not supported', this.dataStack, context.activeWord);
        }
        this.pendingAction = { kind: 'definitionName' };
        return;
      }
      case ';': {
        if (!this.compileMode) {
          throw makeRuntimeError('Unexpected ; outside of definition', this.dataStack, context.activeWord);
        }
        this.finishDefinition();
        return;
      }
      case 'CONSTANT': {
        if (this.compileMode) {
          compileCall(this.currentInstructions, 'CONSTANT', this.currentCompileMeta(context, rawText));
          return;
        }
        const value = this.popData(context.activeWord);
        this.pendingAction = { kind: 'constantName', value };
        return;
      }
      case 'VARIABLE': {
        if (this.compileMode) {
          compileCall(this.currentInstructions, 'VARIABLE', this.currentCompileMeta(context, rawText));
          return;
        }
        this.pendingAction = { kind: 'variableName' };
        return;
      }
      case 'VALUE': {
        if (this.compileMode) {
          compileCall(this.currentInstructions, 'VALUE', this.currentCompileMeta(context, rawText));
          return;
        }
        const value = this.popData(context.activeWord);
        this.pendingAction = { kind: 'valueName', value };
        return;
      }
      case 'TO': {
        if (this.compileMode) {
          this.pendingAction = { kind: 'toTarget' };
          return;
        }
        this.pendingAction = { kind: 'toTarget' };
        return;
      }
      case "'": {
        this.pendingAction = { kind: 'tick' };
        return;
      }
      case 'SEE': {
        this.pendingAction = { kind: 'see' };
        return;
      }
      case 'FORGET': {
        this.pendingAction = { kind: 'forget' };
        return;
      }
      case 'IF':
      case 'ELSE':
      case 'THEN':
      case 'BEGIN':
      case 'UNTIL':
      case 'WHILE':
      case 'REPEAT':
      case 'DO':
      case 'LOOP':
      case '+LOOP':
      case 'LEAVE':
      case 'RECURSE':
      case 'EXIT': {
        if (this.compileMode) {
          this.compileControlWord(upper, context);
          return;
        }
        break;
      }
      default:
        break;
    }

    const word = this.findWord(rawText);
    if (word) {
      if (this.compileMode && !word.immediate) {
        compileCall(this.currentInstructions, word.name, this.currentCompileMeta(context, rawText));
      } else {
        this.executeWordByName(word.name, context);
      }
      return;
    }

    const parsedNumber = this.parseNumber(rawText);
    if (parsedNumber !== undefined) {
      if (this.compileMode) {
        compileLiteral(this.currentInstructions, parsedNumber, this.currentCompileMeta(context, rawText));
      } else {
        this.pushData(parsedNumber);
      }
      return;
    }

    throw makeRuntimeError(`Unknown word: ${rawText}`, this.dataStack, context.activeWord);
  }

  private currentCompileMeta(context: ExecuteContext, sourceToken: string): {
    sourceLine?: number;
    sourceToken?: string;
    sourceDefinition?: string;
  } {
    return {
      sourceLine: context.sourceLine,
      sourceToken,
      sourceDefinition: this.currentWordName,
    };
  }

  private consumePendingAction(name: string, context: ExecuteContext): void {
    if (!this.pendingAction) {
      return;
    }

    const pending = this.pendingAction;
    this.pendingAction = undefined;

    switch (pending.kind) {
      case 'definitionName': {
        this.startDefinition(name);
        break;
      }
      case 'constantName': {
        this.defineConstant(name, pending.value ?? 0);
        break;
      }
      case 'variableName': {
        this.defineVariable(name);
        break;
      }
      case 'valueName': {
        this.defineValue(name, pending.value ?? 0);
        break;
      }
      case 'toTarget': {
        if (this.compileMode) {
          this.currentInstructions.push({
            kind: 'setValue',
            name,
            ...this.currentCompileMeta(context, name),
          });
          this.currentSourceTokens.push(name);
        } else {
          const value = this.popData();
          this.setValueWord(name, value);
        }
        break;
      }
      case 'tick': {
        const target = this.findWord(name);
        if (!target) {
          throw makeRuntimeError(`Unknown word for ': ${name}`, this.dataStack);
        }
        this.pushData(target.id);
        break;
      }
      case 'see': {
        const target = this.findWord(name);
        if (!target) {
          throw makeRuntimeError(`Unknown word for SEE: ${name}`, this.dataStack);
        }
        if (target.type === 'primitive') {
          this.writeOutput(`${target.name} <primitive>`);
        } else {
          const source = target.sourceTokens?.join(' ') ?? '';
          this.writeOutput(`: ${target.name} ${source} ;`);
        }
        break;
      }
      case 'forget': {
        this.forget(name);
        break;
      }
      default:
        break;
    }
  }

  private compileControlWord(word: string, context: ExecuteContext): void {
    const meta = this.currentCompileMeta(context, word);
    switch (word) {
      case 'IF': {
        const branchIndex = this.currentInstructions.length;
        this.currentInstructions.push({ kind: 'branchIfZero', target: -1, ...meta });
        this.controlStack.push({ kind: 'if', origin: branchIndex, branchSlot: branchIndex });
        return;
      }
      case 'ELSE': {
        const ifIndex = findLatestControl(this.controlStack, ['if']);
        if (ifIndex === -1) {
          throw makeRuntimeError('ELSE without IF', this.dataStack, this.currentWordName);
        }

        const frame = this.controlStack[ifIndex];
        const branchIndex = this.currentInstructions.length;
        this.currentInstructions.push({ kind: 'branch', target: -1, ...meta });
        if (frame.branchSlot === undefined) {
          throw makeRuntimeError('Malformed IF frame', this.dataStack, this.currentWordName);
        }
        patchTarget(this.currentInstructions, frame.branchSlot, branchIndex + 1);
        frame.kind = 'else';
        frame.branchSlot = branchIndex;
        return;
      }
      case 'THEN': {
        const frameIndex = findLatestControl(this.controlStack, ['if', 'else']);
        if (frameIndex === -1) {
          throw makeRuntimeError('THEN without IF/ELSE', this.dataStack, this.currentWordName);
        }
        const frame = this.controlStack[frameIndex];
        if (frame.branchSlot === undefined) {
          throw makeRuntimeError('Malformed THEN frame', this.dataStack, this.currentWordName);
        }
        patchTarget(this.currentInstructions, frame.branchSlot, this.currentInstructions.length);
        this.controlStack.splice(frameIndex, 1);
        return;
      }
      case 'BEGIN': {
        this.controlStack.push({ kind: 'begin', origin: this.currentInstructions.length, beginIndex: this.currentInstructions.length });
        return;
      }
      case 'UNTIL': {
        const beginIndex = findLatestControl(this.controlStack, ['begin']);
        if (beginIndex === -1) {
          throw makeRuntimeError('UNTIL without BEGIN', this.dataStack, this.currentWordName);
        }
        const beginFrame = this.controlStack[beginIndex];
        this.currentInstructions.push({
          kind: 'branchIfZero',
          target: beginFrame.beginIndex ?? beginFrame.origin,
          ...meta,
        });
        this.controlStack.splice(beginIndex, 1);
        return;
      }
      case 'WHILE': {
        const beginIndex = findLatestControl(this.controlStack, ['begin']);
        if (beginIndex === -1) {
          throw makeRuntimeError('WHILE without BEGIN', this.dataStack, this.currentWordName);
        }
        const beginFrame = this.controlStack[beginIndex];
        const branchIndex = this.currentInstructions.length;
        this.currentInstructions.push({ kind: 'branchIfZero', target: -1, ...meta });
        this.controlStack.push({
          kind: 'while',
          origin: beginFrame.origin,
          beginIndex: beginFrame.beginIndex,
          branchSlot: branchIndex,
        });
        return;
      }
      case 'REPEAT': {
        const whileIndex = findLatestControl(this.controlStack, ['while']);
        if (whileIndex === -1) {
          throw makeRuntimeError('REPEAT without WHILE', this.dataStack, this.currentWordName);
        }

        const whileFrame = this.controlStack[whileIndex];
        this.currentInstructions.push({ kind: 'branch', target: whileFrame.beginIndex ?? whileFrame.origin, ...meta });
        if (whileFrame.branchSlot === undefined) {
          throw makeRuntimeError('Malformed WHILE frame', this.dataStack, this.currentWordName);
        }
        patchTarget(this.currentInstructions, whileFrame.branchSlot, this.currentInstructions.length);
        this.controlStack.splice(whileIndex, 1);

        const beginIndex = findLatestControl(this.controlStack, ['begin']);
        if (beginIndex !== -1) {
          this.controlStack.splice(beginIndex, 1);
        }
        return;
      }
      case 'DO': {
        const doIndex = this.currentInstructions.length;
        this.currentInstructions.push({ kind: 'do', leaveTarget: -1, ...meta });
        this.controlStack.push({ kind: 'do', origin: doIndex, beginIndex: doIndex + 1, leaveSlots: [] });
        return;
      }
      case 'LEAVE': {
        const doIndex = findLatestControl(this.controlStack, ['do']);
        if (doIndex === -1) {
          throw makeRuntimeError('LEAVE outside DO...LOOP', this.dataStack, this.currentWordName);
        }
        const frame = this.controlStack[doIndex];
        const leaveIndex = this.currentInstructions.length;
        this.currentInstructions.push({ kind: 'leave', target: -1, ...meta });
        frame.leaveSlots = frame.leaveSlots ?? [];
        frame.leaveSlots.push(leaveIndex);
        return;
      }
      case 'LOOP':
      case '+LOOP': {
        const doIndex = findLatestControl(this.controlStack, ['do']);
        if (doIndex === -1) {
          throw makeRuntimeError(`${word} without DO`, this.dataStack, this.currentWordName);
        }
        const frame = this.controlStack[doIndex];
        const target = frame.beginIndex ?? frame.origin + 1;

        if (word === 'LOOP') {
          this.currentInstructions.push({ kind: 'loop', target, ...meta });
        } else {
          this.currentInstructions.push({ kind: 'plusLoop', target, ...meta });
        }

        patchTarget(this.currentInstructions, frame.origin, this.currentInstructions.length);
        for (const slot of frame.leaveSlots ?? []) {
          patchTarget(this.currentInstructions, slot, this.currentInstructions.length);
        }

        this.controlStack.splice(doIndex, 1);
        return;
      }
      case 'RECURSE': {
        if (!this.currentWordName) {
          throw makeRuntimeError('RECURSE outside of definition', this.dataStack, this.currentWordName);
        }
        compileCall(this.currentInstructions, this.currentWordName, meta);
        return;
      }
      case 'EXIT': {
        this.currentInstructions.push({ kind: 'exit', ...meta });
        return;
      }
      default:
        return;
    }
  }

  private startDefinition(name: string): void {
    this.compileMode = true;
    this.currentWordName = name;
    this.currentInstructions = [];
    this.currentSourceTokens = [];
    this.controlStack = [];
  }

  private finishDefinition(): void {
    if (!this.currentWordName) {
      throw makeRuntimeError('No active definition to close', this.dataStack);
    }
    if (this.controlStack.length > 0) {
      throw makeRuntimeError('Unclosed control structure in definition', this.dataStack, this.currentWordName);
    }

    const wordName = this.currentWordName;
    const body = [...this.currentSourceTokens];
    const compiledInstructions = structuredClone(this.currentInstructions);

    this.defineWord(wordName, 'compiled', {
      instructions: compiledInstructions,
      sourceTokens: body,
      immediate: false,
    });

    this.emitEvent({
      type: 'define',
      definition: {
        name: wordName,
        body,
      },
    });

    this.compileMode = false;
    this.currentWordName = undefined;
    this.currentInstructions = [];
    this.currentSourceTokens = [];
    this.controlStack = [];
  }

  private emitEvent(partial: Omit<ForthEvent, 'sequenceNumber' | 'dataStack' | 'returnStack' | 'floatStack'>): void {
    if (this.suppressedEventsDepth > 0) {
      return;
    }

    this.sequenceNumber += 1;

    const event: ForthEvent = {
      sequenceNumber: this.sequenceNumber,
      dataStack: [...this.dataStack],
      returnStack: [...this.returnStack],
      floatStack: [...this.floatStack],
      here: this.here,
      base: this.base,
      loopI: this.loopFrames.at(-1)?.index,
      loopJ: this.loopFrames.length >= 2 ? this.loopFrames[this.loopFrames.length - 2]?.index : undefined,
      loopDepth: this.loopFrames.length,
      callStack: partial.callStack ?? [...this.executionStack],
      ...partial,
    };

    for (const listener of this.listeners) {
      listener(event);
    }
  }

  public writeOutput(text: string): void {
    this.emitEvent({
      type: 'output',
      text,
    });
  }

  public pushData(value: number): void {
    const numericValue = clampToCell(value);
    this.dataStack.push(numericValue);
    this.emitEvent({
      type: 'push',
      stack: 'data',
      value: numericValue,
    });
  }

  public popData(word?: string): number {
    if (this.dataStack.length === 0) {
      throw makeRuntimeError('Data stack underflow', this.dataStack, word);
    }
    const value = this.dataStack.pop() as number;
    this.emitEvent({
      type: 'pop',
      stack: 'data',
      value,
    });
    return value;
  }

  public pushReturn(value: number): void {
    const numericValue = clampToCell(value);
    this.returnStack.push(numericValue);
    this.emitEvent({
      type: 'push',
      stack: 'return',
      value: numericValue,
    });
  }

  public popReturn(word?: string): number {
    if (this.returnStack.length === 0) {
      throw makeRuntimeError('Return stack underflow', this.dataStack, word);
    }
    const value = this.returnStack.pop() as number;
    this.emitEvent({
      type: 'pop',
      stack: 'return',
      value,
    });
    return value;
  }

  public peekData(depth = 0): number {
    const index = this.dataStack.length - 1 - depth;
    if (index < 0) {
      throw makeRuntimeError('Data stack underflow', this.dataStack);
    }
    return this.dataStack[index];
  }

  public peekReturn(depth = 0): number {
    const index = this.returnStack.length - 1 - depth;
    if (index < 0) {
      throw makeRuntimeError('Return stack underflow', this.dataStack);
    }
    return this.returnStack[index];
  }

  public getDataStack(): number[] {
    return [...this.dataStack];
  }

  public getReturnStack(): number[] {
    return [...this.returnStack];
  }

  public clearStacks(): void {
    this.dataStack = [];
    this.returnStack = [];
    this.floatStack = [];
    this.loopFrames = [];
    this.executionStack = [];
  }

  public getLoopFrames(): LoopFrame[] {
    return structuredClone(this.loopFrames);
  }

  public getMemoryCells(): Int32Array {
    return this.memory;
  }

  public getMemoryBytes(): Uint8Array {
    return this.memoryBytes;
  }

  public getBase(): number {
    return this.base;
  }

  public setBase(nextBase: number): void {
    if (nextBase < 2 || nextBase > 36) {
      throw makeRuntimeError(`Invalid BASE value: ${nextBase}`, this.dataStack);
    }
    this.base = nextBase;
  }

  public getHere(): number {
    return this.here;
  }

  public allot(bytes: number): void {
    const nextHere = this.here + bytes;
    if (nextHere < 0 || nextHere > this.memoryBytes.length) {
      throw makeRuntimeError('ALLOT exceeds memory bounds', this.dataStack);
    }
    this.here = nextHere;
  }

  private checkByteAddress(address: number): void {
    if (address < 0 || address >= this.memoryBytes.length) {
      throw makeRuntimeError(`Memory byte address out of range: ${address}`, this.dataStack);
    }
  }

  private checkCellAddress(address: number): number {
    if (address % 4 !== 0) {
      throw makeRuntimeError(`Cell address must be aligned to 4 bytes: ${address}`, this.dataStack);
    }
    const index = address / 4;
    if (index < 0 || index >= this.memory.length) {
      throw makeRuntimeError(`Memory cell address out of range: ${address}`, this.dataStack);
    }
    return index;
  }

  public readCell(address: number): number {
    const index = this.checkCellAddress(address);
    return this.memory[index];
  }

  public writeCell(address: number, value: number): void {
    const index = this.checkCellAddress(address);
    this.memory[index] = clampToCell(value);
  }

  public readByte(address: number): number {
    this.checkByteAddress(address);
    return this.memoryBytes[address];
  }

  public writeByte(address: number, value: number): void {
    this.checkByteAddress(address);
    this.memoryBytes[address] = value & 0xff;
  }

  public storeString(text: string): { addr: number; len: number } {
    const bytes = new TextEncoder().encode(text);
    if (this.here + bytes.length + 1 > this.memoryBytes.length) {
      throw makeRuntimeError('Not enough memory for string literal', this.dataStack);
    }
    const addr = this.here;
    this.memoryBytes.set(bytes, addr);
    this.memoryBytes[addr + bytes.length] = 0;
    this.here += bytes.length + 1;
    return { addr, len: bytes.length };
  }

  public readString(address: number, length: number): string {
    if (address < 0 || length < 0 || address + length > this.memoryBytes.length) {
      throw makeRuntimeError('Invalid string address/length', this.dataStack);
    }
    return new TextDecoder().decode(this.memoryBytes.slice(address, address + length));
  }

  public formatNumber(value: number): string {
    return value.toString(this.base).toUpperCase();
  }

  public parseNumber(text: string): number | undefined {
    if (!text) {
      return undefined;
    }

    const sign = text.startsWith('-') ? -1 : 1;
    const unsigned = text.startsWith('-') || text.startsWith('+') ? text.slice(1) : text;
    if (!unsigned) {
      return undefined;
    }

    if (!/^[0-9A-Za-z]+$/.test(unsigned)) {
      return undefined;
    }

    const value = parseInt(unsigned, this.base);
    if (Number.isNaN(value)) {
      return undefined;
    }

    return clampToCell(sign * value);
  }

  public definePrimitive(
    name: string,
    implementation: WordEntry['primitive'],
    options: { immediate?: boolean; stackEffect?: StackEffectDecl; documentation?: string; opaque?: boolean } = {}
  ): void {
    const entry = this.defineWord(name, 'primitive', {
      primitive: implementation,
      primitiveName: name.toUpperCase(),
      immediate: options.immediate ?? false,
      stackEffect: options.stackEffect,
      documentation: options.documentation,
      opaque: options.opaque,
    });

    this.primitiveRegistry.set(entry.primitiveName ?? entry.upperName, implementation);
  }

  public defineConstant(name: string, value: number): void {
    this.defineWord(name, 'constant', {
      runtimeValue: value,
      stackEffect: {
        raw: '-- n',
        outputs: ['n'],
      },
    });
  }

  public defineVariable(name: string): void {
    const address = this.here;
    this.allot(4);
    this.writeCell(address, 0);

    this.defineWord(name, 'variable', {
      address,
      stackEffect: {
        raw: '-- addr',
        outputs: ['addr'],
      },
    });
  }

  public defineValue(name: string, value: number): void {
    this.defineWord(name, 'value', {
      runtimeValue: value,
      stackEffect: {
        raw: '-- n',
        outputs: ['n'],
      },
    });
  }

  public setValueWord(name: string, value: number): void {
    const word = this.findWord(name);
    if (!word || word.type !== 'value') {
      throw makeRuntimeError(`TO requires VALUE target, got: ${name}`, this.dataStack);
    }
    word.runtimeValue = clampToCell(value);
  }

  public markLatestImmediate(): void {
    const latest = this.allWords[this.allWords.length - 1];
    if (!latest) {
      throw makeRuntimeError('No latest word to mark IMMEDIATE', this.dataStack);
    }
    latest.immediate = true;
  }

  public forget(name: string): void {
    const target = this.findWord(name);
    if (!target) {
      throw makeRuntimeError(`FORGET unknown word: ${name}`, this.dataStack);
    }
    if (target.type === 'primitive') {
      throw makeRuntimeError(`FORGET cannot remove primitive: ${name}`, this.dataStack);
    }

    const cutoff = target.definitionOrder;
    const retained = this.allWords.filter((word) => word.type === 'primitive' || word.definitionOrder < cutoff);

    this.dictionaryByName.clear();
    this.allWords = [];
    this.definitionOrder = 0;

    for (const word of retained) {
      this.addWord({ ...word });
    }

    this.emitEvent({
      type: 'forget',
      word: target.name,
    });
  }

  public defineWord(
    name: string,
    type: WordType,
    options: {
      immediate?: boolean;
      primitive?: WordEntry['primitive'];
      primitiveName?: string;
      instructions?: Instruction[];
      sourceTokens?: string[];
      stackEffect?: StackEffectDecl;
      documentation?: string;
      runtimeValue?: number;
      address?: number;
      opaque?: boolean;
    } = {}
  ): WordEntry {
    const entry: WordEntry = {
      id: this.definitionOrder + 1,
      name,
      upperName: normalizeWordName(name),
      immediate: options.immediate ?? false,
      type,
      primitiveName: options.primitiveName,
      primitive: options.primitive,
      instructions: options.instructions,
      sourceTokens: options.sourceTokens,
      stackEffect: options.stackEffect,
      documentation: options.documentation,
      definitionOrder: this.definitionOrder + 1,
      callCount: 0,
      runtimeValue: options.runtimeValue,
      address: options.address,
      opaque: options.opaque,
    };

    this.addWord(entry);
    return entry;
  }

  private addWord(entry: WordEntry): void {
    this.definitionOrder = Math.max(this.definitionOrder, entry.definitionOrder);
    this.allWords.push(entry);

    const existing = this.dictionaryByName.get(entry.upperName) ?? [];
    existing.push(entry);
    this.dictionaryByName.set(entry.upperName, existing);
  }

  public findWord(name: string): WordEntry | undefined {
    const key = normalizeWordName(name);
    const versions = this.dictionaryByName.get(key);
    if (!versions || versions.length === 0) {
      return undefined;
    }
    return versions[versions.length - 1];
  }

  public getWordVersions(name: string): WordEntry[] {
    const key = normalizeWordName(name);
    return [...(this.dictionaryByName.get(key) ?? [])];
  }

  public getLatestWords(): WordEntry[] {
    const latest: WordEntry[] = [];
    for (const versions of this.dictionaryByName.values()) {
      const word = versions[versions.length - 1];
      if (word) {
        latest.push(word);
      }
    }

    latest.sort((a, b) => a.definitionOrder - b.definitionOrder);
    return latest;
  }

  public getAllWords(): WordEntry[] {
    return [...this.allWords];
  }

  public executeLiteralWord(word: WordEntry): void {
    switch (word.type) {
      case 'constant':
      case 'value': {
        this.executionStack.push(word.name);
        try {
          this.pushData(word.runtimeValue ?? 0);
          this.emitEvent({
            type: 'execute',
            word: word.name,
          });
        } finally {
          this.executionStack.pop();
        }
        return;
      }
      case 'variable': {
        this.executionStack.push(word.name);
        try {
          this.pushData(word.address ?? 0);
          this.emitEvent({
            type: 'execute',
            word: word.name,
          });
        } finally {
          this.executionStack.pop();
        }
        return;
      }
      default:
        this.executeWordByName(word.name);
    }
  }

  public createSnapshot(): ForthSnapshot {
    const dictionary = this.getLatestWords()
      .filter((word) => word.type !== 'primitive')
      .map((word) => serializeWord(word));

    return {
      dataStack: [...this.dataStack],
      returnStack: [...this.returnStack],
      floatStack: [...this.floatStack],
      loopFrames: structuredClone(this.loopFrames),
      memory: Array.from(this.memory),
      here: this.here,
      base: this.base,
      compileMode: this.compileMode,
      currentWordName: this.currentWordName,
      currentInstructions: structuredClone(this.currentInstructions),
      currentSourceTokens: [...this.currentSourceTokens],
      pendingControl: structuredClone(this.controlStack),
      dictionary,
      sequenceNumber: this.sequenceNumber,
    };
  }

  public restoreSnapshot(snapshot: ForthSnapshot): void {
    const safeSnapshot = cloneSnapshot(snapshot);

    this.dataStack = [...safeSnapshot.dataStack];
    this.returnStack = [...safeSnapshot.returnStack];
    this.floatStack = [...safeSnapshot.floatStack];
    this.loopFrames = structuredClone(safeSnapshot.loopFrames);
    this.memory = Int32Array.from(safeSnapshot.memory);
    this.memoryBytes = new Uint8Array(this.memory.buffer);
    this.here = safeSnapshot.here;
    this.base = safeSnapshot.base;
    this.compileMode = safeSnapshot.compileMode;
    this.currentWordName = safeSnapshot.currentWordName;
    this.currentInstructions = safeSnapshot.currentInstructions
      ? structuredClone(safeSnapshot.currentInstructions)
      : [];
    this.currentSourceTokens = safeSnapshot.currentSourceTokens ? [...safeSnapshot.currentSourceTokens] : [];
    this.controlStack = safeSnapshot.pendingControl ? structuredClone(safeSnapshot.pendingControl) : [];
    this.pendingAction = undefined;
    this.executionStack = [];
    this.sequenceNumber = safeSnapshot.sequenceNumber;

    this.dictionaryByName.clear();
    this.allWords = [];
    this.definitionOrder = 0;

    for (const builtin of this.builtins) {
      this.addWord({ ...builtin });
    }

    for (const serialized of safeSnapshot.dictionary) {
      const entry: WordEntry = {
        id: serialized.definitionOrder,
        name: serialized.name,
        upperName: serialized.upperName,
        immediate: serialized.immediate,
        type: serialized.type,
        primitiveName: serialized.primitiveName,
        primitive: serialized.primitiveName
          ? this.primitiveRegistry.get(serialized.primitiveName)
          : undefined,
        instructions: serialized.instructions ? structuredClone(serialized.instructions) : undefined,
        sourceTokens: serialized.sourceTokens ? [...serialized.sourceTokens] : undefined,
        stackEffect: serialized.stackEffect ? structuredClone(serialized.stackEffect) : undefined,
        documentation: serialized.documentation,
        definitionOrder: serialized.definitionOrder,
        callCount: serialized.callCount,
        runtimeValue: serialized.runtimeValue,
        address: serialized.address,
        opaque: serialized.opaque,
      };
      this.addWord(entry);
    }
  }

  public runWithRecovery(source: string, options: EngineExecuteOptions = {}): { ok: boolean; error?: ForthRuntimeError } {
    const before = this.createSnapshot();
    try {
      this.execute(source, options);
      return { ok: true };
    } catch (error) {
      const runtimeError = this.normalizeError(error);
      this.restoreSnapshot(before);
      this.emitEvent({
        type: 'error',
        error: {
          message: runtimeError.message,
          word: runtimeError.word,
          stackBefore: runtimeError.stackBefore,
        },
      });
      return {
        ok: false,
        error: runtimeError,
      };
    }
  }

  private normalizeError(error: unknown): ForthRuntimeError {
    if (error instanceof Error && 'stackBefore' in error) {
      return error as ForthRuntimeError;
    }

    if (error instanceof Error) {
      return makeRuntimeError(error.message, this.dataStack);
    }

    return makeRuntimeError('Unknown engine error', this.dataStack);
  }

  public renderStack(): string {
    if (this.dataStack.length === 0) {
      return '<empty>';
    }
    return `[ ${this.dataStack.map((value) => this.formatNumber(value)).join(' ')} ]`;
  }

  public printStack(): void {
    this.writeOutput(this.renderStack());
  }

  public getDictionaryNames(): string[] {
    return this.getLatestWords().map((word) => word.name);
  }

  public parseStackEffect(effect: string): StackEffectDecl {
    const cleaned = effect.trim();
    const [lhs, rhs] = cleaned.split('--').map((part) => part.trim());
    const inputs = lhs ? lhs.split(/\s+/).filter(Boolean) : [];
    const outputs = rhs ? rhs.split(/\s+/).filter(Boolean) : [];
    return {
      raw: cleaned,
      inputs,
      outputs,
    };
  }

  public applyWordRuntime(word: WordEntry): boolean {
    switch (word.type) {
      case 'constant':
      case 'value': {
        this.pushData(word.runtimeValue ?? 0);
        return true;
      }
      case 'variable': {
        this.pushData(word.address ?? 0);
        return true;
      }
      default:
        return false;
    }
  }

  public executeNamed(name: string): void {
    const word = this.findWord(name);
    if (!word) {
      throw makeRuntimeError(`Unknown word: ${name}`, this.dataStack);
    }

    if (this.applyWordRuntime(word)) {
      this.executionStack.push(word.name);
      try {
        this.emitEvent({
          type: 'execute',
          word: word.name,
        });
      } finally {
        this.executionStack.pop();
      }
      return;
    }

    this.executeWordByName(word.name);
  }

  public runLine(source: string): { ok: boolean; error?: ForthRuntimeError } {
    return this.runWithRecovery(source, { recordInput: true, sourceLabel: 'repl' });
  }

  public tokenUpper(text: string): string {
    return tokenTextUpper({
      text,
      kind: 'word',
      line: 0,
      column: 0,
      start: 0,
      end: 0,
    });
  }
}
