import { useState } from 'react';
import { useEngineStore } from '../store/engine-store';
import { useUiStore } from '../store/ui-store';

function renderStack(values?: number[]): string {
  if (!values || values.length === 0) {
    return '<empty>';
  }
  return `[ ${values.join(' ')} ]`;
}

export function WatchPanel() {
  const watchExpressions = useUiStore((state) => state.watchExpressions);
  const addWatchExpression = useUiStore((state) => state.addWatchExpression);
  const updateWatchExpression = useUiStore((state) => state.updateWatchExpression);
  const removeWatchExpression = useUiStore((state) => state.removeWatchExpression);

  const evaluateWatchExpression = useEngineStore((state) => state.evaluateWatchExpression);
  const latestSeq = useEngineStore((state) => state.events[state.events.length - 1]?.sequenceNumber ?? 0);

  const [draft, setDraft] = useState('');

  const evaluations = watchExpressions.map((expression) => evaluateWatchExpression(expression));

  return (
    <div className="watch-pane">
      <div className="panel-header">
        <span>Watch</span>
        <span className="hint">Read-only probes, refreshed at seq {latestSeq}.</span>
      </div>

      <div className="watch-add-row">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addWatchExpression(draft);
              setDraft('');
            }
          }}
          placeholder="Add watch expression, e.g. DEPTH or HERE"
        />
        <button
          type="button"
          onClick={() => {
            addWatchExpression(draft);
            setDraft('');
          }}
        >
          Add
        </button>
      </div>

      <div className="watch-list">
        {watchExpressions.length === 0 ? (
          <div className="muted watch-empty">No watch expressions yet.</div>
        ) : null}

        {watchExpressions.map((expression, index) => {
          const evaluation = evaluations[index];
          return (
            <div key={`${index}-${expression}`} className="watch-item">
              <div className="watch-item-controls">
                <input
                  className="watch-expression-input"
                  value={expression}
                  onChange={(event) => updateWatchExpression(index, event.target.value)}
                  placeholder="watch expression"
                />
                <button type="button" onClick={() => removeWatchExpression(index)}>
                  Remove
                </button>
              </div>

              {evaluation?.ok ? (
                <div className="watch-result">
                  <span>
                    top: {evaluation.top !== undefined ? evaluation.top : '<empty>'}
                  </span>
                  <span>stack: {renderStack(evaluation.stack)}</span>
                </div>
              ) : (
                <div className="watch-result error-text">{evaluation?.error ?? 'Invalid watch expression'}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
