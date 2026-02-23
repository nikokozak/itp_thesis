import { forwardRef, useEffect, useMemo, useRef, useState } from 'react';
import { tokenizeForth } from '../utils/forth-parser';
import type { StackEffectDatabase } from '../analysis/types';
import { useEngineStore } from '../store/engine-store';

interface ReplProps {
  effectDb: StackEffectDatabase;
  onInspectWord: (word: string) => void;
}

function parseNumeric(label: string): number | undefined {
  if (!/^[+-]?\d+$/.test(label)) {
    return undefined;
  }
  const parsed = Number(label);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  return parsed;
}

function asValueLabel(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}

function applyPreviewOperation(token: string, stack: string[], effectDb: StackEffectDatabase): void {
  const upper = token.toUpperCase();

  switch (upper) {
    case 'DUP': {
      stack.push(stack[stack.length - 1] ?? '?');
      return;
    }
    case 'DROP': {
      stack.pop();
      return;
    }
    case 'SWAP': {
      const b = stack.pop() ?? '?';
      const a = stack.pop() ?? '?';
      stack.push(b, a);
      return;
    }
    case '+':
    case '-':
    case '*':
    case '/': {
      const b = stack.pop() ?? '?';
      const a = stack.pop() ?? '?';
      const av = parseNumeric(a);
      const bv = parseNumeric(b);
      if (av !== undefined && bv !== undefined) {
        const value =
          upper === '+'
            ? av + bv
            : upper === '-'
              ? av - bv
              : upper === '*'
                ? av * bv
                : bv === 0
                  ? NaN
                  : Math.trunc(av / bv);
        stack.push(Number.isFinite(value) ? asValueLabel(value) : '?');
      } else {
        stack.push('?');
      }
      return;
    }
    default:
      break;
  }

  const effect = effectDb[upper];
  if (!effect) {
    stack.push('?');
    return;
  }

  for (let i = 0; i < effect.inputs; i += 1) {
    stack.pop();
  }

  for (let i = 0; i < effect.outputs; i += 1) {
    stack.push('?');
  }
}

function previewLine(line: string, currentStack: number[], effectDb: StackEffectDatabase): string[] {
  const stack = currentStack.map((value) => asValueLabel(value));

  const tokens = tokenizeForth(line);
  for (const token of tokens) {
    if (token.kind === 'number') {
      stack.push(token.text);
      continue;
    }

    if (token.kind === 'sQuote') {
      stack.push('addr');
      stack.push('len');
      continue;
    }

    if (token.kind === 'dotQuote') {
      continue;
    }

    applyPreviewOperation(token.text, stack, effectDb);
  }

  return stack;
}

export const REPL = forwardRef<HTMLInputElement, ReplProps>(function REPL(
  { effectDb, onInspectWord },
  ref
) {
  const runReplLine = useEngineStore((state) => state.runReplLine);
  const dataStack = useEngineStore((state) => state.dataStack);
  const outputLog = useEngineStore((state) => state.outputLog);
  const lastError = useEngineStore((state) => state.lastError);
  const undoRuntime = useEngineStore((state) => state.undoRuntime);
  const redoRuntime = useEngineStore((state) => state.redoRuntime);

  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [localError, setLocalError] = useState<string>();
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputLog]);

  const preview = useMemo(() => {
    if (!input.trim()) {
      return [];
    }
    return previewLine(input, dataStack, effectDb);
  }, [dataStack, effectDb, input]);

  const submit = () => {
    const text = input.trim();
    if (!text) {
      return;
    }

    const inspectMatch = text.match(/^INSPECT\s+(.+)$/i);
    if (inspectMatch) {
      const word = inspectMatch[1].trim();
      if (word) {
        onInspectWord(word);
      }
      setHistory((current) => [...current, text]);
      setHistoryIndex(-1);
      setInput('');
      setLocalError(undefined);
      return;
    }

    const result = runReplLine(text);
    setHistory((current) => [...current, text]);
    setHistoryIndex(-1);
    setInput('');
    setLocalError(result.ok ? undefined : result.error);
  };

  return (
    <div className="repl-pane">
      <div className="panel-header">
        <span>REPL</span>
        <span className="hint">Enter executes. Up/Down history. Ctrl+Z runtime undo.</span>
      </div>

      <div className="repl-output" ref={outputRef}>
        {outputLog.length === 0 ? <div className="muted">No output yet.</div> : null}
        {outputLog.map((line, index) => (
          <div key={`${line}-${index}`} className="repl-line">
            {line}
          </div>
        ))}
      </div>

      <div className="repl-preview">
        {preview.length > 0 ? <span>preview stack: [ {preview.join(' ')} ]</span> : <span>&nbsp;</span>}
      </div>

      <div className="repl-input-row">
        <input
          ref={ref}
          className="repl-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              submit();
              return;
            }

            if (event.key === 'ArrowUp') {
              event.preventDefault();
              if (history.length === 0) {
                return;
              }

              const nextIndex = historyIndex < 0 ? history.length - 1 : Math.max(0, historyIndex - 1);
              setHistoryIndex(nextIndex);
              setInput(history[nextIndex]);
              return;
            }

            if (event.key === 'ArrowDown') {
              event.preventDefault();
              if (history.length === 0) {
                return;
              }

              if (historyIndex < 0) {
                return;
              }

              const nextIndex = Math.min(history.length, historyIndex + 1);
              if (nextIndex === history.length) {
                setHistoryIndex(-1);
                setInput('');
                return;
              }

              setHistoryIndex(nextIndex);
              setInput(history[nextIndex]);
            }

            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.shiftKey) {
              event.preventDefault();
              undoRuntime();
              return;
            }

            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && event.shiftKey) {
              event.preventDefault();
              redoRuntime();
            }
          }}
          placeholder="Type Forth here..."
        />
        <button type="button" onClick={submit}>
          Run
        </button>
      </div>

      {localError || lastError ? <div className="error-text">{localError ?? lastError}</div> : null}
    </div>
  );
});
