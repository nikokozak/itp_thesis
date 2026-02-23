import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { EngineHarness } from '../testing/engine-harness';
import { generateStackSafeProgram } from '../testing/generators';

const FUZZ_RUNS = Number(process.env.FORTH_FUZZ_RUNS ?? 220);
const SNAPSHOT_RUNS = Number(process.env.FORTH_SNAPSHOT_RUNS ?? 120);

describe('ForthEngine property checks', () => {
  it('compiled and interpreted forms are stack-equivalent for generated stack-safe programs', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 0x7fffffff }), (seed) => {
        const program = generateStackSafeProgram(seed, { maxOps: 60 });

        const direct = new EngineHarness();
        const compiled = new EngineHarness();

        const directResult = direct.run(program.directProgram, { recordInput: true, sourceLabel: 'direct' });
        const compiledResult = compiled.run(program.compiledProgram, { recordInput: true, sourceLabel: 'compiled' });

        expect(directResult.ok).toBe(true);
        expect(compiledResult.ok).toBe(true);

        const directState = direct.getState();
        const compiledState = compiled.getState();

        expect(compiledState.dataStack).toEqual(directState.dataStack);
        expect(compiledState.returnStack).toEqual(directState.returnStack);
        expect(compiledState.output.join('')).toEqual(directState.output.join(''));

        expect(direct.assertEventInvariants()).toEqual([]);
        expect(compiled.assertEventInvariants()).toEqual([]);
      }),
      { numRuns: FUZZ_RUNS }
    );
  });

  it('snapshot restore is behavior-preserving for continuation programs', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 0x7fffffff }),
        fc.integer({ min: 0, max: 0x7fffffff }),
        (seedA, seedB) => {
          const baseProgram = generateStackSafeProgram(seedA, { maxOps: 45 });
          const continuation = generateStackSafeProgram(seedB, { maxOps: 45 });

          const left = new EngineHarness();
          const right = new EngineHarness();

          const leftBase = left.run(baseProgram.directProgram, { recordInput: true, sourceLabel: 'base' });
          const rightBase = right.run(baseProgram.directProgram, { recordInput: true, sourceLabel: 'base' });
          expect(leftBase.ok).toBe(true);
          expect(rightBase.ok).toBe(true);

          const snap = left.engine.createSnapshot();
          right.engine.restoreSnapshot(snap);

          const leftNext = left.run(continuation.directProgram, { recordInput: true, sourceLabel: 'next' });
          const rightNext = right.run(continuation.directProgram, { recordInput: true, sourceLabel: 'next' });
          expect(leftNext.ok).toBe(true);
          expect(rightNext.ok).toBe(true);

          expect(right.getState().dataStack).toEqual(left.getState().dataStack);
          expect(right.getState().returnStack).toEqual(left.getState().returnStack);
          expect(right.getState().output.join('')).toEqual(left.getState().output.join(''));
        }
      ),
      { numRuns: SNAPSHOT_RUNS }
    );
  });
});
