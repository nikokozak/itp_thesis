import { useEffect, useMemo, useState } from 'react';
import type { StackEffectDatabase, XRefEntry } from '../analysis/types';
import type { WordEntry } from '../engine/types';

interface WordInspectorProps {
  selectedWord?: string;
  dictionary: WordEntry[];
  effects: StackEffectDatabase;
  xref: Record<string, XRefEntry>;
  onSelectWord: (word: string) => void;
  onSetDocumentation: (word: string, doc: string) => void;
  onGoToDefinition?: (globalLine: number) => void;
}

function effectLabel(effect?: { inputs: number; outputs: number; opaque?: boolean }, hasSig?: boolean): string {
  if (!effect) {
    return '?';
  }

  const tag = hasSig ? '' : effect.opaque ? ' opaque' : '';
  return `(${effect.inputs} -> ${effect.outputs})${tag}`;
}

function pickDefaultWordUpper(dictionary: WordEntry[], xref: Record<string, XRefEntry>): string | undefined {
  const defined = Object.values(xref)
    .filter((entry) => entry.definedAt > 0)
    .sort((a, b) => a.definedAt - b.definedAt)[0];
  if (defined) {
    return defined.word.toUpperCase();
  }

  const compiled = dictionary.find((word) => word.type === 'compiled');
  if (compiled) {
    return compiled.name.toUpperCase();
  }

  return dictionary[0]?.name.toUpperCase();
}

export function WordInspector({
  selectedWord,
  dictionary,
  effects,
  xref,
  onSelectWord,
  onSetDocumentation,
  onGoToDefinition,
}: WordInspectorProps) {
  const resolvedUpper = useMemo(() => {
    if (selectedWord) {
      return selectedWord.toUpperCase();
    }
    return pickDefaultWordUpper(dictionary, xref);
  }, [dictionary, selectedWord, xref]);

  const xrefEntry = resolvedUpper ? xref[resolvedUpper] : undefined;
  const runtimeEntry = useMemo(
    () => (resolvedUpper ? dictionary.find((word) => word.name.toUpperCase() === resolvedUpper) : undefined),
    [dictionary, resolvedUpper]
  );
  const effect = resolvedUpper ? effects[resolvedUpper] : undefined;
  const hasSig = runtimeEntry?.type === 'primitive' || !!xrefEntry?.declaredEffect;
  const resolvedName = xrefEntry?.word ?? runtimeEntry?.name ?? resolvedUpper;

  const [docDraft, setDocDraft] = useState('');

  useEffect(() => {
    setDocDraft(xrefEntry?.documentation ?? runtimeEntry?.documentation ?? '');
  }, [runtimeEntry?.documentation, xrefEntry?.documentation]);

  if (!resolvedUpper || !resolvedName) {
    return (
      <div className="inspector-pane">
        <div className="panel-header">
          <span>Word Inspector</span>
        </div>
        <div className="muted">No word selected.</div>
      </div>
    );
  }

  return (
    <div className="inspector-pane">
      <div className="panel-header">
        <span>Word Inspector</span>
        <span className="hint">Select from dictionary/outline, or place cursor on a word in code.</span>
      </div>

      <div className="inspector-grid">
        <div>
          <strong>Name</strong>
          <div>{resolvedName}</div>
        </div>
        <div>
          <strong>Kind</strong>
          <div>{runtimeEntry?.type ?? (xrefEntry?.definedAt ? 'compiled' : 'unknown')}</div>
        </div>
        <div>
          <strong>Stack effect</strong>
          <div>{effectLabel(effect, hasSig)}</div>
        </div>
        <div>
          <strong>Calls (runtime)</strong>
          <div>{runtimeEntry?.callCount ?? '-'}</div>
        </div>
      </div>

      {xrefEntry?.definedAt ? (
        <div className="inspector-section">
          <strong>Definition</strong>
          <div className="inspector-definition-row">
            <span>Defined at line {xrefEntry.definedAt}</span>
            {onGoToDefinition ? (
              <button type="button" onClick={() => onGoToDefinition(xrefEntry.definedAt)}>
                Go to Definition
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="inspector-section">
        <strong>Documentation</strong>
        <textarea
          value={docDraft}
          onChange={(event) => setDocDraft(event.target.value)}
          placeholder="Describe intent, assumptions, and usage."
        />
        <button type="button" onClick={() => onSetDocumentation(resolvedName, docDraft)}>
          Save Doc
        </button>
      </div>

      <div className="inspector-section">
        <strong>Source</strong>
        <pre>
          {xrefEntry?.source
            ? xrefEntry.source
            : runtimeEntry?.type === 'primitive'
              ? '<primitive>'
              : runtimeEntry?.sourceTokens
                ? `: ${runtimeEntry.name} ${runtimeEntry.sourceTokens.join(' ')} ;`
                : '<unknown>'}
        </pre>
      </div>

      <div className="inspector-section two-col">
        <div>
          <strong>Callers</strong>
          <div className="word-link-list">
            {(xrefEntry?.callers ?? []).map((caller) => (
              <button type="button" key={caller} onClick={() => onSelectWord(caller)}>
                {caller}
              </button>
            ))}
            {(xrefEntry?.callers?.length ?? 0) === 0 ? <span className="muted">None</span> : null}
          </div>
        </div>

        <div>
          <strong>Callees</strong>
          <div className="word-link-list">
            {(xrefEntry?.callees ?? []).map((callee) => (
              <button type="button" key={callee} onClick={() => onSelectWord(callee)}>
                {callee}
              </button>
            ))}
            {(xrefEntry?.callees?.length ?? 0) === 0 ? <span className="muted">None</span> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

