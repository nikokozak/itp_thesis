import type { ForthEngine } from './forth';
import type { StackEffectDecl } from './types';

export interface PrimitiveEffect {
  inputs: number;
  outputs: number;
  inputLabels?: string[];
  outputLabels?: string[];
  verified: boolean;
  opaque?: boolean;
}

const EFFECTS: Record<string, PrimitiveEffect> = {
  DUP: { inputs: 1, outputs: 2, inputLabels: ['a'], outputLabels: ['a', 'a'], verified: true },
  DROP: { inputs: 1, outputs: 0, inputLabels: ['a'], outputLabels: [], verified: true },
  SWAP: { inputs: 2, outputs: 2, inputLabels: ['a', 'b'], outputLabels: ['b', 'a'], verified: true },
  OVER: { inputs: 2, outputs: 3, inputLabels: ['a', 'b'], outputLabels: ['a', 'b', 'a'], verified: true },
  ROT: { inputs: 3, outputs: 3, inputLabels: ['a', 'b', 'c'], outputLabels: ['b', 'c', 'a'], verified: true },
  '-ROT': { inputs: 3, outputs: 3, inputLabels: ['a', 'b', 'c'], outputLabels: ['c', 'a', 'b'], verified: true },
  NIP: { inputs: 2, outputs: 1, verified: true },
  TUCK: { inputs: 2, outputs: 3, verified: true },
  PICK: { inputs: 1, outputs: 1, verified: false, opaque: true },
  ROLL: { inputs: 1, outputs: 0, verified: false, opaque: true },
  '2DUP': { inputs: 2, outputs: 4, verified: true },
  '2DROP': { inputs: 2, outputs: 0, verified: true },
  '2SWAP': { inputs: 4, outputs: 4, verified: true },
  '2OVER': { inputs: 4, outputs: 6, verified: true },
  DEPTH: { inputs: 0, outputs: 1, verified: true },
  '+': { inputs: 2, outputs: 1, verified: true },
  '-': { inputs: 2, outputs: 1, verified: true },
  '*': { inputs: 2, outputs: 1, verified: true },
  '/': { inputs: 2, outputs: 1, verified: true },
  MOD: { inputs: 2, outputs: 1, verified: true },
  '/MOD': { inputs: 2, outputs: 2, verified: true },
  NEGATE: { inputs: 1, outputs: 1, verified: true },
  ABS: { inputs: 1, outputs: 1, verified: true },
  MIN: { inputs: 2, outputs: 1, verified: true },
  MAX: { inputs: 2, outputs: 1, verified: true },
  '=': { inputs: 2, outputs: 1, verified: true },
  '<>': { inputs: 2, outputs: 1, verified: true },
  '<': { inputs: 2, outputs: 1, verified: true },
  '>': { inputs: 2, outputs: 1, verified: true },
  '<=': { inputs: 2, outputs: 1, verified: true },
  '>=': { inputs: 2, outputs: 1, verified: true },
  '0=': { inputs: 1, outputs: 1, verified: true },
  '0<': { inputs: 1, outputs: 1, verified: true },
  '0>': { inputs: 1, outputs: 1, verified: true },
  AND: { inputs: 2, outputs: 1, verified: true },
  OR: { inputs: 2, outputs: 1, verified: true },
  XOR: { inputs: 2, outputs: 1, verified: true },
  INVERT: { inputs: 1, outputs: 1, verified: true },
  '@': { inputs: 1, outputs: 1, verified: true },
  '!': { inputs: 2, outputs: 0, verified: true },
  '+!': { inputs: 2, outputs: 0, verified: true },
  'C@': { inputs: 1, outputs: 1, verified: true },
  'C!': { inputs: 2, outputs: 0, verified: true },
  ALLOT: { inputs: 1, outputs: 0, verified: true },
  HERE: { inputs: 0, outputs: 1, verified: true },
  CELLS: { inputs: 1, outputs: 1, verified: true },
  'CELL+': { inputs: 1, outputs: 1, verified: true },
  '.': { inputs: 1, outputs: 0, verified: true },
  '.S': { inputs: 0, outputs: 0, verified: true },
  CR: { inputs: 0, outputs: 0, verified: true },
  SPACE: { inputs: 0, outputs: 0, verified: true },
  SPACES: { inputs: 1, outputs: 0, verified: true },
  EMIT: { inputs: 1, outputs: 0, verified: true },
  TYPE: { inputs: 2, outputs: 0, verified: true },
  '>R': { inputs: 1, outputs: 0, verified: true },
  'R>': { inputs: 0, outputs: 1, verified: true },
  'R@': { inputs: 0, outputs: 1, verified: true },
  I: { inputs: 0, outputs: 1, verified: true },
  J: { inputs: 0, outputs: 1, verified: true },
  COUNT: { inputs: 1, outputs: 2, verified: true },
  BASE: { inputs: 0, outputs: 1, verified: true },
  HEX: { inputs: 0, outputs: 0, verified: true },
  DECIMAL: { inputs: 0, outputs: 0, verified: true },
};

export function getCoreEffects(): Record<string, PrimitiveEffect> {
  return EFFECTS;
}

function stackEffectFromCounts(effect: PrimitiveEffect): StackEffectDecl {
  const inputs = Array.from({ length: effect.inputs }, (_, index) => `in${index + 1}`);
  const outputs = Array.from({ length: effect.outputs }, (_, index) => `out${index + 1}`);
  return {
    raw: `${inputs.join(' ')} -- ${outputs.join(' ')}`.trim(),
    inputs,
    outputs,
  };
}

function define(engine: ForthEngine, name: string, fn: () => void, immediate = false): void {
  const effect = EFFECTS[name];
  engine.definePrimitive(name, fn, {
    immediate,
    stackEffect: effect ? stackEffectFromCounts(effect) : undefined,
    opaque: Boolean(effect?.opaque),
  });
}

function binaryOp(engine: ForthEngine, op: (a: number, b: number) => number): number {
  const b = engine.popData();
  const a = engine.popData();
  return op(a, b);
}

function unaryOp(engine: ForthEngine, op: (a: number) => number): number {
  const a = engine.popData();
  return op(a);
}

function comparisonFlag(result: boolean): number {
  return result ? 1 : 0;
}

function fail(message: string): never {
  throw new Error(message);
}

export function registerCorePrimitives(engine: ForthEngine): void {
  define(engine, 'DUP', () => {
    engine.pushData(engine.peekData());
  });

  define(engine, 'DROP', () => {
    engine.popData();
  });

  define(engine, 'SWAP', () => {
    const b = engine.popData();
    const a = engine.popData();
    engine.pushData(b);
    engine.pushData(a);
  });

  define(engine, 'OVER', () => {
    engine.pushData(engine.peekData(1));
  });

  define(engine, 'ROT', () => {
    const c = engine.popData();
    const b = engine.popData();
    const a = engine.popData();
    engine.pushData(b);
    engine.pushData(c);
    engine.pushData(a);
  });

  define(engine, '-ROT', () => {
    const c = engine.popData();
    const b = engine.popData();
    const a = engine.popData();
    engine.pushData(c);
    engine.pushData(a);
    engine.pushData(b);
  });

  define(engine, 'NIP', () => {
    const b = engine.popData();
    engine.popData();
    engine.pushData(b);
  });

  define(engine, 'TUCK', () => {
    const b = engine.popData();
    const a = engine.popData();
    engine.pushData(b);
    engine.pushData(a);
    engine.pushData(b);
  });

  define(engine, 'PICK', () => {
    const depth = engine.popData();
    if (depth < 0) {
      fail('PICK depth must be non-negative');
    }
    engine.pushData(engine.peekData(depth));
  });

  define(engine, 'ROLL', () => {
    const depth = engine.popData();
    if (depth < 0) {
      fail('ROLL depth must be non-negative');
    }
    const temp: number[] = [];
    for (let i = 0; i < depth; i += 1) {
      temp.push(engine.popData());
    }
    const target = engine.popData();
    for (let i = temp.length - 1; i >= 0; i -= 1) {
      engine.pushData(temp[i]);
    }
    engine.pushData(target);
  });

  define(engine, '2DUP', () => {
    const b = engine.peekData();
    const a = engine.peekData(1);
    engine.pushData(a);
    engine.pushData(b);
  });

  define(engine, '2DROP', () => {
    engine.popData();
    engine.popData();
  });

  define(engine, '2SWAP', () => {
    const d = engine.popData();
    const c = engine.popData();
    const b = engine.popData();
    const a = engine.popData();
    engine.pushData(c);
    engine.pushData(d);
    engine.pushData(a);
    engine.pushData(b);
  });

  define(engine, '2OVER', () => {
    const a = engine.peekData(3);
    const b = engine.peekData(2);
    engine.pushData(a);
    engine.pushData(b);
  });

  define(engine, 'DEPTH', () => {
    engine.pushData(engine.getDataStack().length);
  });

  define(engine, '+', () => {
    engine.pushData(binaryOp(engine, (a, b) => a + b));
  });

  define(engine, '-', () => {
    engine.pushData(binaryOp(engine, (a, b) => a - b));
  });

  define(engine, '*', () => {
    engine.pushData(binaryOp(engine, (a, b) => a * b));
  });

  define(engine, '/', () => {
    engine.pushData(binaryOp(engine, (a, b) => (b === 0 ? 0 : Math.trunc(a / b))));
  });

  define(engine, 'MOD', () => {
    engine.pushData(binaryOp(engine, (a, b) => (b === 0 ? 0 : a % b)));
  });

  define(engine, '/MOD', () => {
    const divisor = engine.popData();
    const dividend = engine.popData();
    if (divisor === 0) {
      engine.pushData(0);
      engine.pushData(0);
      return;
    }
    engine.pushData(dividend % divisor);
    engine.pushData(Math.trunc(dividend / divisor));
  });

  define(engine, 'NEGATE', () => {
    engine.pushData(unaryOp(engine, (a) => -a));
  });

  define(engine, 'ABS', () => {
    engine.pushData(unaryOp(engine, (a) => Math.abs(a)));
  });

  define(engine, 'MIN', () => {
    engine.pushData(binaryOp(engine, (a, b) => Math.min(a, b)));
  });

  define(engine, 'MAX', () => {
    engine.pushData(binaryOp(engine, (a, b) => Math.max(a, b)));
  });

  define(engine, '=', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a === b)));
  });

  define(engine, '<>', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a !== b)));
  });

  define(engine, '<', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a < b)));
  });

  define(engine, '>', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a > b)));
  });

  define(engine, '<=', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a <= b)));
  });

  define(engine, '>=', () => {
    engine.pushData(binaryOp(engine, (a, b) => comparisonFlag(a >= b)));
  });

  define(engine, '0=', () => {
    engine.pushData(unaryOp(engine, (a) => comparisonFlag(a === 0)));
  });

  define(engine, '0<', () => {
    engine.pushData(unaryOp(engine, (a) => comparisonFlag(a < 0)));
  });

  define(engine, '0>', () => {
    engine.pushData(unaryOp(engine, (a) => comparisonFlag(a > 0)));
  });

  define(engine, 'AND', () => {
    engine.pushData(binaryOp(engine, (a, b) => a & b));
  });

  define(engine, 'OR', () => {
    engine.pushData(binaryOp(engine, (a, b) => a | b));
  });

  define(engine, 'XOR', () => {
    engine.pushData(binaryOp(engine, (a, b) => a ^ b));
  });

  define(engine, 'INVERT', () => {
    engine.pushData(unaryOp(engine, (a) => ~a));
  });

  define(engine, '@', () => {
    const address = engine.popData();
    engine.pushData(engine.readCell(address));
  });

  define(engine, '!', () => {
    const address = engine.popData();
    const value = engine.popData();
    engine.writeCell(address, value);
  });

  define(engine, '+!', () => {
    const address = engine.popData();
    const value = engine.popData();
    engine.writeCell(address, engine.readCell(address) + value);
  });

  define(engine, 'C@', () => {
    const address = engine.popData();
    engine.pushData(engine.readByte(address));
  });

  define(engine, 'C!', () => {
    const address = engine.popData();
    const value = engine.popData();
    engine.writeByte(address, value);
  });

  define(engine, 'ALLOT', () => {
    engine.allot(engine.popData());
  });

  define(engine, 'HERE', () => {
    engine.pushData(engine.getHere());
  });

  define(engine, 'CELLS', () => {
    engine.pushData(engine.popData() * 4);
  });

  define(engine, 'CELL+', () => {
    engine.pushData(engine.popData() + 4);
  });

  define(engine, '>R', () => {
    engine.pushReturn(engine.popData());
  });

  define(engine, 'R>', () => {
    engine.pushData(engine.popReturn());
  });

  define(engine, 'R@', () => {
    engine.pushData(engine.peekReturn());
  });

  define(engine, 'I', () => {
    const frame = engine.getLoopFrames().at(-1);
    if (!frame) {
      fail('I used outside loop');
    }
    engine.pushData(frame.index);
  });

  define(engine, 'J', () => {
    const frames = engine.getLoopFrames();
    const frame = frames.length >= 2 ? frames[frames.length - 2] : undefined;
    if (!frame) {
      fail('J used outside nested loop');
    }
    engine.pushData(frame.index);
  });

  define(engine, '.', () => {
    engine.writeOutput(engine.formatNumber(engine.popData()));
  });

  define(engine, '.S', () => {
    engine.printStack();
  });

  define(engine, 'CR', () => {
    engine.writeOutput('\n');
  });

  define(engine, 'SPACE', () => {
    engine.writeOutput(' ');
  });

  define(engine, 'SPACES', () => {
    const count = Math.max(0, engine.popData());
    engine.writeOutput(' '.repeat(count));
  });

  define(engine, 'EMIT', () => {
    engine.writeOutput(String.fromCharCode(engine.popData() & 0xff));
  });

  define(engine, 'TYPE', () => {
    const length = engine.popData();
    const address = engine.popData();
    engine.writeOutput(engine.readString(address, length));
  });

  define(engine, 'COUNT', () => {
    const address = engine.popData();
    const len = engine.readByte(address);
    engine.pushData(address + 1);
    engine.pushData(len);
  });

  define(engine, 'BASE', () => {
    engine.pushData(engine.getBase());
  });

  define(engine, 'HEX', () => {
    engine.setBase(16);
  });

  define(engine, 'DECIMAL', () => {
    engine.setBase(10);
  });

  define(engine, 'WORDS', () => {
    engine.writeOutput(engine.getDictionaryNames().join(' '));
  });

  define(engine, 'FIND', () => {
    const length = engine.popData();
    const address = engine.popData();
    const word = engine.findWord(engine.readString(address, length));
    if (!word) {
      engine.pushData(0);
      engine.pushData(0);
      return;
    }
    engine.pushData(word.id);
    engine.pushData(1);
  });

  define(engine, 'SEE', () => {
    // Token interpreter handles the lookahead behavior.
  });

  define(engine, 'CONSTANT', () => {
    fail('CONSTANT is handled by parser-level token sequencing');
  });

  define(engine, 'VARIABLE', () => {
    fail('VARIABLE is handled by parser-level token sequencing');
  });

  define(engine, 'VALUE', () => {
    fail('VALUE is handled by parser-level token sequencing');
  });

  define(engine, 'TO', () => {
    fail('TO is handled by parser-level token sequencing');
  });

  define(engine, 'CREATE', () => {
    fail('CREATE is not fully supported in this prototype');
  });

  define(engine, 'DOES>', () => {
    fail('DOES> is not fully supported in this prototype');
  }, true);

  define(engine, 'IMMEDIATE', () => {
    engine.markLatestImmediate();
  }, true);

  define(engine, 'IF', () => {
    fail('IF can only be used while compiling a definition');
  }, true);

  define(engine, 'ELSE', () => {
    fail('ELSE can only be used while compiling a definition');
  }, true);

  define(engine, 'THEN', () => {
    fail('THEN can only be used while compiling a definition');
  }, true);

  define(engine, 'DO', () => {
    fail('DO can only be used while compiling a definition');
  }, true);

  define(engine, 'LOOP', () => {
    fail('LOOP can only be used while compiling a definition');
  }, true);

  define(engine, '+LOOP', () => {
    fail('+LOOP can only be used while compiling a definition');
  }, true);

  define(engine, 'BEGIN', () => {
    fail('BEGIN can only be used while compiling a definition');
  }, true);

  define(engine, 'UNTIL', () => {
    fail('UNTIL can only be used while compiling a definition');
  }, true);

  define(engine, 'WHILE', () => {
    fail('WHILE can only be used while compiling a definition');
  }, true);

  define(engine, 'REPEAT', () => {
    fail('REPEAT can only be used while compiling a definition');
  }, true);

  define(engine, 'LEAVE', () => {
    fail('LEAVE can only be used while compiling a definition');
  }, true);

  define(engine, 'RECURSE', () => {
    fail('RECURSE can only be used while compiling a definition');
  }, true);

  define(engine, 'EXIT', () => {
    fail('EXIT can only be used while compiling a definition');
  }, true);
}
