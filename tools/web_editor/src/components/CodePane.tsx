import { useEffect, useMemo, useRef } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { EditorView, Decoration, GutterMarker, gutter, hoverTooltip, keymap, ViewPlugin, ViewUpdate } from '@codemirror/view';
import { Extension, Range, RangeSetBuilder, StateField, Text } from '@codemirror/state';
import type { ControlFlowDiagnostic } from '../analysis/control-flow';
import type { StackEffectDatabase, XRefEntry } from '../analysis/types';
import type { WordEntry } from '../engine/types';
import type { EditorFocusRequest } from '../store/ui-store';
import { findControlFlowMatches } from '../utils/control-flow-match';

interface CodePaneProps {
  fileId: string;
  source: string;
  annotationsByLine: Map<number, string[]>;
  diagnostics: ControlFlowDiagnostic[];
  breakpointLines: number[];
  showAnnotations: boolean;
  activeExecutionLine?: number;
  activeExecutionToken?: string;
  focusRequest?: EditorFocusRequest;
  initialStateJson?: unknown;
  effects?: StackEffectDatabase;
  xref?: Record<string, XRefEntry>;
  dictionary?: WordEntry[];
  onChange: (value: string) => void;
  onExecuteSelection: (text: string) => void;
  onExecuteAll: () => void;
  onExecuteFile?: () => void;
  onCursorWord: (word?: string) => void;
  onCursorLine: (line: number) => void;
  onToggleBreakpointLine: (line: number) => void;
  onPersistEditorState?: (fileId: string, stateJson: unknown) => void;
}

function findTokenRangeInLine(lineText: string, token: string): [number, number] | undefined {
  const wanted = token.toUpperCase();
  const tokenRegex = /[^\s]+/g;
  let match: RegExpExecArray | null;
  while ((match = tokenRegex.exec(lineText)) !== null) {
    if (match[0].toUpperCase() === wanted) {
      return [match.index, match.index + match[0].length];
    }
  }

  return undefined;
}

function buildLineDecorationSet(
  doc: Text,
  annotationsByLine: Map<number, string[]>,
  diagnosticsByLine: Map<number, ControlFlowDiagnostic[]>,
  breakpointLineSet: Set<number>,
  showAnnotations: boolean,
  activeExecutionLine?: number,
  activeExecutionToken?: string
) {
  const decorations: Range<Decoration>[] = [];

  for (const line of breakpointLineSet) {
    if (line < 1 || line > doc.lines) {
      continue;
    }
    const lineFrom = doc.line(line).from;
    decorations.push(
      Decoration.line({
        attributes: {
          class: 'cm-breakpoint-line',
        },
      }).range(lineFrom)
    );
  }

  for (const [line, labels] of annotationsByLine.entries()) {
    if (line < 1 || line > doc.lines || !showAnnotations) {
      continue;
    }

    const stackText = `[ ${labels.join(' ')} ]`;
    const lineFrom = doc.line(line).from;
    decorations.push(
      Decoration.line({
        attributes: {
          class: 'cm-stack-annotation',
          'data-stack': stackText,
        },
      }).range(lineFrom)
    );
  }

  for (const [line, diagnostics] of diagnosticsByLine.entries()) {
    if (line < 1 || line > doc.lines || diagnostics.length === 0) {
      continue;
    }

    const first = diagnostics[0];
    const lineFrom = doc.line(line).from;
    decorations.push(
      Decoration.line({
        attributes: {
          class: first.severity === 'error' ? 'cm-arity-error' : 'cm-arity-warning',
          'data-diagnostic': first.message,
        },
      }).range(lineFrom)
    );
  }

  if (activeExecutionLine && activeExecutionLine >= 1 && activeExecutionLine <= doc.lines) {
    const line = doc.line(activeExecutionLine);
    const lineFrom = line.from;
    decorations.push(
      Decoration.line({
        attributes: {
          class: 'cm-timeline-active-line',
          'data-execution-token': activeExecutionToken ?? '',
        },
      }).range(lineFrom)
    );

    if (activeExecutionToken) {
      const tokenRange = findTokenRangeInLine(line.text, activeExecutionToken);
      if (tokenRange) {
        decorations.push(
          Decoration.mark({ class: 'cm-timeline-active-token' }).range(line.from + tokenRange[0], line.from + tokenRange[1])
        );
      }
    }
  }

  return Decoration.set(decorations, true);
}

function syntaxClassForToken(token: string): string | undefined {
  const upper = token.toUpperCase();

  if ([
    ':',
    ';',
    'CONSTANT',
    'VARIABLE',
    'VALUE',
    'CREATE',
    'DOES>',
    'IMMEDIATE',
  ].includes(upper)) {
    return 'cm-token-define';
  }

  if ([
    'DUP',
    'DROP',
    'SWAP',
    'OVER',
    'ROT',
    '-ROT',
    'NIP',
    'TUCK',
    '2DUP',
    '2DROP',
    '2SWAP',
    '2OVER',
  ].includes(upper)) {
    return 'cm-token-stack';
  }

  if (['IF', 'ELSE', 'THEN', 'DO', 'LOOP', '+LOOP', 'BEGIN', 'UNTIL', 'WHILE', 'REPEAT'].includes(upper)) {
    return 'cm-token-control';
  }

  if (/^[+-]?\d+$/.test(token)) {
    return 'cm-token-number';
  }

  return undefined;
}

function syntaxDecorationExtension(): Extension {
  return ViewPlugin.fromClass(
    class {
      decorations;

      constructor(view: EditorView) {
        this.decorations = this.build(view);
      }

      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged) {
          this.decorations = this.build(update.view);
        }
      }

      build(view: EditorView) {
        const ranges: Array<{ from: number; to: number; deco: Decoration }> = [];

        for (const { from, to } of view.visibleRanges) {
          const text = view.state.doc.sliceString(from, to);
          const regex = /\b[^\s]+\b/g;
          let match: RegExpExecArray | null;
          while ((match = regex.exec(text)) !== null) {
            const token = match[0];
            const className = syntaxClassForToken(token);
            if (!className) {
              continue;
            }
            ranges.push({ from: from + match.index, to: from + match.index + token.length, deco: Decoration.mark({ class: className }) });
          }

          const commentRegex = /\\[^\n]*/g;
          while ((match = commentRegex.exec(text)) !== null) {
            ranges.push({ from: from + match.index, to: from + match.index + match[0].length, deco: Decoration.mark({ class: 'cm-token-comment' }) });
          }

          const stringRegex = /(\."[^"]*"|S"[^"]*")/g;
          while ((match = stringRegex.exec(text)) !== null) {
            ranges.push({ from: from + match.index, to: from + match.index + match[0].length, deco: Decoration.mark({ class: 'cm-token-string' }) });
          }
        }

        ranges.sort((a, b) => a.from - b.from || a.to - b.to);
        const builder = new RangeSetBuilder<Decoration>();
        for (const r of ranges) {
          builder.add(r.from, r.to, r.deco);
        }
        return builder.finish();
      }
    },
    {
      decorations: (value) => value.decorations,
    }
  );
}

function selectedTextOrLine(view: EditorView): string {
  const selection = view.state.selection.main;
  if (selection.from !== selection.to) {
    return view.state.sliceDoc(selection.from, selection.to);
  }

  return view.state.doc.lineAt(selection.from).text;
}

function detectWordAtCursor(view: EditorView): string | undefined {
  const selection = view.state.selection.main;
  const line = view.state.doc.lineAt(selection.from);
  const cursor = selection.from - line.from;

  const wordRegex = /[^\s]+/g;
  let match: RegExpExecArray | null;
  while ((match = wordRegex.exec(line.text)) !== null) {
    const start = match.index;
    const end = start + match[0].length;
    if (cursor >= start && cursor <= end) {
      return match[0];
    }
  }

  return undefined;
}

function controlFlowMatchExtension(): Extension {
  const matchDeco = Decoration.mark({ class: 'cm-matched-control' });

  return ViewPlugin.fromClass(
    class {
      decorations;

      constructor(view: EditorView) {
        this.decorations = this.build(view);
      }

      update(update: ViewUpdate) {
        if (update.selectionSet || update.docChanged) {
          this.decorations = this.build(update.view);
        }
      }

      build(view: EditorView) {
        const builder = new RangeSetBuilder<Decoration>();
        const cursorPos = view.state.selection.main.head;
        const text = view.state.doc.toString();
        const matches = findControlFlowMatches(text, cursorPos);

        if (matches.length === 0) {
          return builder.finish();
        }

        const sorted = [...matches].sort((a, b) => a.from - b.from);
        for (const m of sorted) {
          builder.add(m.from, m.to, matchDeco);
        }
        return builder.finish();
      }
    },
    {
      decorations: (value) => value.decorations,
    }
  );
}

function wordTooltipExtension(
  effects: StackEffectDatabase,
  xref: Record<string, XRefEntry>,
  dictionary: WordEntry[]
): Extension {
  return hoverTooltip((view, pos) => {
    const line = view.state.doc.lineAt(pos);
    const cursor = pos - line.from;
    const wordRegex = /[^\s]+/g;
    let match: RegExpExecArray | null;
    while ((match = wordRegex.exec(line.text)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      if (cursor >= start && cursor <= end) {
        const word = match[0];
        const upper = word.toUpperCase();
        const effect = effects[upper];
        const xrefEntry = xref[upper];
        const dictEntry = dictionary.find((w) => w.upperName === upper);

        if (!effect && !xrefEntry && !dictEntry) {
          if (/^[+-]?\d+$/.test(word)) {
            return {
              pos: line.from + start,
              end: line.from + end,
              above: true,
              create() {
                const dom = document.createElement('div');
                dom.className = 'cm-word-tooltip';
                dom.innerHTML = `<strong>${word}</strong> <span class="tooltip-meta">number literal</span><br/><span class="tooltip-effect">( -- ${word} )</span>`;
                return { dom };
              },
            };
          }
          return null;
        }

        return {
          pos: line.from + start,
          end: line.from + end,
          above: true,
          create() {
            const dom = document.createElement('div');
            dom.className = 'cm-word-tooltip';
            const parts: string[] = [];

            let headerLine = `<strong>${word}</strong>`;
            if (dictEntry) {
              headerLine += ` <span class="tooltip-meta">${dictEntry.type}</span>`;
            }
            if (effect) {
              headerLine += ` <span class="tooltip-badge ${effect.verified ? 'verified' : 'unverified'}">${effect.verified ? 'verified' : 'declared'}</span>`;
            }
            parts.push(headerLine);

            if (effect) {
              const inputLabels = effect.inputLabels?.join(' ') ?? new Array(effect.inputs).fill('x').join(' ');
              const outputLabels = effect.outputLabels?.join(' ') ?? new Array(effect.outputs).fill('x').join(' ');
              parts.push(`<span class="tooltip-effect">( ${inputLabels} -- ${outputLabels} )</span>`);
            }

            if (xrefEntry?.documentation) {
              parts.push(`<span class="tooltip-doc">${xrefEntry.documentation}</span>`);
            } else if (dictEntry?.documentation) {
              parts.push(`<span class="tooltip-doc">${dictEntry.documentation}</span>`);
            }

            dom.innerHTML = parts.join('<br/>');
            return { dom };
          },
        };
      }
    }
    return null;
  });
}

class BreakpointMarker extends GutterMarker {
  toDOM(): HTMLElement {
    const marker = document.createElement('span');
    marker.className = 'cm-breakpoint-marker';
    marker.textContent = '●';
    marker.setAttribute('aria-hidden', 'true');
    return marker;
  }
}

class BreakpointSpacer extends GutterMarker {
  toDOM(): HTMLElement {
    const spacer = document.createElement('span');
    spacer.className = 'cm-breakpoint-spacer';
    spacer.textContent = '●';
    spacer.setAttribute('aria-hidden', 'true');
    return spacer;
  }
}

const breakpointMarker = new BreakpointMarker();
const breakpointSpacer = new BreakpointSpacer();

export function CodePane({
  fileId,
  source,
  annotationsByLine,
  diagnostics,
  breakpointLines,
  showAnnotations,
  activeExecutionLine,
  activeExecutionToken,
  focusRequest,
  initialStateJson,
  effects,
  xref,
  dictionary,
  onChange,
  onExecuteSelection,
  onExecuteAll,
  onExecuteFile,
  onCursorWord,
  onCursorLine,
  onToggleBreakpointLine,
  onPersistEditorState,
}: CodePaneProps) {
  const editorRef = useRef<EditorView | null>(null);

  const diagnosticsByLine = useMemo(() => {
    const map = new Map<number, ControlFlowDiagnostic[]>();
    for (const diagnostic of diagnostics) {
      const existing = map.get(diagnostic.line) ?? [];
      existing.push(diagnostic);
      map.set(diagnostic.line, existing);
    }
    return map;
  }, [diagnostics]);

  const breakpointLineSet = useMemo(() => new Set(breakpointLines), [breakpointLines]);

  const breakpointGutterExtension = useMemo(() => {
    return gutter({
      class: 'cm-breakpoint-gutter',
      markers(view) {
        const builder = new RangeSetBuilder<GutterMarker>();
        for (const line of breakpointLines) {
          if (line < 1 || line > view.state.doc.lines) {
            continue;
          }
          const lineInfo = view.state.doc.line(line);
          builder.add(lineInfo.from, lineInfo.from, breakpointMarker);
        }
        return builder.finish();
      },
      initialSpacer: () => breakpointSpacer,
      domEventHandlers: {
        mousedown: (view, block) => {
          onToggleBreakpointLine(view.state.doc.lineAt(block.from).number);
          return true;
        },
      },
    });
  }, [breakpointLines, onToggleBreakpointLine]);

  const annotationExtension = useMemo(() => {
    return StateField.define({
      create(state) {
        return buildLineDecorationSet(
          state.doc,
          annotationsByLine,
          diagnosticsByLine,
          breakpointLineSet,
          showAnnotations,
          activeExecutionLine,
          activeExecutionToken
        );
      },
      update(_old, transaction) {
        return buildLineDecorationSet(
          transaction.state.doc,
          annotationsByLine,
          diagnosticsByLine,
          breakpointLineSet,
          showAnnotations,
          activeExecutionLine,
          activeExecutionToken
        );
      },
      provide: (field) => EditorView.decorations.from(field),
    });
  }, [
    annotationsByLine,
    diagnosticsByLine,
    breakpointLineSet,
    showAnnotations,
    activeExecutionLine,
    activeExecutionToken,
  ]);

  const keymapExtension = useMemo(() => {
    const bindings = [
      {
        key: 'Mod-Enter',
        run(view: EditorView) {
          onExecuteSelection(selectedTextOrLine(view));
          return true;
        },
      },
      {
        key: 'Mod-Shift-Enter',
        run() {
          onExecuteAll();
          return true;
        },
      },
    ];
    if (onExecuteFile) {
      bindings.push({
        key: 'Mod-Alt-Enter',
        run() {
          onExecuteFile();
          return true;
        },
      });
    }
    return keymap.of(bindings);
  }, [onExecuteAll, onExecuteFile, onExecuteSelection]);

  const tooltipExtension = useMemo(() => {
    if (!effects || !xref || !dictionary) {
      return [];
    }
    return wordTooltipExtension(effects, xref, dictionary);
  }, [effects, xref, dictionary]);

  const extensions = useMemo(
    () => [EditorView.lineWrapping, breakpointGutterExtension, syntaxDecorationExtension(), controlFlowMatchExtension(), annotationExtension, keymapExtension, tooltipExtension],
    [annotationExtension, breakpointGutterExtension, keymapExtension, tooltipExtension]
  );

  useEffect(() => {
    const view = editorRef.current;
    if (!view || !activeExecutionLine || activeExecutionLine < 1 || activeExecutionLine > view.state.doc.lines) {
      return;
    }

    const line = view.state.doc.line(activeExecutionLine);
    view.dispatch({
      effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
    });
  }, [activeExecutionLine]);

  useEffect(() => {
    return () => {
      if (!onPersistEditorState) {
        return;
      }
      const view = editorRef.current;
      if (!view) {
        return;
      }

      try {
        onPersistEditorState(fileId, view.state.toJSON());
      } catch {
        // If a custom extension introduces non-serializable state, just skip persistence.
      }
    };
  }, [fileId, onPersistEditorState]);

  useEffect(() => {
    if (!focusRequest || focusRequest.fileId !== fileId) {
      return;
    }

    const view = editorRef.current;
    if (!view) {
      return;
    }

    const lineNumber = focusRequest.line;
    if (lineNumber < 1 || lineNumber > view.state.doc.lines) {
      return;
    }

    const line = view.state.doc.line(lineNumber);
    view.dispatch({
      selection: { anchor: line.from },
      effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
    });
  }, [fileId, focusRequest]);

  return (
    <div className="code-pane">
      <div className="panel-header">
        <span>Code Pane</span>
        <span className="hint">Mod+Enter runs selection/line, Mod+Shift+Enter runs the project buffer</span>
      </div>
      <CodeMirror
        value={source}
        height="100%"
        extensions={extensions}
        theme="light"
        initialState={initialStateJson ? { json: initialStateJson } : undefined}
        onCreateEditor={(view) => {
          editorRef.current = view;
          onCursorLine(view.state.doc.lineAt(view.state.selection.main.from).number);
        }}
        onChange={onChange}
        onUpdate={(update) => {
          if (update.selectionSet || update.docChanged) {
            onCursorWord(detectWordAtCursor(update.view));
            const line = update.view.state.doc.lineAt(update.state.selection.main.from).number;
            onCursorLine(line);
          }
        }}
      />
    </div>
  );
}
