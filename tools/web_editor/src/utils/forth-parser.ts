export type ForthTokenKind = 'word' | 'number' | 'sQuote' | 'dotQuote';

export interface ForthToken {
  kind: ForthTokenKind;
  text: string;
  value?: string;
  line: number;
  column: number;
  start: number;
  end: number;
}

export interface DefinitionBlock {
  name: string;
  nameToken: ForthToken;
  body: ForthToken[];
  startLine: number;
  endLine: number;
  startOffset: number;
  endOffset: number;
  source: string;
  declaredEffect?: string;
}

function isWhitespace(char: string): boolean {
  return char === ' ' || char === '\t' || char === '\n' || char === '\r';
}

function looksLikeNumber(word: string): boolean {
  if (/^[+-]?\d+$/.test(word)) {
    return true;
  }

  // Allow hex-like tokens when BASE is 16 (engine decides final parse validity).
  return /^[+-]?[0-9A-Fa-f]+$/.test(word);
}

function readQuoted(source: string, from: number): { value: string; end: number } {
  let i = from;
  while (i < source.length && source[i] === ' ') {
    i += 1;
  }

  const start = i;
  while (i < source.length && source[i] !== '"') {
    i += 1;
  }

  return {
    value: source.slice(start, i),
    end: i < source.length ? i + 1 : i,
  };
}

export function tokenizeForth(source: string): ForthToken[] {
  const tokens: ForthToken[] = [];

  let i = 0;
  let line = 1;
  let column = 1;

  while (i < source.length) {
    const ch = source[i];

    if (ch === '\n') {
      i += 1;
      line += 1;
      column = 1;
      continue;
    }

    if (ch === '\r') {
      i += 1;
      continue;
    }

    if (isWhitespace(ch)) {
      i += 1;
      column += 1;
      continue;
    }

    // Backslash comments consume rest of line.
    if (ch === '\\') {
      while (i < source.length && source[i] !== '\n') {
        i += 1;
        column += 1;
      }
      continue;
    }

    // Parenthesized comments are skipped.
    if (ch === '(') {
      i += 1;
      column += 1;
      while (i < source.length && source[i] !== ')') {
        if (source[i] === '\n') {
          line += 1;
          column = 1;
          i += 1;
        } else {
          i += 1;
          column += 1;
        }
      }
      if (i < source.length && source[i] === ')') {
        i += 1;
        column += 1;
      }
      continue;
    }

    // S" ..."
    if ((ch === 'S' || ch === 's') && source[i + 1] === '"') {
      const start = i;
      const startLine = line;
      const startColumn = column;
      i += 2;
      column += 2;

      const quoted = readQuoted(source, i);
      const consumed = source.slice(i, quoted.end);
      for (const char of consumed) {
        if (char === '\n') {
          line += 1;
          column = 1;
        } else {
          column += 1;
        }
      }
      i = quoted.end;

      tokens.push({
        kind: 'sQuote',
        text: 'S"',
        value: quoted.value,
        line: startLine,
        column: startColumn,
        start,
        end: i,
      });
      continue;
    }

    // ." ..."
    if (ch === '.' && source[i + 1] === '"') {
      const start = i;
      const startLine = line;
      const startColumn = column;
      i += 2;
      column += 2;

      const quoted = readQuoted(source, i);
      const consumed = source.slice(i, quoted.end);
      for (const char of consumed) {
        if (char === '\n') {
          line += 1;
          column = 1;
        } else {
          column += 1;
        }
      }
      i = quoted.end;

      tokens.push({
        kind: 'dotQuote',
        text: '."',
        value: quoted.value,
        line: startLine,
        column: startColumn,
        start,
        end: i,
      });
      continue;
    }

    const start = i;
    const startLine = line;
    const startColumn = column;

    while (i < source.length && !isWhitespace(source[i])) {
      if (source[i] === '\\' || source[i] === '(') {
        break;
      }
      i += 1;
      column += 1;
    }

    const text = source.slice(start, i);
    if (!text) {
      continue;
    }

    tokens.push({
      kind: looksLikeNumber(text) ? 'number' : 'word',
      text,
      line: startLine,
      column: startColumn,
      start,
      end: i,
    });
  }

  return tokens;
}

export function extractStackEffectComment(source: string): string | undefined {
  const match = source.match(/\(([^)]*--[^)]*)\)/);
  if (!match) {
    return undefined;
  }
  return match[1].trim();
}

export function parseDefinitionBlocks(source: string): DefinitionBlock[] {
  const tokens = tokenizeForth(source);
  const definitions: DefinitionBlock[] = [];

  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    if (token.kind === 'word' && token.text === ':') {
      const nameToken = tokens[i + 1];
      if (!nameToken || nameToken.kind !== 'word') {
        i += 1;
        continue;
      }

      let endIndex = -1;
      for (let j = i + 2; j < tokens.length; j += 1) {
        const candidate = tokens[j];
        if (candidate.kind === 'word' && candidate.text === ';') {
          endIndex = j;
          break;
        }
      }

      if (endIndex === -1) {
        break;
      }

      const body = tokens.slice(i + 2, endIndex);
      const startOffset = token.start;
      const endOffset = tokens[endIndex].end;
      const definitionSource = source.slice(startOffset, endOffset);

      definitions.push({
        name: nameToken.text,
        nameToken,
        body,
        startLine: token.line,
        endLine: tokens[endIndex].line,
        startOffset,
        endOffset,
        source: definitionSource,
        declaredEffect: extractStackEffectComment(definitionSource),
      });

      i = endIndex + 1;
      continue;
    }

    i += 1;
  }

  return definitions;
}

export function tokenTextUpper(token: ForthToken): string {
  return token.text.toUpperCase();
}
