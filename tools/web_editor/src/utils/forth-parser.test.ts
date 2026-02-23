import { describe, expect, it } from 'vitest';
import { parseDefinitionBlocks, tokenizeForth } from './forth-parser';

describe('forth parser/tokenizer', () => {
  it('handles comments and quoted strings while preserving token offsets', () => {
    const source = `\\ line comment\n: SAY ( x -- ) ." hello" S" world" ;`;
    const tokens = tokenizeForth(source);

    expect(tokens.some((token) => token.text === ':')).toBe(true);
    expect(tokens.some((token) => token.kind === 'dotQuote' && token.value === 'hello')).toBe(true);
    expect(tokens.some((token) => token.kind === 'sQuote' && token.value === 'world')).toBe(true);

    for (let i = 1; i < tokens.length; i += 1) {
      expect(tokens[i].start).toBeGreaterThanOrEqual(tokens[i - 1].end);
      expect(tokens[i].line).toBeGreaterThanOrEqual(tokens[i - 1].line);
    }
  });

  it('extracts multiple colon definitions with declared stack effects', () => {
    const source = `: SQUARE ( x -- x2 ) DUP * ;\n: INC ( n -- n1 ) 1 + ;`;
    const definitions = parseDefinitionBlocks(source);

    expect(definitions).toHaveLength(2);
    expect(definitions[0].name).toBe('SQUARE');
    expect(definitions[0].declaredEffect).toBe('x -- x2');
    expect(definitions[1].name).toBe('INC');
    expect(definitions[1].declaredEffect).toBe('n -- n1');
  });

  it('classifies signed and base-friendly tokens as numbers', () => {
    const tokens = tokenizeForth('-1 +7 FF G1');
    const kinds = tokens.map((token) => ({ text: token.text, kind: token.kind }));

    expect(kinds).toEqual([
      { text: '-1', kind: 'number' },
      { text: '+7', kind: 'number' },
      { text: 'FF', kind: 'number' },
      { text: 'G1', kind: 'word' },
    ]);
  });
});
