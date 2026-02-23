import { useMemo, useState } from 'react';
import { useEngineStore } from '../store/engine-store';
import type { TimelinePoint } from '../store/engine-store';
import { useUiStore } from '../store/ui-store';
import { resolveMemoryView } from '../utils/memory-view';

interface MemoryInspectorProps {
  visible: boolean;
  activePoint?: TimelinePoint;
  selectedStep?: number;
  totalSteps?: number;
}

const PAGE_SIZE = 32;
const STACK_WINDOW_SIZE = 24;

interface MemoryRow {
  cellIndex: number;
  address: number;
  value: number;
  hex: string;
  bytes: string;
  ascii: string;
  tag?: string;
}

interface StackRow {
  slot: number;
  virtualAddress: number;
  value: number;
  hex: string;
}

function byteToAscii(value: number): string {
  if (value >= 32 && value <= 126) {
    return String.fromCharCode(value);
  }
  return '.';
}

function toHex(value: number, width: number): string {
  return value.toString(16).toUpperCase().padStart(width, '0');
}

function stackCellClass(value: number, kind: 'data' | 'return' | 'float'): string {
  const bucket = Math.abs(value) % 6;
  const base = `stack-cell stack-color-${bucket}`;
  if (kind === 'return') {
    return `${base} return-cell`;
  }
  if (kind === 'float') {
    return `${base} float-cell`;
  }
  return base;
}

function toStackRows(stack: number[]): StackRow[] {
  return stack
    .map((value, slot) => ({
      slot,
      virtualAddress: slot * 4,
      value,
      hex: `0x${toHex(value >>> 0, 8)}`,
    }))
    .reverse();
}

export function MemoryInspector({ visible, activePoint, selectedStep, totalSteps }: MemoryInspectorProps) {
  const engine = useEngineStore((state) => state.engine);
  const dictionary = useEngineStore((state) => state.dictionary);
  const latestSeq = useEngineStore((state) => state.events[state.events.length - 1]?.sequenceNumber ?? 0);
  const runtimeDataStack = useEngineStore((state) => state.dataStack);
  const runtimeReturnStack = useEngineStore((state) => state.returnStack);
  const runtimeFloatStack = useEngineStore((state) => state.floatStack);
  const memoryViewMode = useUiStore((state) => state.memoryViewMode);
  const setMemoryViewMode = useUiStore((state) => state.setMemoryViewMode);
  const [startCell, setStartCell] = useState(0);
  const [nonZeroOnly, setNonZeroOnly] = useState(false);

  const liveLoopFrames = engine.getLoopFrames();
  const liveLoopI = liveLoopFrames.at(-1)?.index;
  const liveLoopJ = liveLoopFrames.length >= 2 ? liveLoopFrames[liveLoopFrames.length - 2]?.index : undefined;
  const resolvedView = resolveMemoryView(
    {
      dataStack: runtimeDataStack,
      returnStack: runtimeReturnStack,
      floatStack: runtimeFloatStack,
      here: engine.getHere(),
      base: engine.getBase(),
      loopI: liveLoopI,
      loopJ: liveLoopJ,
      loopDepth: liveLoopFrames.length,
    },
    activePoint,
    memoryViewMode
  );

  const dataStack = resolvedView.dataStack;
  const returnStack = resolvedView.returnStack;
  const floatStack = resolvedView.floatStack;
  const here = resolvedView.here;
  const base = resolvedView.base;
  const loopI = resolvedView.loopI;
  const loopJ = resolvedView.loopJ;
  const loopDepth = resolvedView.loopDepth;
  const displayedSeq = resolvedView.source === 'timeline' ? resolvedView.sequenceNumber ?? latestSeq : latestSeq;

  const variableAddressMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const word of dictionary) {
      if (word.type === 'variable' && typeof word.address === 'number') {
        map.set(word.address, word.name);
      }
    }
    return map;
  }, [dictionary]);

  const rows = (() => {
    const memory = engine.getMemoryCells();
    const bytes = engine.getMemoryBytes();
    const candidateIndices = nonZeroOnly
      ? Array.from(memory)
          .map((value, index) => ({ value, index }))
          .filter((entry) => entry.value !== 0)
          .map((entry) => entry.index)
      : Array.from({ length: memory.length }, (_, index) => index);

    const window = candidateIndices.slice(startCell, startCell + PAGE_SIZE);

    return window.map((cellIndex) => {
      const address = cellIndex * 4;
      const value = memory[cellIndex];
      const b0 = bytes[address] ?? 0;
      const b1 = bytes[address + 1] ?? 0;
      const b2 = bytes[address + 2] ?? 0;
      const b3 = bytes[address + 3] ?? 0;

      const tag = variableAddressMap.get(address);
      return {
        cellIndex,
        address,
        value,
        hex: `0x${toHex(value >>> 0, 8)}`,
        bytes: `${toHex(b0, 2)} ${toHex(b1, 2)} ${toHex(b2, 2)} ${toHex(b3, 2)}`,
        ascii: `${byteToAscii(b0)}${byteToAscii(b1)}${byteToAscii(b2)}${byteToAscii(b3)}`,
        tag,
      } satisfies MemoryRow;
    });
  })();

  const nonZeroCount = (() => {
    const memory = engine.getMemoryCells();
    let count = 0;
    for (const value of memory) {
      if (value !== 0) {
        count += 1;
      }
    }
    return count;
  })();

  const dataStackRows = toStackRows(dataStack).slice(0, STACK_WINDOW_SIZE);
  const returnStackRows = toStackRows(returnStack).slice(0, STACK_WINDOW_SIZE);
  const floatStackRows = toStackRows(floatStack).slice(0, STACK_WINDOW_SIZE);

  if (!visible) {
    return null;
  }

  return (
    <div className="memory-pane">
      <div className="panel-header">
        <span>Memory Inspector</span>
        <span className="hint">Stack state + register view + linear memory cells.</span>
      </div>

      <div className="memory-summary">
        <span>Seq: {displayedSeq}</span>
        <span>BASE: {base}</span>
        <span>HERE: {here}</span>
        <span>Non-zero cells: {nonZeroCount}</span>
        <span>{nonZeroOnly ? 'Showing non-zero window' : 'Showing sequential window'}</span>
      </div>

      <div className="memory-view-toggle">
        <button
          type="button"
          className={memoryViewMode === 'timeline' ? 'is-active' : ''}
          onClick={() => setMemoryViewMode('timeline')}
          disabled={!activePoint}
          title="Show stack/register state from selected timeline step"
        >
          Selected Step
        </button>
        <button
          type="button"
          className={memoryViewMode === 'live' ? 'is-active' : ''}
          onClick={() => setMemoryViewMode('live')}
          title="Show current runtime state after execution"
        >
          Live Runtime
        </button>
        <span className="hint">
          {resolvedView.source === 'timeline'
            ? `Showing step ${selectedStep ?? '-'}${totalSteps ? `/${totalSteps}` : ''}, seq ${resolvedView.sequenceNumber ?? '-'}`
            : 'Showing current runtime state'}
        </span>
      </div>

      <div className="memory-register-grid">
        <div className="memory-register">
          <span className="memory-register-label">SP</span>
          <span className="memory-register-value">{dataStack.length}</span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">RP</span>
          <span className="memory-register-value">{returnStack.length}</span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">FP</span>
          <span className="memory-register-value">{floatStack.length}</span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">S (TOS)</span>
          <span className="memory-register-value">
            {dataStack.length > 0 ? dataStack[dataStack.length - 1] : '-'}
          </span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">R (RTOS)</span>
          <span className="memory-register-value">
            {returnStack.length > 0 ? returnStack[returnStack.length - 1] : '-'}
          </span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">I</span>
          <span className="memory-register-value">{loopI ?? '-'}</span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">J</span>
          <span className="memory-register-value">{loopJ ?? '-'}</span>
        </div>
        <div className="memory-register">
          <span className="memory-register-label">Loop depth</span>
          <span className="memory-register-value">{loopDepth}</span>
        </div>
      </div>

      <div className="memory-stack-overview">
        <div className="memory-stack-panel">
          <div className="memory-stack-title">Data stack visualizer</div>
          <div className="memory-stack-visual">
            {dataStackRows.length === 0 ? <div className="muted">empty</div> : null}
            {dataStackRows.map((row, idx) => (
              <div
                key={`data-${row.slot}-${row.value}-${idx}`}
                className={`${stackCellClass(row.value, 'data')} ${idx === 0 ? 'is-top' : ''}`}
                title={`slot ${row.slot} addr ${row.virtualAddress}`}
              >
                <span className="stack-index">{row.slot}</span>
                <span>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="memory-stack-panel">
          <div className="memory-stack-title">Return stack visualizer</div>
          <div className="memory-stack-visual">
            {returnStackRows.length === 0 ? <div className="muted">empty</div> : null}
            {returnStackRows.map((row, idx) => (
              <div
                key={`return-${row.slot}-${row.value}-${idx}`}
                className={`${stackCellClass(row.value, 'return')} ${idx === 0 ? 'is-top' : ''}`}
                title={`slot ${row.slot} addr ${row.virtualAddress}`}
              >
                <span className="stack-index">{row.slot}</span>
                <span>{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="memory-stack-panel">
          <div className="memory-stack-title">Float stack visualizer</div>
          <div className="memory-stack-visual">
            {floatStackRows.length === 0 ? <div className="muted">empty</div> : null}
            {floatStackRows.map((row, idx) => (
              <div
                key={`float-${row.slot}-${row.value}-${idx}`}
                className={`${stackCellClass(row.value, 'float')} ${idx === 0 ? 'is-top' : ''}`}
                title={`slot ${row.slot} addr ${row.virtualAddress}`}
              >
                <span className="stack-index">{row.slot}</span>
                <span>{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="memory-stack-table-wrap">
        <div className="memory-section-title">Data stack memory (virtual cells)</div>
        <table className="memory-table memory-stack-table">
          <thead>
            <tr>
              <th>Top</th>
              <th>Slot</th>
              <th>Virt Addr</th>
              <th>Int32</th>
              <th>Hex</th>
            </tr>
          </thead>
          <tbody>
            {dataStackRows.map((row, idx) => (
              <tr key={`row-${row.slot}-${idx}`} className={idx === 0 ? 'is-top-row' : ''}>
                <td>{idx === 0 ? 'TOS' : ''}</td>
                <td>{row.slot}</td>
                <td>{row.virtualAddress}</td>
                <td>{row.value}</td>
                <td>{row.hex}</td>
              </tr>
            ))}
            {dataStackRows.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  Data stack empty.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="memory-controls">
        <button
          type="button"
          onClick={() => setStartCell((value) => Math.max(0, value - PAGE_SIZE))}
        >
          Prev
        </button>
        <span>Offset {startCell}</span>
        <button
          type="button"
          onClick={() => setStartCell((value) => value + PAGE_SIZE)}
        >
          Next
        </button>
        <button
          type="button"
          onClick={() => setStartCell(Math.max(0, Math.floor(here / 4) - Math.floor(PAGE_SIZE / 2)))}
        >
          Jump HERE
        </button>
        <button
          type="button"
          onClick={() => {
            setNonZeroOnly((value) => !value);
            setStartCell(0);
          }}
        >
          {nonZeroOnly ? 'Show All Cells' : 'Show Non-Zero Only'}
        </button>
      </div>

      <div className="memory-explainer">
        {nonZeroCount === 0
          ? 'Linear memory is zero until code writes with !, +!, C!, VARIABLE, or string allocation; stack activity is shown above.'
          : 'Repeated numbers can be expected when values are initialized similarly; use tag/bytes columns to inspect exact storage.'}
      </div>

      <div className="memory-table-wrap">
        <table className="memory-table">
          <thead>
            <tr>
              <th>Addr</th>
              <th>Cell #</th>
              <th>Int32</th>
              <th>Hex</th>
              <th>Bytes</th>
              <th>ASCII</th>
              <th>Tag</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.address}>
                <td>{row.address}</td>
                <td>{row.cellIndex}</td>
                <td>{row.value}</td>
                <td>{row.hex}</td>
                <td>{row.bytes}</td>
                <td>{row.ascii}</td>
                <td>{row.tag ?? '-'}</td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="muted">
                  No cells in this window.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
