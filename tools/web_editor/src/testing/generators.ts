export interface GeneratedProgram {
  seed: number;
  literals: number[];
  operations: string[];
  directProgram: string;
  compiledProgram: string;
}

export interface GenerationOptions {
  minLiterals?: number;
  maxLiterals?: number;
  minOps?: number;
  maxOps?: number;
  maxDepthBeforeBias?: number;
}

interface OpSpec {
  token: string;
  inputs: number;
  outputs: number;
}

const PURE_OPS: OpSpec[] = [
  { token: 'DUP', inputs: 1, outputs: 2 },
  { token: 'DROP', inputs: 1, outputs: 0 },
  { token: 'SWAP', inputs: 2, outputs: 2 },
  { token: 'OVER', inputs: 2, outputs: 3 },
  { token: 'ROT', inputs: 3, outputs: 3 },
  { token: 'NIP', inputs: 2, outputs: 1 },
  { token: 'TUCK', inputs: 2, outputs: 3 },
  { token: '+', inputs: 2, outputs: 1 },
  { token: '-', inputs: 2, outputs: 1 },
  { token: '*', inputs: 2, outputs: 1 },
  { token: 'AND', inputs: 2, outputs: 1 },
  { token: 'OR', inputs: 2, outputs: 1 },
  { token: 'XOR', inputs: 2, outputs: 1 },
  { token: 'MIN', inputs: 2, outputs: 1 },
  { token: 'MAX', inputs: 2, outputs: 1 },
  { token: 'NEGATE', inputs: 1, outputs: 1 },
  { token: 'ABS', inputs: 1, outputs: 1 },
  { token: 'INVERT', inputs: 1, outputs: 1 },
  { token: '=', inputs: 2, outputs: 1 },
  { token: '<', inputs: 2, outputs: 1 },
  { token: '>', inputs: 2, outputs: 1 },
];

function createPrng(seed: number): () => number {
  let state = (seed >>> 0) + 0x9e3779b9;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return state >>> 0;
  };
}

function randomInt(next: () => number, min: number, max: number): number {
  if (max < min) {
    return min;
  }
  return min + (next() % (max - min + 1));
}

function chooseOp(next: () => number, depth: number, maxDepthBeforeBias: number): OpSpec | undefined {
  const eligible = PURE_OPS.filter((op) => op.inputs <= depth);
  if (eligible.length === 0) {
    return undefined;
  }

  // When depth grows high, bias toward reducers.
  if (depth >= maxDepthBeforeBias) {
    const reducers = eligible.filter((op) => op.outputs <= op.inputs);
    if (reducers.length > 0) {
      return reducers[next() % reducers.length];
    }
  }

  return eligible[next() % eligible.length];
}

export function generateStackSafeProgram(seed: number, options: GenerationOptions = {}): GeneratedProgram {
  const minLiterals = options.minLiterals ?? 2;
  const maxLiterals = options.maxLiterals ?? 6;
  const minOps = options.minOps ?? 6;
  const maxOps = options.maxOps ?? 50;
  const maxDepthBeforeBias = options.maxDepthBeforeBias ?? 8;

  const next = createPrng(seed);

  const literalCount = randomInt(next, minLiterals, maxLiterals);
  const literals = Array.from({ length: literalCount }, () => randomInt(next, -60, 60));

  const operationCount = randomInt(next, minOps, maxOps);
  const operations: string[] = [];

  let depth = literalCount;
  for (let i = 0; i < operationCount; i += 1) {
    let op = chooseOp(next, depth, maxDepthBeforeBias);

    if (!op) {
      const lit = randomInt(next, -40, 40);
      operations.push(String(lit));
      depth += 1;
      continue;
    }

    // Inject additional literals occasionally to diversify expression shape.
    if (randomInt(next, 0, 9) === 0) {
      const lit = randomInt(next, -30, 30);
      operations.push(String(lit));
      depth += 1;
      op = chooseOp(next, depth, maxDepthBeforeBias) ?? op;
    }

    operations.push(op.token);
    depth = depth - op.inputs + op.outputs;
  }

  // Keep non-empty result stack.
  if (depth === 0) {
    const lit = randomInt(next, -25, 25);
    operations.push(String(lit));
  }

  const literalPart = literals.map((value) => String(value)).join(' ');
  const opsPart = operations.join(' ');
  const directProgram = `${literalPart} ${opsPart}`.trim();
  const compiledProgram = `: __P ${opsPart} ; ${literalPart} __P`;

  return {
    seed,
    literals,
    operations,
    directProgram,
    compiledProgram,
  };
}
