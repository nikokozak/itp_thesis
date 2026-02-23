import { ForthEngine } from '../engine/forth';
import type { EngineExecuteOptions, ForthEvent } from '../engine/types';

export interface HarnessRunResult {
  ok: boolean;
  error?: string;
}

export interface EngineHarnessState {
  dataStack: number[];
  returnStack: number[];
  output: string[];
  events: ForthEvent[];
}

export class EngineHarness {
  readonly engine: ForthEngine;
  private readonly events: ForthEvent[] = [];
  private readonly output: string[] = [];
  private unsubscribe: () => void;

  constructor(engine = new ForthEngine()) {
    this.engine = engine;
    this.unsubscribe = this.engine.onEvent((event) => {
      this.events.push(event);
      if (event.type === 'output' && event.text !== undefined) {
        this.output.push(event.text);
      }
    });
  }

  dispose(): void {
    this.unsubscribe();
  }

  clearTrace(): void {
    this.events.length = 0;
    this.output.length = 0;
  }

  run(source: string, options: EngineExecuteOptions = { recordInput: true, sourceLabel: 'test' }): HarnessRunResult {
    const result = this.engine.runWithRecovery(source, options);
    return {
      ok: result.ok,
      error: result.error?.message,
    };
  }

  getState(): EngineHarnessState {
    return {
      dataStack: this.engine.getDataStack(),
      returnStack: this.engine.getReturnStack(),
      output: [...this.output],
      events: [...this.events],
    };
  }

  assertEventInvariants(): string[] {
    const issues: string[] = [];
    const events = this.events;

    let previousSequence = 0;
    let previousDataDepth = 0;
    let previousReturnDepth = 0;

    for (const event of events) {
      if (event.sequenceNumber <= previousSequence) {
        issues.push(`Sequence number did not increase: ${event.sequenceNumber} after ${previousSequence}`);
      }
      previousSequence = event.sequenceNumber;

      for (const value of event.dataStack) {
        if ((value | 0) !== value) {
          issues.push(`Non-cell value on data stack at seq ${event.sequenceNumber}: ${value}`);
        }
      }

      for (const value of event.returnStack) {
        if ((value | 0) !== value) {
          issues.push(`Non-cell value on return stack at seq ${event.sequenceNumber}: ${value}`);
        }
      }

      if (event.type === 'push' && event.stack === 'data') {
        if (event.dataStack.length !== previousDataDepth + 1) {
          issues.push(`Data push depth mismatch at seq ${event.sequenceNumber}`);
        }
      }

      if (event.type === 'pop' && event.stack === 'data') {
        if (event.dataStack.length !== Math.max(0, previousDataDepth - 1)) {
          issues.push(`Data pop depth mismatch at seq ${event.sequenceNumber}`);
        }
      }

      if (event.type === 'push' && event.stack === 'return') {
        if (event.returnStack.length !== previousReturnDepth + 1) {
          issues.push(`Return push depth mismatch at seq ${event.sequenceNumber}`);
        }
      }

      if (event.type === 'pop' && event.stack === 'return') {
        if (event.returnStack.length !== Math.max(0, previousReturnDepth - 1)) {
          issues.push(`Return pop depth mismatch at seq ${event.sequenceNumber}`);
        }
      }

      previousDataDepth = event.dataStack.length;
      previousReturnDepth = event.returnStack.length;
    }

    return issues;
  }
}

export interface ScenarioStep {
  source: string;
  options?: EngineExecuteOptions;
  expectOk?: boolean;
  expectStack?: number[];
  expectReturnStack?: number[];
  expectOutputIncludes?: string[];
  expectErrorIncludes?: string;
  resetTraceBefore?: boolean;
}

export function runScenario(steps: ScenarioStep[]): {
  harness: EngineHarness;
  failures: string[];
} {
  const harness = new EngineHarness();
  const failures: string[] = [];

  for (const [index, step] of steps.entries()) {
    if (step.resetTraceBefore) {
      harness.clearTrace();
    }

    const result = harness.run(step.source, step.options ?? { recordInput: true, sourceLabel: 'scenario' });
    const state = harness.getState();

    if (step.expectOk !== undefined && result.ok !== step.expectOk) {
      failures.push(`step ${index}: expected ok=${step.expectOk}, got ${result.ok}`);
    }

    if (step.expectStack && JSON.stringify(state.dataStack) !== JSON.stringify(step.expectStack)) {
      failures.push(`step ${index}: stack mismatch expected ${JSON.stringify(step.expectStack)} got ${JSON.stringify(state.dataStack)}`);
    }

    if (step.expectReturnStack && JSON.stringify(state.returnStack) !== JSON.stringify(step.expectReturnStack)) {
      failures.push(
        `step ${index}: return stack mismatch expected ${JSON.stringify(step.expectReturnStack)} got ${JSON.stringify(state.returnStack)}`
      );
    }

    if (step.expectOutputIncludes) {
      const outputJoined = state.output.join('');
      for (const needle of step.expectOutputIncludes) {
        if (!outputJoined.includes(needle)) {
          failures.push(`step ${index}: expected output to include '${needle}', got '${outputJoined}'`);
        }
      }
    }

    if (step.expectErrorIncludes && (!result.error || !result.error.includes(step.expectErrorIncludes))) {
      failures.push(
        `step ${index}: expected error containing '${step.expectErrorIncludes}', got '${result.error ?? '<none>'}'`
      );
    }
  }

  return {
    harness,
    failures,
  };
}
