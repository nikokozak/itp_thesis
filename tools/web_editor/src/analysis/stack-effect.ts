import { getCoreEffects } from '../engine/primitives';
import { parseDefinitionBlocks } from '../utils/forth-parser';
import type {
  DefinitionAnalysis,
  DefinitionStep,
  StackEffect,
  StackEffectDatabase,
} from './types';

interface ControlFrameState {
  kind: 'if' | 'else' | 'begin' | 'while' | 'do';
  depthAtStart: number;
  branchDepth?: number;
  beginDepth?: number;
  exitDepth?: number;
}

export interface SourceStackEffectResult {
  definitions: DefinitionAnalysis[];
  effectDb: StackEffectDatabase;
}

const CONTROL_WORDS = new Set([
  'IF',
  'ELSE',
  'THEN',
  'BEGIN',
  'UNTIL',
  'WHILE',
  'REPEAT',
  'DO',
  'LOOP',
  '+LOOP',
  'LEAVE',
  'EXIT',
  'RECURSE',
]);

export function parseDeclaredEffect(raw?: string): { inputs: string[]; outputs: string[] } | undefined {
  if (!raw) {
    return undefined;
  }

  const parts = raw.split('--');
  if (parts.length !== 2) {
    return undefined;
  }

  return {
    inputs: parts[0].trim().split(/\s+/).filter(Boolean),
    outputs: parts[1].trim().split(/\s+/).filter(Boolean),
  };
}

export function createInitialEffectDatabase(): StackEffectDatabase {
  const base: StackEffectDatabase = {};

  const core = getCoreEffects();
  for (const [word, effect] of Object.entries(core)) {
    base[word.toUpperCase()] = {
      inputs: effect.inputs,
      outputs: effect.outputs,
      inputLabels: effect.inputLabels,
      outputLabels: effect.outputLabels,
      verified: effect.verified,
      opaque: Boolean(effect.opaque),
    };
  }

  return base;
}

function applyEffect(
  depth: number,
  minDepth: number,
  consumed: number,
  produced: number
): { depth: number; minDepth: number } {
  const afterConsume = depth - consumed;
  const nextMin = Math.min(minDepth, afterConsume);
  return {
    depth: afterConsume + produced,
    minDepth: nextMin,
  };
}

function appendStep(
  steps: DefinitionStep[],
  token: DefinitionStep['token'],
  depthBefore: number,
  depthAfter: number,
  minDepth: number,
  consumed: number,
  produced: number,
  opaque = false
): void {
  steps.push({
    token,
    depthBefore,
    depthAfter,
    minDepth,
    consumed,
    produced,
    opaque,
  });
}

function analyzeDefinition(
  definitionSource: ReturnType<typeof parseDefinitionBlocks>[number],
  effectDb: StackEffectDatabase
): DefinitionAnalysis {
  const errors: string[] = [];
  const warnings: string[] = [];
  const opaqueTokens = new Set<string>();
  const steps: DefinitionStep[] = [];
  const controlStack: ControlFrameState[] = [];

  let depth = 0;
  let minDepth = 0;
  let opaque = false;

  for (const token of definitionSource.body) {
    const upper = token.text.toUpperCase();
    const depthBefore = depth;

    if (CONTROL_WORDS.has(upper)) {
      switch (upper) {
        case 'IF': {
          ({ depth, minDepth } = applyEffect(depth, minDepth, 1, 0));
          controlStack.push({ kind: 'if', depthAtStart: depth });
          appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
          continue;
        }
        case 'ELSE': {
          const frame = controlStack.pop();
          if (!frame || frame.kind !== 'if') {
            errors.push(`${definitionSource.name}:${token.line} ELSE without IF`);
            appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
            continue;
          }

          frame.kind = 'else';
          frame.branchDepth = depth;
          depth = frame.depthAtStart;
          controlStack.push(frame);
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'THEN': {
          const frame = controlStack.pop();
          if (!frame || (frame.kind !== 'if' && frame.kind !== 'else')) {
            errors.push(`${definitionSource.name}:${token.line} THEN without IF/ELSE`);
            appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
            continue;
          }

          if (frame.kind === 'if') {
            if (depth !== frame.depthAtStart) {
              errors.push(
                `${definitionSource.name}:${token.line} IF branch depth ${depth} does not match fallthrough depth ${frame.depthAtStart}`
              );
            }
          } else if (frame.branchDepth !== undefined && depth !== frame.branchDepth) {
            errors.push(
              `${definitionSource.name}:${token.line} ELSE branch depth ${depth} does not match IF branch depth ${frame.branchDepth}`
            );
          }

          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'BEGIN': {
          controlStack.push({ kind: 'begin', depthAtStart: depth, beginDepth: depth });
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'UNTIL': {
          const beginIndex = [...controlStack].reverse().findIndex((frame) => frame.kind === 'begin');
          if (beginIndex === -1) {
            errors.push(`${definitionSource.name}:${token.line} UNTIL without BEGIN`);
            appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
            continue;
          }

          ({ depth, minDepth } = applyEffect(depth, minDepth, 1, 0));

          const absoluteIndex = controlStack.length - beginIndex - 1;
          const beginFrame = controlStack[absoluteIndex];
          if (beginFrame.beginDepth !== undefined && depth !== beginFrame.beginDepth) {
            warnings.push(
              `${definitionSource.name}:${token.line} BEGIN...UNTIL body has net stack effect ${depth - beginFrame.beginDepth}`
            );
          }

          depth = beginFrame.beginDepth ?? depth;
          controlStack.splice(absoluteIndex, 1);
          appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
          continue;
        }
        case 'WHILE': {
          const beginIndex = [...controlStack].reverse().findIndex((frame) => frame.kind === 'begin');
          if (beginIndex === -1) {
            errors.push(`${definitionSource.name}:${token.line} WHILE without BEGIN`);
            appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
            continue;
          }

          ({ depth, minDepth } = applyEffect(depth, minDepth, 1, 0));

          const absoluteIndex = controlStack.length - beginIndex - 1;
          const beginFrame = controlStack[absoluteIndex];
          controlStack.push({
            kind: 'while',
            depthAtStart: beginFrame.depthAtStart,
            beginDepth: beginFrame.beginDepth,
            exitDepth: depth,
          });
          appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
          continue;
        }
        case 'REPEAT': {
          const whileFrame = controlStack.pop();
          if (!whileFrame || whileFrame.kind !== 'while') {
            errors.push(`${definitionSource.name}:${token.line} REPEAT without WHILE`);
            appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
            continue;
          }

          const beginIndex = [...controlStack].reverse().findIndex((frame) => frame.kind === 'begin');
          if (beginIndex === -1) {
            errors.push(`${definitionSource.name}:${token.line} REPEAT missing BEGIN`);
            appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
            continue;
          }

          const absoluteIndex = controlStack.length - beginIndex - 1;
          const beginFrame = controlStack[absoluteIndex];

          if (beginFrame.beginDepth !== undefined && depth !== beginFrame.beginDepth) {
            warnings.push(
              `${definitionSource.name}:${token.line} BEGIN...WHILE...REPEAT body has net stack effect ${depth - beginFrame.beginDepth}`
            );
          }

          depth = whileFrame.exitDepth ?? depth;
          controlStack.splice(absoluteIndex, 1);
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'DO': {
          ({ depth, minDepth } = applyEffect(depth, minDepth, 2, 0));
          controlStack.push({ kind: 'do', depthAtStart: depth });
          appendStep(steps, token, depthBefore, depth, minDepth, 2, 0);
          continue;
        }
        case 'LOOP': {
          const frame = controlStack.pop();
          if (!frame || frame.kind !== 'do') {
            errors.push(`${definitionSource.name}:${token.line} LOOP without DO`);
            appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
            continue;
          }

          if (depth !== frame.depthAtStart) {
            warnings.push(
              `${definitionSource.name}:${token.line} DO...LOOP body changes stack depth by ${depth - frame.depthAtStart}`
            );
          }

          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case '+LOOP': {
          const frame = controlStack.pop();
          if (!frame || frame.kind !== 'do') {
            errors.push(`${definitionSource.name}:${token.line} +LOOP without DO`);
            appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
            continue;
          }

          ({ depth, minDepth } = applyEffect(depth, minDepth, 1, 0));

          if (depth !== frame.depthAtStart) {
            warnings.push(
              `${definitionSource.name}:${token.line} DO...+LOOP body changes stack depth by ${depth - frame.depthAtStart}`
            );
          }

          appendStep(steps, token, depthBefore, depth, minDepth, 1, 0);
          continue;
        }
        case 'LEAVE': {
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'EXIT': {
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
          continue;
        }
        case 'RECURSE': {
          opaque = true;
          opaqueTokens.add('RECURSE');
          warnings.push(`${definitionSource.name}:${token.line} RECURSE treated as opaque during inference`);
          appendStep(steps, token, depthBefore, depth, minDepth, 0, 0, true);
          continue;
        }
        default:
          break;
      }
    }

    if (token.kind === 'number') {
      ({ depth, minDepth } = applyEffect(depth, minDepth, 0, 1));
      appendStep(steps, token, depthBefore, depth, minDepth, 0, 1);
      continue;
    }

    if (token.kind === 'sQuote') {
      ({ depth, minDepth } = applyEffect(depth, minDepth, 0, 2));
      appendStep(steps, token, depthBefore, depth, minDepth, 0, 2);
      continue;
    }

    if (token.kind === 'dotQuote') {
      appendStep(steps, token, depthBefore, depth, minDepth, 0, 0);
      continue;
    }

    const effect = effectDb[upper];
    if (!effect) {
      opaque = true;
      opaqueTokens.add(upper);
      warnings.push(`${definitionSource.name}:${token.line} Unknown/opaque word: ${token.text}`);
      appendStep(steps, token, depthBefore, depth, minDepth, 0, 0, true);
      continue;
    }

    ({ depth, minDepth } = applyEffect(depth, minDepth, effect.inputs, effect.outputs));
    if (effect.opaque) {
      opaque = true;
      opaqueTokens.add(upper);
    }

    appendStep(steps, token, depthBefore, depth, minDepth, effect.inputs, effect.outputs, effect.opaque);
  }

  if (controlStack.length > 0) {
    errors.push(`${definitionSource.name}: unclosed control structure(s) in definition`);
  }

  const inferredInputs = Math.max(0, -minDepth);
  const inferredOutputs = Math.max(0, depth + inferredInputs);

  const declared = parseDeclaredEffect(definitionSource.declaredEffect);
  const effect: StackEffect = {
    inputs: inferredInputs,
    outputs: inferredOutputs,
    inputLabels: declared?.inputs,
    outputLabels: declared?.outputs,
    verified: errors.length === 0 && !opaque,
    opaque,
  };

  if (declared) {
    if (declared.inputs.length !== inferredInputs || declared.outputs.length !== inferredOutputs) {
      warnings.push(
        `${definitionSource.name}: declared effect (${declared.inputs.length} -> ${declared.outputs.length}) differs from inferred (${inferredInputs} -> ${inferredOutputs})`
      );
    }

    // Use declared arity as a manual annotation if analysis is opaque.
    if (opaque) {
      effect.inputs = declared.inputs.length;
      effect.outputs = declared.outputs.length;
      effect.verified = false;
    }
  }

  return {
    name: definitionSource.name,
    startLine: definitionSource.startLine,
    endLine: definitionSource.endLine,
    declaredEffect: definitionSource.declaredEffect,
    effect,
    steps,
    errors,
    warnings,
    source: definitionSource.source,
    opaqueTokens: Array.from(opaqueTokens),
  };
}

export function analyzeSourceStackEffects(
  source: string,
  seedDatabase: StackEffectDatabase = createInitialEffectDatabase()
): SourceStackEffectResult {
  const definitions = parseDefinitionBlocks(source);
  const effectDb: StackEffectDatabase = { ...seedDatabase };
  const analyses: DefinitionAnalysis[] = [];

  for (const definition of definitions) {
    const analysis = analyzeDefinition(definition, effectDb);
    analyses.push(analysis);
    effectDb[definition.name.toUpperCase()] = analysis.effect;
  }

  return {
    definitions: analyses,
    effectDb,
  };
}

export function simulateTokenSequence(
  tokens: string[],
  initialDepth: number,
  effectDb: StackEffectDatabase
): { resultingDepth: number; minDepth: number; unknown: string[] } {
  let depth = initialDepth;
  let minDepth = initialDepth;
  const unknown: string[] = [];

  for (const token of tokens) {
    const upper = token.toUpperCase();
    const effect = effectDb[upper];

    if (effect) {
      depth -= effect.inputs;
      minDepth = Math.min(minDepth, depth);
      depth += effect.outputs;
      continue;
    }

    if (/^[+-]?\d+$/.test(token)) {
      depth += 1;
      continue;
    }

    unknown.push(token);
  }

  return {
    resultingDepth: depth,
    minDepth,
    unknown,
  };
}
