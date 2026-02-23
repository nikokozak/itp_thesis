import { parseDefinitionBlocks } from '../utils/forth-parser';
import type { StackEffect, XRefEntry } from './types';

const IGNORED_CALLEES = new Set([
  ':',
  ';',
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

export function buildCrossReference(
  source: string,
  effectDb: Record<string, StackEffect>,
  docs: Record<string, string> = {}
): Record<string, XRefEntry> {
  const definitions = parseDefinitionBlocks(source);
  const xref: Record<string, XRefEntry> = {};

  const ensure = (word: string): XRefEntry => {
    const upper = word.toUpperCase();
    if (!xref[upper]) {
      xref[upper] = {
        word,
        callers: [],
        callees: [],
        definedAt: 0,
        documentation: docs[upper],
        stackEffect: effectDb[upper],
      };
    }
    return xref[upper];
  };

  for (const definition of definitions) {
    const entry = ensure(definition.name);
    entry.definedAt = definition.startLine;
    entry.source = definition.source;
    entry.stackEffect = effectDb[definition.name.toUpperCase()];

    const calleeSet = new Set<string>();
    for (const token of definition.body) {
      if (token.kind !== 'word') {
        continue;
      }

      const upper = token.text.toUpperCase();
      if (IGNORED_CALLEES.has(upper)) {
        continue;
      }

      calleeSet.add(upper);
      const calleeEntry = ensure(token.text);
      if (!calleeEntry.callers.includes(definition.name)) {
        calleeEntry.callers.push(definition.name);
      }
    }

    entry.callees = Array.from(calleeSet.values()).map((name) => ensure(name).word);
  }

  for (const value of Object.values(xref)) {
    value.callers.sort();
    value.callees.sort();
  }

  return xref;
}
