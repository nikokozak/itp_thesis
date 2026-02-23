import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react';
import { AnnotationOverlay } from './AnnotationOverlay';
import { CodePane } from './CodePane';
import { ConsolePane } from './ConsolePane';
import { DataflowDiagram } from './DataflowDiagram';
import { DictionaryBrowser } from './DictionaryBrowser';
import { MemoryInspector } from './MemoryInspector';
import { ProjectPanel } from './ProjectPanel';
import { REPL } from './REPL';
import { StackHeadsUp } from './StackHeadsUp';
import { StackTimeline } from './StackTimeline';
import { TimelineInspector } from './TimelineInspector';
import { WatchPanel } from './WatchPanel';
import { WordInspector } from './WordInspector';
import { useAnalysisStore } from '../store/analysis-store';
import { useEngineStore } from '../store/engine-store';
import { useUiStore } from '../store/ui-store';
import { useWorkspaceStore } from '../store/workspace-store';
import { findBreakpointIndex, findDistinctSourceLineIndex } from '../utils/debug-navigation';
import { computeDockHeight, computeSidebarWidth } from '../utils/layout-resize';
import { resolveStackHudState } from '../utils/stack-hud';
import {
  buildWorkspaceSourceMap,
  fileForGlobalLine,
  globalLineForFileLine,
} from '../utils/workspace-source';

type BottomTab = 'console' | 'timeline' | 'repl';
type SidebarTab = 'project' | 'inspect' | 'debug';

const SIDEBAR_TABS: Array<{ id: SidebarTab; label: string }> = [
  { id: 'project', label: 'Project' },
  { id: 'inspect', label: 'Inspect' },
  { id: 'debug', label: 'Debug' },
];

function buildLineAnnotationsForFile(
  labels: ReturnType<typeof useAnalysisStore.getState>['labels'],
  sourceMap: ReturnType<typeof useAnalysisStore.getState>['sourceMap'] | undefined,
  fileId: string
): Map<number, string[]> {
  const map = new Map<number, string[]>();
  if (!sourceMap) {
    return map;
  }

  const range = sourceMap.files.find((file) => file.fileId === fileId);
  if (!range) {
    return map;
  }

  for (const trace of labels) {
    for (const step of trace.steps) {
      if (step.token.line < range.startLine || step.token.line > range.endLine) {
        continue;
      }
      map.set(step.token.line - range.startLine + 1, step.after);
    }
  }

  return map;
}

function mapDiagnosticsToFile(
  diagnostics: ReturnType<typeof useAnalysisStore.getState>['diagnostics'],
  sourceMap: ReturnType<typeof useAnalysisStore.getState>['sourceMap'] | undefined,
  fileId: string
) {
  if (!sourceMap) {
    return [];
  }

  const range = sourceMap.files.find((file) => file.fileId === fileId);
  if (!range) {
    return [];
  }

  return diagnostics
    .filter((diagnostic) => diagnostic.line >= range.startLine && diagnostic.line <= range.endLine)
    .map((diagnostic) => ({
      ...diagnostic,
      line: diagnostic.line - range.startLine + 1,
    }));
}

function buildWordLineHints(analyses: ReturnType<typeof useAnalysisStore.getState>['analyses']): Record<string, number> {
  const hints: Record<string, number> = {};
  for (const analysis of analyses) {
    hints[analysis.name.toUpperCase()] = analysis.startLine;
  }
  return hints;
}

const LAYOUT_SPLITTER_SIZE = 8;
const SIDEBAR_MIN_WIDTH = 280;
const SIDEBAR_MAX_WIDTH = 640;
const MAIN_MIN_WIDTH = 480;
const DOCK_MIN_HEIGHT = 132;
const DOCK_MAX_HEIGHT = 520;
const EDITOR_MIN_HEIGHT = 180;

export function App() {
  const replInputRef = useRef<HTMLInputElement>(null);
  const ideLayoutRef = useRef<HTMLElement>(null);
  const workspaceCenterRef = useRef<HTMLDivElement>(null);
  const editorStateJsonByFileId = useRef<Record<string, unknown>>({});

  const initializeEngine = useEngineStore((state) => state.initialize);
  const executeSource = useEngineStore((state) => state.executeSource);
  const clearTimeline = useEngineStore((state) => state.clearTimeline);
  const clearOutput = useEngineStore((state) => state.clearOutput);
  const resetRuntime = useEngineStore((state) => state.resetRuntime);
  const dictionary = useEngineStore((state) => state.dictionary);
  const timeline = useEngineStore((state) => state.timeline);
  const analysisVersion = useEngineStore((state) => state.analysisVersion);
  const outputLog = useEngineStore((state) => state.outputLog);
  const lastError = useEngineStore((state) => state.lastError);
  const runtimeDataStack = useEngineStore((state) => state.dataStack);
  const runtimeReturnStack = useEngineStore((state) => state.returnStack);
  const runtimeFloatStack = useEngineStore((state) => state.floatStack);

  const workspaceVersion = useWorkspaceStore((state) => state.version);
  const files = useWorkspaceStore((state) => state.files);
  const activeFileId = useWorkspaceStore((state) => state.activeFileId);
  const setActiveFile = useWorkspaceStore((state) => state.setActiveFile);
  const setFileContent = useWorkspaceStore((state) => state.setFileContent);
  const createFile = useWorkspaceStore((state) => state.createFile);
  const setDocumentation = useWorkspaceStore((state) => state.setDocumentation);

  const recompute = useAnalysisStore((state) => state.recompute);
  const analyses = useAnalysisStore((state) => state.analyses);
  const effects = useAnalysisStore((state) => state.effects);
  const labels = useAnalysisStore((state) => state.labels);
  const xref = useAnalysisStore((state) => state.xref);
  const diagnostics = useAnalysisStore((state) => state.diagnostics);
  const combinedSource = useAnalysisStore((state) => state.combinedSource);
  const sourceMap = useAnalysisStore((state) => state.sourceMap);
  const selectedWord = useAnalysisStore((state) => state.selectedWord);
  const setSelectedWord = useAnalysisStore((state) => state.setSelectedWord);

  const showAnnotations = useUiStore((state) => state.showAnnotations);
  const setShowAnnotations = useUiStore((state) => state.setShowAnnotations);
  const editorFocus = useUiStore((state) => state.editorFocus);
  const timelineCursor = useUiStore((state) => state.timelineCursor);
  const setTimelineCursor = useUiStore((state) => state.setTimelineCursor);
  const timelineMode = useUiStore((state) => state.timelineMode);
  const setTimelineMode = useUiStore((state) => state.setTimelineMode);
  const breakpointsByFileId = useUiStore((state) => state.breakpointsByFileId);
  const toggleBreakpointLine = useUiStore((state) => state.toggleBreakpointLine);
  const clearBreakpointLines = useUiStore((state) => state.clearBreakpointLines);
  const executionTarget = useUiStore((state) => state.executionTarget);
  const setExecutionTarget = useUiStore((state) => state.setExecutionTarget);
  const minimalMode = useUiStore((state) => state.minimalMode);
  const setMinimalMode = useUiStore((state) => state.setMinimalMode);
  const requestEditorFocus = useUiStore((state) => state.requestEditorFocus);

  const [bottomTab, setBottomTab] = useState<BottomTab>('console');
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>('project');
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [editorCursorLine, setEditorCursorLine] = useState(1);
  const [sidebarWidth, setSidebarWidth] = useState(410);
  const [dockHeight, setDockHeight] = useState(280);

  const activeFile = useMemo(() => files.find((file) => file.id === activeFileId) ?? files[0], [activeFileId, files]);

  useEffect(() => {
    initializeEngine();
  }, [initializeEngine]);

  useEffect(() => {
    recompute();
  }, [analysisVersion, recompute, workspaceVersion]);

  useEffect(() => {
    if (activeFile && activeFile.id !== activeFileId) {
      setActiveFile(activeFile.id);
    }
  }, [activeFile, activeFileId, setActiveFile]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) {
        return;
      }

      const key = event.key.toLowerCase();

      if (key === '`') {
        event.preventDefault();
        setBottomTab('repl');
        requestAnimationFrame(() => replInputRef.current?.focus());
        return;
      }

      if (key === 'p') {
        event.preventDefault();
        setSidebarVisible(true);
        setSidebarTab('project');
        return;
      }

      if (key === 'd' || key === 'i') {
        event.preventDefault();
        setSidebarVisible(true);
        setSidebarTab('inspect');
        return;
      }

      if (key === 'a' && !event.shiftKey) {
        event.preventDefault();
        setShowAnnotations(!showAnnotations);
        setSidebarVisible(true);
        setSidebarTab('inspect');
        return;
      }

      if (key === 'b') {
        event.preventDefault();
        setSidebarVisible((value) => !value);
        return;
      }

      if (key === 'm') {
        event.preventDefault();
        setMinimalMode(!minimalMode);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [minimalMode, requestEditorFocus, setMinimalMode, setShowAnnotations, showAnnotations]);

  const annotationsByLine = useMemo(
    () => buildLineAnnotationsForFile(labels, sourceMap, activeFile?.id ?? ''),
    [activeFile?.id, labels, sourceMap]
  );
  const fileDiagnostics = useMemo(
    () => mapDiagnosticsToFile(diagnostics, sourceMap, activeFile?.id ?? ''),
    [activeFile?.id, diagnostics, sourceMap]
  );
  const wordLineHints = useMemo(() => buildWordLineHints(analyses), [analyses]);
  const stepCount = useMemo(
    () => timeline.filter((point) => point.eventType === 'execute' || point.eventType === 'error').length,
    [timeline]
  );
  const hiddenEventCount = Math.max(0, timeline.length - stepCount);
  const visibleTimeline = useMemo(
    () =>
      timelineMode === 'trace'
        ? timeline
        : timeline.filter((point) => point.eventType === 'execute' || point.eventType === 'error'),
    [timeline, timelineMode]
  );

  const breakpointLines = activeFile ? breakpointsByFileId[activeFile.id] ?? [] : [];
  const globalBreakpointLineSet = useMemo(() => {
    const map = sourceMap ?? buildWorkspaceSourceMap(files);
    const set = new Set<number>();

    for (const [fileId, lines] of Object.entries(breakpointsByFileId)) {
      for (const line of lines) {
        const global = globalLineForFileLine(map, fileId, line);
        if (global !== undefined) {
          set.add(global);
        }
      }
    }

    return set;
  }, [breakpointsByFileId, files, sourceMap]);

  const selectedTimelineIndex = Math.max(0, Math.min(visibleTimeline.length - 1, timelineCursor));
  const activeTimelinePoint = selectedTimelineIndex >= 0 ? visibleTimeline[selectedTimelineIndex] : undefined;

  const formatLocation = useCallback(
    (point: (typeof visibleTimeline)[number]) => {
      if (point.sourceLine !== undefined && point.sourceLabel === 'project') {
        const loc = fileForGlobalLine(sourceMap, point.sourceLine);
        return loc ? `${loc.fileName}:L${loc.fileLine}` : `L${point.sourceLine}`;
      }

      if (point.sourceLine !== undefined) {
        return `${point.sourceLabel ?? 'input'}:L${point.sourceLine}`;
      }

      if (point.word) {
        const globalLine = wordLineHints[point.word.toUpperCase()];
        if (globalLine !== undefined) {
          const loc = fileForGlobalLine(sourceMap, globalLine);
          return loc ? `${loc.fileName}:L${loc.fileLine}` : `L${globalLine}`;
        }
      }

      return undefined;
    },
    [sourceMap, wordLineHints]
  );

  const activeExecutionGlobalLine =
    activeTimelinePoint?.sourceLabel === 'project' ? activeTimelinePoint.sourceLine : undefined;
  const activeExecutionHintLine = activeTimelinePoint?.word
    ? wordLineHints[activeTimelinePoint.word.toUpperCase()]
    : undefined;
  const activeExecutionLoc = activeExecutionGlobalLine
    ? fileForGlobalLine(sourceMap, activeExecutionGlobalLine)
    : activeExecutionHintLine !== undefined
      ? fileForGlobalLine(sourceMap, activeExecutionHintLine)
      : undefined;
  const activeExecutionLine =
    activeExecutionLoc && activeFile && activeExecutionLoc.fileId === activeFile.id
      ? activeExecutionLoc.fileLine
      : undefined;

  const hasTimeline = visibleTimeline.length > 0;
  const hasMultipleSteps = visibleTimeline.length > 1;
  const canStepBackward = hasMultipleSteps && selectedTimelineIndex > 0;
  const canStepForward = hasMultipleSteps && selectedTimelineIndex < visibleTimeline.length - 1;

  const stackHudState = useMemo(
    () =>
      resolveStackHudState(
        {
          dataStack: runtimeDataStack,
          returnStack: runtimeReturnStack,
          floatStack: runtimeFloatStack,
        },
        activeTimelinePoint,
        bottomTab === 'timeline',
        selectedTimelineIndex,
        visibleTimeline.length
      ),
    [
      activeTimelinePoint,
      bottomTab,
      runtimeDataStack,
      runtimeFloatStack,
      runtimeReturnStack,
      selectedTimelineIndex,
      visibleTimeline.length,
    ]
  );

  const prevBottomTab = useRef(bottomTab);
  useEffect(() => {
    if (bottomTab === 'timeline' && prevBottomTab.current !== 'timeline' && sidebarVisible) {
      setSidebarTab('debug');
    }
    prevBottomTab.current = bottomTab;
  }, [bottomTab, sidebarVisible]);

  useEffect(() => {
    if (bottomTab !== 'timeline' || !activeExecutionLoc) {
      return;
    }
    if (activeExecutionLoc.fileId !== activeFile?.id) {
      setActiveFile(activeExecutionLoc.fileId);
    }
    requestEditorFocus(activeExecutionLoc.fileId, activeExecutionLoc.fileLine);
  }, [activeExecutionLoc, activeFile?.id, bottomTab, requestEditorFocus, setActiveFile]);

  useEffect(() => {
    if (!activeTimelinePoint?.word) {
      return;
    }

    const exists = dictionary.some((entry) => entry.name.toUpperCase() === activeTimelinePoint.word?.toUpperCase());
    if (exists) {
      setSelectedWord(activeTimelinePoint.word);
    }
  }, [activeTimelinePoint?.word, dictionary, setSelectedWord]);

  const setClampedTimelineCursor = useCallback(
    (index: number) => {
      if (visibleTimeline.length === 0) {
        setTimelineCursor(0);
        return;
      }
      const clamped = Math.max(0, Math.min(visibleTimeline.length - 1, index));
      setTimelineCursor(clamped);
    },
    [setTimelineCursor, visibleTimeline.length]
  );

  const stepTimeline = useCallback(
    (delta: number) => {
      if (visibleTimeline.length === 0) {
        return;
      }
      setClampedTimelineCursor(selectedTimelineIndex + delta);
    },
    [selectedTimelineIndex, setClampedTimelineCursor, visibleTimeline.length]
  );

  const jumpTimelineBoundary = useCallback(
    (target: 'start' | 'end') => {
      if (visibleTimeline.length === 0) {
        return;
      }
      setTimelineCursor(target === 'start' ? 0 : visibleTimeline.length - 1);
    },
    [setTimelineCursor, visibleTimeline.length]
  );

  const stepTimelineByLine = useCallback(
    (direction: 'prev' | 'next') => {
      if (visibleTimeline.length === 0) {
        return;
      }

      const index = findDistinctSourceLineIndex(
        visibleTimeline,
        selectedTimelineIndex,
        direction === 'next' ? 'forward' : 'backward'
      );
      if (index >= 0) {
        setTimelineCursor(index);
      }
    },
    [selectedTimelineIndex, setTimelineCursor, visibleTimeline]
  );

  const runProjectAndStopAtLines = useCallback(
    (stopLines: Set<number>) => {
      const source = combinedSource || buildWorkspaceSourceMap(files).source;
      executeSource(source, 'project', { resetTimeline: true, resetStacks: true, clearOutput: true });
      setBottomTab('timeline');
      recompute();

      const nextTimeline = useEngineStore.getState().timeline;
      const visible =
        timelineMode === 'trace'
          ? nextTimeline
          : nextTimeline.filter((point) => point.eventType === 'execute' || point.eventType === 'error');
      const firstStop = findBreakpointIndex(visible, stopLines, 0, 'forward');
      setTimelineCursor(firstStop >= 0 ? firstStop : 0);
    },
    [combinedSource, executeSource, files, recompute, setTimelineCursor, timelineMode]
  );

  const runProjectAndStopAtBreakpoint = useCallback(() => {
    runProjectAndStopAtLines(globalBreakpointLineSet);
  }, [globalBreakpointLineSet, runProjectAndStopAtLines]);

  const runProjectToCursorLine = useCallback(() => {
    if (!activeFile) {
      return;
    }
    const map = sourceMap ?? buildWorkspaceSourceMap(files);
    const global = globalLineForFileLine(map, activeFile.id, editorCursorLine);
    if (global === undefined) {
      return;
    }
    runProjectAndStopAtLines(new Set([global]));
  }, [activeFile, editorCursorLine, files, runProjectAndStopAtLines, sourceMap]);

  const startSidebarResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (minimalMode || !sidebarVisible) {
        return;
      }

      event.preventDefault();
      document.body.classList.add('is-resizing-panels');

      const onPointerMove = (moveEvent: PointerEvent) => {
        const rect = ideLayoutRef.current?.getBoundingClientRect();
        if (!rect) {
          return;
        }
        const pointerOffsetX = moveEvent.clientX - rect.left;
        const nextWidth = computeSidebarWidth({
          containerWidth: rect.width,
          pointerOffsetX,
          minSidebarWidth: SIDEBAR_MIN_WIDTH,
          maxSidebarWidth: SIDEBAR_MAX_WIDTH,
          minMainWidth: MAIN_MIN_WIDTH,
          splitterWidth: LAYOUT_SPLITTER_SIZE,
        });
        setSidebarWidth(nextWidth);
      };

      const onPointerUp = () => {
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', onPointerUp);
        window.removeEventListener('pointercancel', onPointerUp);
        document.body.classList.remove('is-resizing-panels');
      };

      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerUp);
    },
    [minimalMode, sidebarVisible]
  );

  const startDockResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    document.body.classList.add('is-resizing-panels');

    const onPointerMove = (moveEvent: PointerEvent) => {
      const rect = workspaceCenterRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      const pointerOffsetY = moveEvent.clientY - rect.top;
      const nextHeight = computeDockHeight({
        containerHeight: rect.height,
        pointerOffsetY,
        minDockHeight: DOCK_MIN_HEIGHT,
        maxDockHeight: DOCK_MAX_HEIGHT,
        minEditorHeight: EDITOR_MIN_HEIGHT,
        splitterHeight: LAYOUT_SPLITTER_SIZE,
      });
      setDockHeight(nextHeight);
    };

    const onPointerUp = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      document.body.classList.remove('is-resizing-panels');
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (visibleTimeline.length === 0) {
        return;
      }

      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTextInput = tag === 'INPUT' || tag === 'TEXTAREA' || target?.getAttribute('contenteditable') === 'true';
      if (isTextInput) {
        return;
      }

      if (event.key === 'F10' && !event.shiftKey) {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimeline(1);
        return;
      }

      if (event.key === 'F10' && event.shiftKey) {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimeline(-1);
        return;
      }

      if (event.altKey && event.key === ']') {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimeline(1);
        return;
      }

      if (event.altKey && event.key === '[') {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimeline(-1);
        return;
      }

      if (event.altKey && event.key === 'F9') {
        event.preventDefault();
        setBottomTab('timeline');
        runProjectToCursorLine();
        return;
      }

      if (event.altKey && event.key === 'ArrowDown') {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimelineByLine('next');
        return;
      }

      if (event.altKey && event.key === 'ArrowUp') {
        event.preventDefault();
        setBottomTab('timeline');
        stepTimelineByLine('prev');
        return;
      }

      if (event.altKey && event.key === 'Home') {
        event.preventDefault();
        setBottomTab('timeline');
        jumpTimelineBoundary('start');
        return;
      }

      if (event.altKey && event.key === 'End') {
        event.preventDefault();
        setBottomTab('timeline');
        jumpTimelineBoundary('end');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [jumpTimelineBoundary, runProjectToCursorLine, stepTimeline, stepTimelineByLine, visibleTimeline.length]);

  const breakpointCount = useMemo(() => {
    let count = 0;
    for (const lines of Object.values(breakpointsByFileId)) {
      count += lines.length;
    }
    return count;
  }, [breakpointsByFileId]);

  const isSidebarShown = !minimalMode && sidebarVisible;
  const layoutStyle = useMemo(() => {
    if (!isSidebarShown) {
      return undefined;
    }
    return {
      '--sidebar-width': `${sidebarWidth}px`,
    } as CSSProperties;
  }, [isSidebarShown, sidebarWidth]);

  const workspaceCenterStyle = useMemo(
    () =>
      ({
        gridTemplateRows: `minmax(${EDITOR_MIN_HEIGHT}px, 1fr) ${LAYOUT_SPLITTER_SIZE}px ${dockHeight}px`,
      }) as CSSProperties,
    [dockHeight]
  );

  const sidebarPanel = (() => {
    switch (sidebarTab) {
      case 'project':
        return <ProjectPanel />;
      case 'inspect':
        return (
          <div className="inspect-panel">
            <DictionaryBrowser
              words={dictionary}
              effects={effects}
              selectedWord={selectedWord}
              onSelectWord={setSelectedWord}
              compact
            />
            <WordInspector
              selectedWord={selectedWord}
              dictionary={dictionary}
              effects={effects}
              xref={xref}
              onSelectWord={setSelectedWord}
              onSetDocumentation={setDocumentation}
              onGoToDefinition={(globalLine) => {
                const loc = fileForGlobalLine(sourceMap, globalLine);
                if (!loc) {
                  return;
                }
                setActiveFile(loc.fileId);
                requestEditorFocus(loc.fileId, loc.fileLine);
              }}
            />
            <details className="sidebar-details">
              <summary>Annotations</summary>
              <AnnotationOverlay analyses={analyses} labels={labels} sourceMap={sourceMap} />
            </details>
            <details className="sidebar-details">
              <summary>Dataflow</summary>
              <DataflowDiagram selectedWord={selectedWord} analyses={analyses} labels={labels} />
            </details>
          </div>
        );
      case 'debug':
        return (
          <div className="debug-panel">
            <TimelineInspector
              selectedPoint={activeTimelinePoint}
              selectedIndex={selectedTimelineIndex}
              totalSteps={visibleTimeline.length}
              formatLocation={formatLocation}
              timelineMode={timelineMode}
              onTimelineModeChange={(mode) => {
                setTimelineMode(mode);
                setTimelineCursor(0);
              }}
              stepCount={stepCount}
              traceCount={timeline.length}
              hiddenEventCount={hiddenEventCount}
            />
            <details className="sidebar-details" open>
              <summary>Watch</summary>
              <WatchPanel />
            </details>
            <details className="sidebar-details">
              <summary>Memory</summary>
              <MemoryInspector
                visible
                activePoint={activeTimelinePoint}
                selectedStep={hasTimeline ? selectedTimelineIndex + 1 : undefined}
                totalSteps={visibleTimeline.length}
              />
            </details>
          </div>
        );
      default:
        return null;
    }
  })();

  return (
    <div className={`app-shell ${minimalMode ? 'minimal-mode' : ''}`}>
      <header className="app-toolbar">
        <div className="toolbar-title">
          <h1>Bedrock Web Editor</h1>
          <span className="hint">Multi-file workspace, progressive debugging, and device-oriented workflows (serial transport coming next).</span>
        </div>

        <div className="toolbar-actions">
          <div className="target-picker" role="group" aria-label="Execution target">
            <button
              type="button"
              className={executionTarget === 'local' ? 'is-active' : ''}
              onClick={() => setExecutionTarget('local')}
            >
              Local
            </button>
            <button
              type="button"
              className={executionTarget === 'device' ? 'is-active' : ''}
              disabled
              title="Connect via serial (coming soon)"
            >
              Device
            </button>
          </div>

          <button type="button" onClick={() => runProjectAndStopAtBreakpoint()} title="Run all files in order (fresh trace)">
            Run Project
          </button>

          <button type="button" onClick={() => runProjectToCursorLine()} title="Run from start and stop at cursor line (Alt+F9)">
            Run To Cursor
          </button>

          <button
            type="button"
            onClick={() => {
              if (activeFile) {
                executeSource(activeFile.content, activeFile.name);
                recompute();
              }
            }}
            title="Run active file only (Mod+Alt+Enter)"
          >
            Run File
          </button>

          <button
            type="button"
            onClick={() => {
              resetRuntime();
              setTimelineCursor(0);
            }}
            title="Clear stacks + dictionary state"
          >
            Reset Runtime
          </button>

          <button
            type="button"
            onClick={() => {
              clearTimeline();
              clearOutput();
              setTimelineCursor(0);
            }}
            disabled={timeline.length === 0 && outputLog.length === 0}
            title="Clears timeline and console output"
          >
            Clear All
          </button>

          <button type="button" onClick={() => setSidebarVisible((value) => !value)}>
            {sidebarVisible ? 'Hide' : 'Show'} Sidebar
          </button>

          <button type="button" onClick={() => setMinimalMode(!minimalMode)}>
            {minimalMode ? 'Full Mode' : 'Minimal Mode'}
          </button>
        </div>

        <div className="debug-transport" role="group" aria-label="Debugger transport">
          <button
            type="button"
            onClick={() => {
              setBottomTab('timeline');
              jumpTimelineBoundary('start');
            }}
            disabled={!canStepBackward}
            title="First step (Alt+Home)"
          >
            |&lt;
          </button>
          <button
            type="button"
            onClick={() => {
              setBottomTab('timeline');
              stepTimeline(-1);
            }}
            disabled={!canStepBackward}
            title="Step back (Shift+F10)"
          >
            Step-
          </button>
          <button
            type="button"
            onClick={() => {
              setBottomTab('timeline');
              stepTimeline(1);
            }}
            disabled={!canStepForward}
            title="Step over (F10)"
          >
            Step+
          </button>
          <button
            type="button"
            onClick={() => {
              setBottomTab('timeline');
              jumpTimelineBoundary('end');
            }}
            disabled={!canStepForward}
            title="Last step (Alt+End)"
          >
            &gt;|
          </button>
          <span className="hint debug-transport-status">
            {hasTimeline
              ? `${selectedTimelineIndex + 1}/${visibleTimeline.length} · ${activeTimelinePoint?.eventType ?? 'step'}${
                  activeExecutionLoc ? ` · ${activeExecutionLoc.fileName}:L${activeExecutionLoc.fileLine}` : ''
                }`
              : 'No timeline yet'}
          </span>
        </div>
      </header>

      <main
        ref={ideLayoutRef}
        className={`ide-layout ${isSidebarShown ? 'is-sidebar-visible' : 'is-sidebar-hidden'}`}
        style={layoutStyle}
      >
        <section className="workspace-main">
          <div className="editor-tabstrip">
            {files.map((file) => (
              <button
                key={file.id}
                type="button"
                className={`editor-tab ${file.id === activeFile?.id ? 'is-active' : ''}`}
                onClick={() => setActiveFile(file.id)}
              >
                {file.name}
              </button>
            ))}
            <button
              type="button"
              className="editor-tab"
              onClick={() => {
                createFile();
                setSidebarVisible(true);
                setSidebarTab('project');
              }}
              title="Create a new file"
            >
              +
            </button>
            <span className="hint">Mod+Enter line, Mod+Alt+Enter file, Mod+Shift+Enter project</span>
          </div>

          <StackHeadsUp state={stackHudState} />

          <div className="workspace-center" ref={workspaceCenterRef} style={workspaceCenterStyle}>
            <div className="editor-surface">
              {activeFile ? (
                <CodePane
                  key={activeFile.id}
                  fileId={activeFile.id}
                  source={activeFile.content}
                  annotationsByLine={annotationsByLine}
                  diagnostics={fileDiagnostics}
                  breakpointLines={breakpointLines}
                  showAnnotations={showAnnotations && !minimalMode}
                  activeExecutionLine={activeExecutionLine}
                  activeExecutionToken={activeTimelinePoint?.sourceToken}
                  focusRequest={editorFocus}
                  initialStateJson={editorStateJsonByFileId.current[activeFile.id]}
                  effects={effects}
                  xref={xref}
                  dictionary={dictionary}
                  onChange={(value) => setFileContent(activeFile.id, value)}
                  onExecuteSelection={(text) => {
                    executeSource(text, `selection:${activeFile.name}`);
                    recompute();
                  }}
                  onExecuteAll={() => {
                    runProjectAndStopAtBreakpoint();
                  }}
                  onExecuteFile={() => {
                    executeSource(activeFile.content, activeFile.name);
                    recompute();
                  }}
                  onCursorWord={(word) => {
                    if (word) {
                      setSelectedWord(word);
                      if (sidebarVisible && sidebarTab === 'project') {
                        setSidebarTab('inspect');
                      }
                    }
                  }}
                  onCursorLine={(line) => {
                    setEditorCursorLine(line);
                  }}
                  onToggleBreakpointLine={(line) => toggleBreakpointLine(activeFile.id, line)}
                  onPersistEditorState={(fileId, stateJson) => {
                    editorStateJsonByFileId.current[fileId] = stateJson;
                  }}
                />
              ) : (
                <div className="muted">No active file.</div>
              )}
            </div>

            <div
              className="panel-splitter horizontal"
              onPointerDown={startDockResize}
              role="separator"
              aria-label="Resize editor and dock"
              aria-orientation="horizontal"
            />

            <section className="bottom-dock">
              <div className="dock-tabs">
                <button
                  type="button"
                  className={`dock-tab ${bottomTab === 'console' ? 'is-active' : ''}`}
                  onClick={() => setBottomTab('console')}
                >
                  Console ({outputLog.length})
                </button>
                <button
                  type="button"
                  className={`dock-tab ${bottomTab === 'repl' ? 'is-active' : ''}`}
                  onClick={() => setBottomTab('repl')}
                >
                  REPL
                </button>
                <button
                  type="button"
                  className={`dock-tab ${bottomTab === 'timeline' ? 'is-active' : ''}`}
                  onClick={() => setBottomTab('timeline')}
                  disabled={minimalMode}
                  title={minimalMode ? 'Timeline hidden in minimal mode' : undefined}
                >
                  Timeline ({visibleTimeline.length})
                </button>
                <div className="dock-spacer" />
                {bottomTab === 'timeline' ? <span className="hint">Details live in sidebar Timeline tab.</span> : null}
              </div>

              <div className="dock-body">
                {bottomTab === 'console' ? (
                  <ConsolePane outputLog={outputLog} lastError={lastError} onClear={() => clearOutput()} />
                ) : bottomTab === 'timeline' ? (
                  <StackTimeline
                    timeline={visibleTimeline}
                    cursor={selectedTimelineIndex}
                    onCursorChange={(index) => setTimelineCursor(index)}
                    formatLocation={formatLocation}
                  />
                ) : (
                  <REPL ref={replInputRef} effectDb={effects} onInspectWord={setSelectedWord} />
                )}
              </div>
            </section>
          </div>
        </section>

        {isSidebarShown ? (
          <>
            <div
              className="panel-splitter vertical"
              onPointerDown={startSidebarResize}
              role="separator"
              aria-label="Resize main and sidebar"
              aria-orientation="vertical"
            />
            <aside className="workspace-sidebar">
              <div className="sidebar-tabs">
                {SIDEBAR_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={`sidebar-tab ${sidebarTab === tab.id ? 'is-active' : ''}`}
                    onClick={() => setSidebarTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="sidebar-body">{sidebarPanel}</div>
            </aside>
          </>
        ) : null}
      </main>
    </div>
  );
}
