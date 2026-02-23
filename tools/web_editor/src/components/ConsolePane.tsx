import { useEffect, useRef } from 'react';

interface ConsolePaneProps {
  outputLog: string[];
  lastError?: string;
  onClear: () => void;
}

export function ConsolePane({ outputLog, lastError, onClear }: ConsolePaneProps) {
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputLog]);

  return (
    <div className="console-pane">
      <div className="panel-header">
        <span>Console</span>
        <div className="panel-header-actions">
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(outputLog.join('\n'));
            }}
            disabled={outputLog.length === 0}
          >
            Copy All
          </button>
          <button type="button" onClick={onClear} disabled={outputLog.length === 0}>
            Clear
          </button>
        </div>
      </div>

      <div className="repl-output console-output" ref={outputRef}>
        {outputLog.length === 0 ? <div className="muted">No output yet.</div> : null}
        {outputLog.map((line, index) => (
          <div key={`${line}-${index}`} className="repl-line">
            {line}
          </div>
        ))}
      </div>

      {lastError ? <div className="error-text console-error">{lastError}</div> : null}
    </div>
  );
}

