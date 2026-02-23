import { useMemo, useRef, useState } from 'react';
import { fileForGlobalLine } from '../utils/workspace-source';
import { useAnalysisStore } from '../store/analysis-store';
import { useUiStore } from '../store/ui-store';
import { useWorkspaceStore } from '../store/workspace-store';

function effectSummary(effect?: { inputs: number; outputs: number }): string {
  if (!effect) {
    return '?';
  }
  return `${effect.inputs} -> ${effect.outputs}`;
}

export function ProjectPanel() {
  const files = useWorkspaceStore((state) => state.files);
  const activeFileId = useWorkspaceStore((state) => state.activeFileId);
  const setActiveFile = useWorkspaceStore((state) => state.setActiveFile);
  const createFile = useWorkspaceStore((state) => state.createFile);
  const renameFile = useWorkspaceStore((state) => state.renameFile);
  const deleteFile = useWorkspaceStore((state) => state.deleteFile);
  const moveFile = useWorkspaceStore((state) => state.moveFile);
  const exportWorkspace = useWorkspaceStore((state) => state.exportWorkspace);
  const importWorkspace = useWorkspaceStore((state) => state.importWorkspace);
  const resetWorkspace = useWorkspaceStore((state) => state.resetWorkspace);
  const externalWords = useWorkspaceStore((state) => state.externalWords);
  const upsertExternalWord = useWorkspaceStore((state) => state.upsertExternalWord);
  const removeExternalWord = useWorkspaceStore((state) => state.removeExternalWord);

  const analyses = useAnalysisStore((state) => state.analyses);
  const diagnostics = useAnalysisStore((state) => state.diagnostics);
  const sourceMap = useAnalysisStore((state) => state.sourceMap);
  const setSelectedWord = useAnalysisStore((state) => state.setSelectedWord);

  const requestEditorFocus = useUiStore((state) => state.requestEditorFocus);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string>();
  const [renamingFileId, setRenamingFileId] = useState<string>();
  const [renameDraft, setRenameDraft] = useState('');

  const [externalDraftWord, setExternalDraftWord] = useState('');
  const [externalDraftInputs, setExternalDraftInputs] = useState('0');
  const [externalDraftOutputs, setExternalDraftOutputs] = useState('0');

  const problems = useMemo(() => {
    if (!sourceMap) {
      return [];
    }

    return diagnostics
      .map((diagnostic) => {
        const loc = fileForGlobalLine(sourceMap, diagnostic.line);
        if (!loc) {
          return undefined;
        }
        return {
          ...diagnostic,
          fileId: loc.fileId,
          fileName: loc.fileName,
          fileLine: loc.fileLine,
        };
      })
      .filter(Boolean) as Array<
      (typeof diagnostics)[number] & { fileId: string; fileName: string; fileLine: number }
    >;
  }, [diagnostics, sourceMap]);

  const outline = useMemo(() => {
    if (!sourceMap) {
      return [];
    }

    return analyses
      .map((analysis) => {
        const loc = fileForGlobalLine(sourceMap, analysis.startLine);
        if (!loc) {
          return undefined;
        }
        return {
          ...analysis,
          fileId: loc.fileId,
          fileName: loc.fileName,
          fileLine: loc.fileLine,
        };
      })
      .filter(Boolean) as Array<
      (typeof analyses)[number] & { fileId: string; fileName: string; fileLine: number }
    >;
  }, [analyses, sourceMap]);

  const externalList = useMemo(() => {
    return Object.values(externalWords).sort((a, b) => a.word.localeCompare(b.word));
  }, [externalWords]);

  const issueCounts = useMemo(() => {
    let errors = 0;
    let warnings = 0;
    for (const problem of problems) {
      if (problem.severity === 'error') {
        errors += 1;
      } else {
        warnings += 1;
      }
    }
    return { errors, warnings };
  }, [problems]);

  return (
    <div className="project-pane">
      <div className="panel-header">
        <span>Project</span>
        <div className="panel-header-actions">
          <button
            type="button"
            onClick={() => {
              const payload = exportWorkspace();
              const json = JSON.stringify(payload, null, 2);
              const blob = new Blob([json], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'bedrock-workspace.json';
              a.click();
              URL.revokeObjectURL(url);
            }}
            title="Export files + docs + external word stubs"
          >
            Export
          </button>
          <button type="button" onClick={() => fileInputRef.current?.click()} title="Import a previously exported workspace">
            Import
          </button>
          <button
            type="button"
            onClick={() => {
              const ok = window.confirm('Reset workspace to the default example project?');
              if (ok) {
                resetWorkspace();
              }
            }}
            title="Reset to the default example project"
          >
            Reset
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/json"
        className="sr-only"
        onChange={async (event) => {
          setImportError(undefined);
          const file = event.target.files?.[0];
          if (!file) {
            return;
          }
          try {
            const text = await file.text();
            const parsed = JSON.parse(text);
            const result = importWorkspace(parsed);
            if (!result.ok) {
              setImportError(result.error ?? 'Import failed');
            }
          } catch (error) {
            setImportError(error instanceof Error ? error.message : 'Import failed');
          } finally {
            event.target.value = '';
          }
        }}
      />

      {importError ? <div className="error-text">{importError}</div> : null}

      <div className="project-section">
        <strong>Files</strong>
        <div className="hint">File order is run order for "Run Project".</div>

        <div className="project-file-list">
          {files.map((file, index) => (
            <div key={file.id} className={`project-file-row ${file.id === activeFileId ? 'is-active' : ''}`}>
              {renamingFileId === file.id ? (
                <>
                  <input
                    value={renameDraft}
                    onChange={(event) => setRenameDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        renameFile(file.id, renameDraft);
                        setRenamingFileId(undefined);
                      }
                      if (event.key === 'Escape') {
                        setRenamingFileId(undefined);
                      }
                    }}
                    aria-label={`Rename ${file.name}`}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      renameFile(file.id, renameDraft);
                      setRenamingFileId(undefined);
                    }}
                  >
                    Save
                  </button>
                  <button type="button" onClick={() => setRenamingFileId(undefined)}>
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="project-file-name"
                    onClick={() => setActiveFile(file.id)}
                    title="Switch active file"
                  >
                    {file.name}
                  </button>
                  <div className="project-file-actions">
                    <button
                      type="button"
                      onClick={() => moveFile(file.id, 'up')}
                      disabled={index === 0}
                      title="Move up"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => moveFile(file.id, 'down')}
                      disabled={index === files.length - 1}
                      title="Move down"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenamingFileId(file.id);
                        setRenameDraft(file.name);
                      }}
                      title="Rename"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const ok = window.confirm(`Delete ${file.name}?`);
                        if (ok) {
                          deleteFile(file.id);
                        }
                      }}
                      disabled={files.length <= 1}
                      title="Delete file"
                    >
                      Delete
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>

        <button type="button" onClick={() => createFile()}>
          + New File
        </button>
      </div>

      <div className="project-section">
        <strong>
          Problems ({issueCounts.errors} errors, {issueCounts.warnings} warnings)
        </strong>
        <div className="project-problem-list">
          {problems.length === 0 ? <div className="muted">No problems detected.</div> : null}
          {problems.map((problem) => (
            <button
              key={`${problem.word}:${problem.line}:${problem.message}`}
              type="button"
              className={`project-problem ${problem.severity === 'error' ? 'is-error' : 'is-warning'}`}
              onClick={() => {
                setActiveFile(problem.fileId);
                requestEditorFocus(problem.fileId, problem.fileLine);
              }}
              title={`${problem.fileName}:L${problem.fileLine}`}
            >
              <span className="project-problem-location">
                {problem.fileName}:L{problem.fileLine}
              </span>
              <span className="project-problem-message">{problem.message}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="project-section">
        <strong>Outline</strong>
        <div className="project-outline-list">
          {outline.length === 0 ? <div className="muted">No definitions found yet.</div> : null}
          {outline.map((item) => (
            <button
              key={`${item.name}:${item.startLine}`}
              type="button"
              className="project-outline-item"
              onClick={() => {
                setSelectedWord(item.name);
                setActiveFile(item.fileId);
                requestEditorFocus(item.fileId, item.fileLine);
              }}
              title={`${item.fileName}:L${item.fileLine}`}
            >
              <span className="project-outline-name">{item.name}</span>
              <span className="project-outline-meta">{item.fileName}:L{item.fileLine}</span>
              <span className="project-outline-meta">{effectSummary(item.effect)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="project-section">
        <strong>External Word Stubs</strong>
        <div className="hint">
          Use these to model words that exist on your device (ESP32forth/Bedrock) but not in the simulator.
        </div>

        <div className="external-word-add-row">
          <input
            value={externalDraftWord}
            onChange={(event) => setExternalDraftWord(event.target.value)}
            placeholder="WORD"
            aria-label="External word name"
          />
          <input
            value={externalDraftInputs}
            onChange={(event) => setExternalDraftInputs(event.target.value)}
            placeholder="in"
            aria-label="External word inputs"
          />
          <input
            value={externalDraftOutputs}
            onChange={(event) => setExternalDraftOutputs(event.target.value)}
            placeholder="out"
            aria-label="External word outputs"
          />
          <button
            type="button"
            onClick={() => {
              const word = externalDraftWord.trim();
              const inputs = Number(externalDraftInputs);
              const outputs = Number(externalDraftOutputs);
              if (!word || !Number.isFinite(inputs) || !Number.isFinite(outputs) || inputs < 0 || outputs < 0) {
                return;
              }
              upsertExternalWord({
                word,
                effect: { inputs, outputs },
              });
              setExternalDraftWord('');
              setExternalDraftInputs('0');
              setExternalDraftOutputs('0');
            }}
          >
            Add
          </button>
        </div>

        <div className="external-word-list">
          {externalList.length === 0 ? <div className="muted">No external stubs yet.</div> : null}
          {externalList.map((spec) => (
            <div key={spec.word} className="external-word-row">
              <div className="external-word-name">{spec.word}</div>
              <div className="external-word-effect">{effectSummary(spec.effect)}</div>
              <button type="button" onClick={() => removeExternalWord(spec.word)} title="Remove stub">
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

