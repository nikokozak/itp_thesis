import { useEffect, useMemo, useState } from 'react';
import type { TimelinePoint } from '../store/engine-store';

interface TimelineInspectorProps {
  selectedPoint?: TimelinePoint;
  selectedIndex: number;
  totalSteps: number;
  formatLocation: (point: TimelinePoint) => string | undefined;
  timelineMode: 'steps' | 'trace';
  onTimelineModeChange: (mode: 'steps' | 'trace') => void;
  stepCount: number;
  traceCount: number;
  hiddenEventCount: number;
}

function stepLabel(point: TimelinePoint, formatLocation: (point: TimelinePoint) => string | undefined): string {
  if (point.eventType === 'define') {
    return point.definitionName ? `define ${point.definitionName}` : 'define';
  }

  if (point.eventType === 'input') {
    return 'input';
  }

  if (point.eventType === 'output') {
    return 'output';
  }

  if (point.eventType === 'push' || point.eventType === 'pop') {
    return point.value !== undefined ? `${point.eventType} ${point.value}` : point.eventType;
  }

  const word = point.word ?? point.eventType;
  const location = formatLocation(point);
  return location ? `${word} @${location}` : word;
}

function eventToken(point: TimelinePoint): string {
  if (point.sourceToken) {
    return point.sourceToken;
  }
  if (point.word) {
    return point.word;
  }
  if (point.definitionName) {
    return point.definitionName;
  }
  if ((point.eventType === 'input' || point.eventType === 'output') && point.text) {
    return point.text.length > 40 ? `${point.text.slice(0, 40)}...` : point.text;
  }
  return '-';
}

function stackLine(label: string, stack: number[]) {
  return (
    <div className="timeline-stack-line">
      <span>{label}</span>
      <code>[ {stack.join(' ')} ]</code>
    </div>
  );
}

export function TimelineInspector({
  selectedPoint,
  selectedIndex,
  totalSteps,
  formatLocation,
  timelineMode,
  onTimelineModeChange,
  stepCount,
  traceCount,
  hiddenEventCount,
}: TimelineInspectorProps) {
  const [selectedFrameIndex, setSelectedFrameIndex] = useState(0);

  const callStackFrames = useMemo(
    () => (selectedPoint?.callStack ? [...selectedPoint.callStack].reverse() : []),
    [selectedPoint?.callStack]
  );
  const selectedFrame =
    callStackFrames.length > 0 ? callStackFrames[Math.min(selectedFrameIndex, callStackFrames.length - 1)] : undefined;

  useEffect(() => {
    setSelectedFrameIndex(0);
  }, [selectedPoint?.sequenceNumber]);

  return (
    <div className="timeline-inspector-pane">
      <div className="panel-header">
        <span>Timeline Inspector</span>
        <span className="hint">
          {selectedPoint ? `Step ${selectedIndex + 1}/${Math.max(totalSteps, 1)} · seq ${selectedPoint.sequenceNumber}` : 'No timeline step selected'}
        </span>
      </div>

      <div className="timeline-inspector-mode-row">
        <button
          type="button"
          className={timelineMode === 'steps' ? 'is-active' : ''}
          onClick={() => onTimelineModeChange('steps')}
        >
          Focused ({stepCount})
        </button>
        <button
          type="button"
          className={timelineMode === 'trace' ? 'is-active' : ''}
          onClick={() => onTimelineModeChange('trace')}
        >
          Full Trace ({traceCount})
        </button>
        <span className="hint">
          {timelineMode === 'steps'
            ? hiddenEventCount > 0
              ? `${hiddenEventCount} non-step events hidden`
              : 'No extra events hidden'
            : 'Showing all runtime events'}
        </span>
      </div>

      {selectedPoint ? (
        <div className="timeline-details">
          <div className="timeline-meta">
            <strong>{stepLabel(selectedPoint, formatLocation)}</strong>
            <span>{selectedPoint.eventType}</span>
          </div>

          <div className="timeline-meta secondary-meta">
            <span>token: {eventToken(selectedPoint)}</span>
            <span>
              code focus:{' '}
              {formatLocation(selectedPoint) ?? selectedPoint.sourceDefinition ?? 'n/a'}
            </span>
          </div>

          <div className="timeline-meta secondary-meta">
            <span>source: {selectedPoint.sourceLabel ?? 'n/a'}</span>
            <span>data depth: {selectedPoint.dataStack.length}</span>
          </div>

          {selectedPoint.callStack && selectedPoint.callStack.length > 0 ? (
            <div className="timeline-callstack">
              <strong>Call Stack</strong>
              <div className="timeline-callstack-list">
                {callStackFrames.map((frame, index) => (
                  <button
                    key={`${frame}-${index}`}
                    type="button"
                    className={`timeline-callstack-frame ${index === selectedFrameIndex ? 'is-active' : ''}`}
                    onClick={() => setSelectedFrameIndex(index)}
                    title={`Select frame ${frame}`}
                  >
                    {frame}
                  </button>
                ))}
              </div>
              <div className="timeline-frame-scope">
                <strong>Frame Scope</strong>
                <div className="timeline-frame-grid">
                  <span>frame</span>
                  <span>{selectedFrame ?? '-'}</span>
                  <span>depth</span>
                  <span>{callStackFrames.length === 0 ? '-' : `${selectedFrameIndex + 1} / ${callStackFrames.length}`}</span>
                  <span>S0</span>
                  <span>{selectedPoint.dataStack.length > 0 ? selectedPoint.dataStack[selectedPoint.dataStack.length - 1] : '-'}</span>
                  <span>R0</span>
                  <span>{selectedPoint.returnStack.length > 0 ? selectedPoint.returnStack[selectedPoint.returnStack.length - 1] : '-'}</span>
                  <span>I</span>
                  <span>{selectedPoint.loopI ?? '-'}</span>
                  <span>J</span>
                  <span>{selectedPoint.loopJ ?? '-'}</span>
                  <span>LOOP#</span>
                  <span>{selectedPoint.loopDepth ?? 0}</span>
                  <span>HERE</span>
                  <span>{selectedPoint.here ?? '-'}</span>
                  <span>BASE</span>
                  <span>{selectedPoint.base ?? '-'}</span>
                </div>
                <span className="muted timeline-frame-note">
                  Locals are not modeled yet; showing stack/register probes at this frame boundary.
                </span>
              </div>
            </div>
          ) : null}

          <div className="timeline-stack-block">
            <strong>Stack Snapshot</strong>
            {stackLine('Data', selectedPoint.dataStack)}
            {stackLine('Return', selectedPoint.returnStack)}
            {stackLine('Float', selectedPoint.floatStack)}
          </div>

          {selectedPoint.errorMessage ? (
            <div className="timeline-meta secondary-meta">
              <span>error: {selectedPoint.errorMessage}</span>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="muted timeline-empty">Run buffer or REPL input to inspect timeline events.</div>
      )}
    </div>
  );
}
