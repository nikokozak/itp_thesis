import { useEffect, useMemo, useRef } from 'react';
import type { TimelinePoint } from '../store/engine-store';

interface StackTimelineProps {
  timeline: TimelinePoint[];
  cursor: number;
  onCursorChange: (index: number) => void;
  formatLocation: (point: TimelinePoint) => string | undefined;
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

function chipText(point: TimelinePoint): string {
  if (point.eventType === 'define') {
    return point.definitionName ?? 'define';
  }
  if (point.eventType === 'push' || point.eventType === 'pop') {
    return point.value !== undefined ? `${point.eventType} ${point.value}` : point.eventType;
  }
  if (point.eventType === 'input') {
    return 'input';
  }
  if (point.eventType === 'output') {
    return 'output';
  }
  return point.word ?? point.eventType;
}

export function StackTimeline({ timeline, cursor, onCursorChange, formatLocation }: StackTimelineProps) {
  const stripRef = useRef<HTMLDivElement>(null);

  const points = useMemo(() => {
    return timeline.map((point, index) => ({
      ...point,
      index,
      depth: point.dataStack.length,
      label: stepLabel(point, formatLocation),
    }));
  }, [formatLocation, timeline]);

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) {
      return;
    }

    const active = strip.querySelector<HTMLButtonElement>(`button[data-index="${cursor}"]`);
    if (!active) {
      return;
    }

    const activeCenter = active.offsetLeft + active.offsetWidth / 2;
    const targetScroll = Math.max(0, activeCenter - strip.clientWidth / 2);
    strip.scrollTo({ left: targetScroll, behavior: 'smooth' });
  }, [cursor]);

  const maxIndex = Math.max(0, points.length - 1);

  return (
    <div className="timeline-pane compact">
      <div className="timeline-scrubber-row">
        <input
          type="range"
          min={0}
          max={maxIndex}
          value={points.length === 0 ? 0 : cursor}
          onChange={(event) => onCursorChange(Number(event.target.value))}
          disabled={points.length <= 1}
          aria-label="Timeline scrubber"
        />
        <span className="timeline-scrubber-label">{points.length === 0 ? 'No steps' : `${cursor + 1} / ${points.length}`}</span>
      </div>

      <div className="timeline-meta secondary-meta timeline-depth-legend">
        <span>d:N on chip = data stack depth after event.</span>
      </div>

      {points.length === 0 ? (
        <div className="muted timeline-empty">No timeline data yet.</div>
      ) : (
        <div className="timeline-strip" ref={stripRef}>
          {points.map((point) => (
            <button
              key={`${point.sequenceNumber}-${point.index}`}
              data-index={point.index}
              type="button"
              className={`timeline-point compact ${point.index === cursor ? 'is-active' : ''}`}
              onClick={() => onCursorChange(point.index)}
              title={`${point.label}${point.sourceLabel ? ` (${point.sourceLabel})` : ''}`}
            >
              <span className="timeline-depth" title="Data stack depth after this event">
                d:{point.depth}
              </span>
              <span className="timeline-word-chip">{chipText(point)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
