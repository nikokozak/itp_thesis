import { parseDefinitionBlocks } from '../utils/forth-parser';
import { parseDeclaredEffect } from './stack-effect';
import type { LabelPropagationResult, LabelStep, StackEffectDatabase } from './types';

interface LabelContext {
  tempIndex: number;
  tempNames: Record<string, string>;
}

function cloneLabels(labels: string[]): string[] {
  return [...labels];
}

function popLabel(stack: string[]): string {
  return stack.pop() ?? '?';
}

function pushLabel(stack: string[], label: string): void {
  stack.push(label);
}

function simplifyBinary(op: string, a: string, b: string): string {
  if (op === '*' && a === b) {
    return `${a}²`;
  }

  if (op === '+' && a === b) {
    return `2${a}`;
  }

  if (op === '-' && a === b) {
    return '0';
  }

  if (op === '*' && a === '1') {
    return b;
  }

  if (op === '*' && b === '1') {
    return a;
  }

  if (op === '+' && a === '0') {
    return b;
  }

  if (op === '+' && b === '0') {
    return a;
  }

  if (op === '*' && (a === '0' || b === '0')) {
    return '0';
  }

  return `${a}${op}${b}`;
}

function foldExpression(label: string, context: LabelContext): string {
  const depth = (label.match(/[+\-*/]/g) ?? []).length;
  if (depth <= 3 && label.length <= 26) {
    return label;
  }

  const key = `_t${context.tempIndex}`;
  context.tempIndex += 1;
  context.tempNames[key] = label;
  return key;
}

function applyKnownOperation(token: string, stack: string[], context: LabelContext): boolean {
  switch (token) {
    case 'DUP': {
      const a = popLabel(stack);
      pushLabel(stack, a);
      pushLabel(stack, a);
      return true;
    }
    case 'DROP': {
      popLabel(stack);
      return true;
    }
    case 'SWAP': {
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, b);
      pushLabel(stack, a);
      return true;
    }
    case 'OVER': {
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, a);
      pushLabel(stack, b);
      pushLabel(stack, a);
      return true;
    }
    case 'ROT': {
      const c = popLabel(stack);
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, b);
      pushLabel(stack, c);
      pushLabel(stack, a);
      return true;
    }
    case '-ROT': {
      const c = popLabel(stack);
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, c);
      pushLabel(stack, a);
      pushLabel(stack, b);
      return true;
    }
    case 'NIP': {
      const b = popLabel(stack);
      popLabel(stack);
      pushLabel(stack, b);
      return true;
    }
    case 'TUCK': {
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, b);
      pushLabel(stack, a);
      pushLabel(stack, b);
      return true;
    }
    case '+':
    case '-':
    case '*':
    case '/':
    case 'MOD': {
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, foldExpression(simplifyBinary(token === 'MOD' ? '%' : token, a, b), context));
      return true;
    }
    case 'NEGATE': {
      const a = popLabel(stack);
      pushLabel(stack, foldExpression(`-${a}`, context));
      return true;
    }
    case 'ABS': {
      const a = popLabel(stack);
      pushLabel(stack, foldExpression(`|${a}|`, context));
      return true;
    }
    case '=':
    case '<>':
    case '<':
    case '>':
    case '<=':
    case '>=': {
      const b = popLabel(stack);
      const a = popLabel(stack);
      pushLabel(stack, `${a}${token}${b}?`);
      return true;
    }
    case '0=':
    case '0<':
    case '0>': {
      const a = popLabel(stack);
      const comparator = token.slice(1);
      pushLabel(stack, `${a}${comparator}?`);
      return true;
    }
    case '@': {
      const a = popLabel(stack);
      pushLabel(stack, `[${a}]`);
      return true;
    }
    case '!': {
      popLabel(stack);
      popLabel(stack);
      return true;
    }
    case 'S"': {
      const id = `_s${context.tempIndex}`;
      context.tempIndex += 1;
      pushLabel(stack, `${id}.addr`);
      pushLabel(stack, `${id}.len`);
      return true;
    }
    case 'COUNT': {
      const a = popLabel(stack);
      pushLabel(stack, `${a}+1`);
      pushLabel(stack, `len(${a})`);
      return true;
    }
    case 'DEPTH': {
      pushLabel(stack, 'depth');
      return true;
    }
    default:
      return false;
  }
}

function applyGenericEffect(token: string, stack: string[], effectDb: StackEffectDatabase, context: LabelContext): void {
  const effect = effectDb[token];
  if (!effect) {
    pushLabel(stack, foldExpression(`?${token.toLowerCase()}`, context));
    return;
  }

  for (let i = 0; i < effect.inputs; i += 1) {
    popLabel(stack);
  }

  if (effect.outputs === 0) {
    return;
  }

  if (effect.outputs === 1) {
    pushLabel(stack, foldExpression(`${token.toLowerCase()}(...)`, context));
    return;
  }

  for (let i = 0; i < effect.outputs; i += 1) {
    pushLabel(stack, foldExpression(`${token.toLowerCase()}#${i + 1}`, context));
  }
}

export function propagateLabelsForSource(
  source: string,
  effectDb: StackEffectDatabase
): LabelPropagationResult[] {
  const definitions = parseDefinitionBlocks(source);

  return definitions.map((definition) => {
    const declared = parseDeclaredEffect(definition.declaredEffect);
    const labels = declared?.inputs?.length
      ? [...declared.inputs]
      : Array.from({ length: effectDb[definition.name.toUpperCase()]?.inputs ?? 0 }, (_, idx) => `in${idx + 1}`);

    const context: LabelContext = {
      tempIndex: 1,
      tempNames: {},
    };

    const steps: LabelStep[] = [];
    for (const token of definition.body) {
      const upper = token.text.toUpperCase();
      const before = cloneLabels(labels);

      if (token.kind === 'number') {
        labels.push(token.text);
      } else if (token.kind === 'sQuote') {
        const id = `_s${context.tempIndex}`;
        context.tempIndex += 1;
        labels.push(`${id}.addr`);
        labels.push(`${id}.len`);
      } else if (token.kind === 'dotQuote') {
        // Output only.
      } else if (!applyKnownOperation(upper, labels, context)) {
        applyGenericEffect(upper, labels, effectDb, context);
      }

      steps.push({
        token,
        before,
        after: cloneLabels(labels),
      });
    }

    return {
      word: definition.name,
      startLine: definition.startLine,
      endLine: definition.endLine,
      steps,
      finalLabels: cloneLabels(labels),
      tempNames: context.tempNames,
    };
  });
}

export function mapLabelsByLine(result: LabelPropagationResult): Map<number, string[]> {
  const byLine = new Map<number, string[]>();
  for (const step of result.steps) {
    byLine.set(step.token.line, step.after);
  }
  return byLine;
}
