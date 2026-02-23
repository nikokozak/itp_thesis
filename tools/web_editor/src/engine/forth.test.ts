import { describe, expect, it } from 'vitest';
import { ForthEngine } from './forth';

describe('ForthEngine', () => {
  it('defines and executes a basic compiled word', () => {
    const engine = new ForthEngine();
    const result = engine.runWithRecovery(': SQUARE DUP * ; 9 SQUARE', {
      recordInput: true,
      sourceLabel: 'test',
    });

    expect(result.ok).toBe(true);
    expect(engine.getDataStack()).toEqual([81]);
  });

  it('restores pre-execution state after runtime error', () => {
    const engine = new ForthEngine();
    engine.runWithRecovery('42', { recordInput: false });
    const before = engine.getDataStack();

    const result = engine.runWithRecovery('DROP DROP', { recordInput: true, sourceLabel: 'test' });
    expect(result.ok).toBe(false);
    expect(engine.getDataStack()).toEqual(before);
  });

  it('supports base switching for number parsing', () => {
    const engine = new ForthEngine();

    const decimal = engine.runWithRecovery('255', { recordInput: false });
    expect(decimal.ok).toBe(true);

    const hex = engine.runWithRecovery('HEX FF', { recordInput: false });
    expect(hex.ok).toBe(true);

    expect(engine.getDataStack()).toEqual([255, 255]);
  });

  it('emits source line/token metadata for compiled execution steps', () => {
    const engine = new ForthEngine();
    const events: Array<{ word?: string; sourceLine?: number; sourceToken?: string }> = [];
    engine.onEvent((event) => {
      if (event.type === 'execute') {
        events.push({
          word: event.word,
          sourceLine: event.sourceLine,
          sourceToken: event.sourceToken,
        });
      }
    });

    const program = `: SQUARE ( x -- x2 )\n  DUP *\n;\n3 SQUARE`;
    const result = engine.runWithRecovery(program, { recordInput: true, sourceLabel: 'test' });
    expect(result.ok).toBe(true);

    const dupExec = events.find((event) => event.word === 'DUP');
    const mulExec = events.find((event) => event.word === '*');
    const callExec = events.find((event) => event.word === 'SQUARE' && event.sourceToken === 'SQUARE');

    expect(dupExec?.sourceLine).toBe(2);
    expect(mulExec?.sourceLine).toBe(2);
    expect(callExec?.sourceLine).toBe(4);
  });

  it('captures call stack metadata for nested execution events', () => {
    const engine = new ForthEngine();
    const stacksByWord = new Map<string, string[]>();

    engine.onEvent((event) => {
      if (event.type === 'execute' && event.word) {
        stacksByWord.set(`${event.word}-${event.sequenceNumber}`, event.callStack ?? []);
      }
    });

    const result = engine.runWithRecovery(': DOUBLE DUP + ; : WRAP DOUBLE ; 7 WRAP', {
      recordInput: true,
      sourceLabel: 'test',
    });
    expect(result.ok).toBe(true);

    const dupCallStack = Array.from(stacksByWord.entries()).find(([key]) => key.startsWith('DUP-'))?.[1];
    const addCallStack = Array.from(stacksByWord.entries()).find(([key]) => key.startsWith('+-'))?.[1];
    const wrapCallStack = Array.from(stacksByWord.entries()).find(([key]) => key.startsWith('WRAP-'))?.[1];

    expect(dupCallStack).toEqual(['WRAP', 'DOUBLE', 'DUP']);
    expect(addCallStack).toEqual(['WRAP', 'DOUBLE', '+']);
    expect(wrapCallStack).toEqual(['WRAP']);
  });

  it('supports silent execution without emitting instrumentation events', () => {
    const engine = new ForthEngine();
    let eventCount = 0;
    engine.onEvent(() => {
      eventCount += 1;
    });

    engine.execute('2 3 +', { recordInput: true, silent: true, sourceLabel: 'watch' });
    expect(engine.getDataStack()).toEqual([5]);
    expect(eventCount).toBe(0);

    engine.runWithRecovery('4', { recordInput: true, sourceLabel: 'normal' });
    expect(eventCount).toBeGreaterThan(0);
  });

  it('emits register metadata (BASE/HERE) with events', () => {
    const engine = new ForthEngine();
    const executeEvents: Array<{ word?: string; here?: number; base?: number }> = [];
    engine.onEvent((event) => {
      if (event.type === 'execute') {
        executeEvents.push({
          word: event.word,
          here: event.here,
          base: event.base,
        });
      }
    });

    const result = engine.runWithRecovery('HEX 1 ALLOT HERE', { recordInput: true, sourceLabel: 'test' });
    expect(result.ok).toBe(true);

    const hereExec = executeEvents.find((event) => event.word === 'HERE');
    expect(hereExec?.base).toBe(16);
    expect(hereExec?.here).toBe(1);
  });

  it('emits loop pointer metadata (I/J/depth) for nested loops', () => {
    const engine = new ForthEngine();
    const executeEvents: Array<{ word?: string; loopI?: number; loopJ?: number; loopDepth?: number }> = [];
    engine.onEvent((event) => {
      if (event.type === 'execute') {
        executeEvents.push({
          word: event.word,
          loopI: event.loopI,
          loopJ: event.loopJ,
          loopDepth: event.loopDepth,
        });
      }
    });

    const program = ': NEST 2 0 DO 3 1 DO I J + DROP LOOP LOOP ; NEST';
    const result = engine.runWithRecovery(program, { recordInput: true, sourceLabel: 'test' });
    expect(result.ok).toBe(true);

    const iEvent = executeEvents.find((event) => event.word === 'I' && event.loopDepth === 2);
    const jEvent = executeEvents.find((event) => event.word === 'J' && event.loopDepth === 2);
    expect(iEvent?.loopI).toBe(1);
    expect(jEvent?.loopJ).toBe(0);
  });
});
