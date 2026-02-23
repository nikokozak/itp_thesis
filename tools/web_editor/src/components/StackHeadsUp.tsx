import type { StackHudState } from '../utils/stack-hud';

interface StackHeadsUpProps {
  state: StackHudState;
}

function renderStackValues(values: number[]): string {
  if (values.length === 0) {
    return '[ ]';
  }
  return `[ ${values.join(' ')} ]`;
}

export function StackHeadsUp({ state }: StackHeadsUpProps) {
  return (
    <section className="stack-hud" aria-label="Stack heads-up display">
      <div className="stack-hud-header">
        <strong>Stack</strong>
        <div className="stack-hud-registers-inline">
          <span>SP {state.dataStack.length}</span>
          <span>RP {state.returnStack.length}</span>
          <span>FP {state.floatStack.length}</span>
        </div>
        <span className="hint">
          {state.source === 'timeline'
            ? `Step ${state.stepIndex ?? '-'}${state.totalSteps ? `/${state.totalSteps}` : ''}`
            : 'Live'}
        </span>
      </div>

      <div className="stack-hud-rows">
        <div className="stack-hud-row">
          <span className="stack-hud-label">Data</span>
          <code>{renderStackValues(state.dataStack)}</code>
        </div>
        <div className="stack-hud-row">
          <span className="stack-hud-label">Return</span>
          <code>{renderStackValues(state.returnStack)}</code>
        </div>
        <div className="stack-hud-row">
          <span className="stack-hud-label">Float</span>
          <code>{renderStackValues(state.floatStack)}</code>
        </div>
      </div>
    </section>
  );
}
