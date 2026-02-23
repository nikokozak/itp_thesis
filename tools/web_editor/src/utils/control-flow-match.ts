/**
 * Control-flow bracket matching for Forth source.
 *
 * Given source text and a cursor position, returns the character positions
 * of all matching control-flow keywords (IF/ELSE/THEN, DO/LOOP, BEGIN/UNTIL etc.)
 */

interface TokenSpan {
  word: string;
  from: number;
  to: number;
}

function tokenize(text: string): TokenSpan[] {
  const tokens: TokenSpan[] = [];
  const regex = /[^\s]+/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    tokens.push({
      word: match[0].toUpperCase(),
      from: match.index,
      to: match.index + match[0].length,
    });
  }
  return tokens;
}

const CONTROL_WORDS = new Set([
  'IF', 'ELSE', 'THEN',
  'DO', 'LOOP', '+LOOP',
  'BEGIN', 'UNTIL', 'WHILE', 'REPEAT',
]);

/**
 * Find all matching control-flow partners for the keyword at the cursor position.
 * Returns an array of { from, to } spans for the matched keywords (including the one
 * under the cursor).
 */
export function findControlFlowMatches(
  text: string,
  cursorPos: number
): Array<{ from: number; to: number }> {
  const tokens = tokenize(text);

  // Find the token under cursor
  const cursorToken = tokens.find((t) => cursorPos >= t.from && cursorPos <= t.to);
  if (!cursorToken || !CONTROL_WORDS.has(cursorToken.word)) {
    return [];
  }

  // Build control-flow groups using a stack-based approach
  const groups: TokenSpan[][] = [];

  // IF/ELSE/THEN matching
  const ifStack: TokenSpan[][] = [];
  // DO/LOOP matching
  const doStack: TokenSpan[][] = [];
  // BEGIN/UNTIL|WHILE/REPEAT matching
  const beginStack: TokenSpan[][] = [];

  for (const token of tokens) {
    switch (token.word) {
      case 'IF':
        ifStack.push([token]);
        break;
      case 'ELSE':
        if (ifStack.length > 0) {
          ifStack[ifStack.length - 1].push(token);
        }
        break;
      case 'THEN':
        if (ifStack.length > 0) {
          const group = ifStack.pop()!;
          group.push(token);
          groups.push(group);
        }
        break;
      case 'DO':
        doStack.push([token]);
        break;
      case 'LOOP':
      case '+LOOP':
        if (doStack.length > 0) {
          const group = doStack.pop()!;
          group.push(token);
          groups.push(group);
        }
        break;
      case 'BEGIN':
        beginStack.push([token]);
        break;
      case 'UNTIL':
        if (beginStack.length > 0) {
          const group = beginStack.pop()!;
          group.push(token);
          groups.push(group);
        }
        break;
      case 'WHILE':
        if (beginStack.length > 0) {
          beginStack[beginStack.length - 1].push(token);
        }
        break;
      case 'REPEAT':
        if (beginStack.length > 0) {
          const group = beginStack.pop()!;
          group.push(token);
          groups.push(group);
        }
        break;
    }
  }

  // Find the group containing the cursor token
  for (const group of groups) {
    if (group.some((t) => t.from === cursorToken.from)) {
      return group.map((t) => ({ from: t.from, to: t.to }));
    }
  }

  return [];
}
