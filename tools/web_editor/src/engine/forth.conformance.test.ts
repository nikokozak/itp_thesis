import { describe, expect, it } from 'vitest';
import { runScenario } from '../testing/engine-harness';

describe('ForthEngine conformance scenarios', () => {
  it('covers arithmetic, memory, values, return stack, control flow, and string output', () => {
    const scenario = runScenario([
      {
        source: ': SQUARE DUP * ; 5 SQUARE',
        expectOk: true,
        expectStack: [25],
      },
      {
        source: 'VARIABLE X 17 X ! X @',
        expectOk: true,
        expectStack: [25, 17],
      },
      {
        source: '10 VALUE N N 5 TO N N',
        expectOk: true,
        expectStack: [25, 17, 10, 5],
      },
      {
        source: '3 >R 4 R> +',
        expectOk: true,
        expectStack: [25, 17, 10, 5, 7],
        expectReturnStack: [],
      },
      {
        source: ': PICKBRANCH ( n -- n ) DUP 0> IF 100 + ELSE 100 - THEN ; 2 PICKBRANCH -2 PICKBRANCH',
        expectOk: true,
        expectStack: [25, 17, 10, 5, 7, 102, -102],
      },
      {
        source: ': SUM10 0 10 0 DO I + LOOP ; SUM10',
        expectOk: true,
        expectStack: [25, 17, 10, 5, 7, 102, -102, 45],
      },
      {
        source: 'S" hi" TYPE',
        expectOk: true,
        expectOutputIncludes: ['hi'],
      },
    ]);

    expect(scenario.failures).toEqual([]);

    const invariantIssues = scenario.harness.assertEventInvariants();
    expect(invariantIssues).toEqual([]);
  });

  it('keeps stack stable on errors due to run-with-recovery', () => {
    const scenario = runScenario([
      {
        source: '42',
        expectOk: true,
        expectStack: [42],
      },
      {
        source: 'DROP DROP',
        expectOk: false,
        expectStack: [42],
        expectErrorIncludes: 'Data stack underflow',
      },
    ]);

    expect(scenario.failures).toEqual([]);
  });
});
