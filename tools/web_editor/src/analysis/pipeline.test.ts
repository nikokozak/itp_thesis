import { describe, expect, it } from 'vitest';
import { propagateLabelsForSource } from './annotations';
import { analyzeSourceStackEffects, createInitialEffectDatabase } from './stack-effect';
import { buildCrossReference } from './xref';

describe('analysis pipeline', () => {
  it('tracks xrefs and inferred effects across chained definitions', () => {
    const source = `
      : SQUARE DUP * ;
      : CUBE DUP DUP * * ;
      : FOO SQUARE CUBE + ;
    `;

    const result = analyzeSourceStackEffects(source, createInitialEffectDatabase());
    const xref = buildCrossReference(source, result.effectDb);

    expect(result.effectDb.SQUARE).toBeDefined();
    expect(result.effectDb.CUBE).toBeDefined();
    expect(result.effectDb.FOO).toBeDefined();

    expect(xref.SQUARE.callers).toContain('FOO');
    expect(xref.CUBE.callers).toContain('FOO');
    expect(xref.FOO.callees).toContain('SQUARE');
    expect(xref.FOO.callees).toContain('CUBE');
  });

  it('propagates labels with expression simplification', () => {
    const source = `: H ( x -- y ) DUP * 1 + ;`;
    const stackResult = analyzeSourceStackEffects(source, createInitialEffectDatabase());
    const labels = propagateLabelsForSource(source, stackResult.effectDb);

    expect(labels).toHaveLength(1);
    const trace = labels[0];

    const mulStep = trace.steps.find((step) => step.token.text === '*');
    expect(mulStep?.after.join(' ')).toContain('x²');

    const plusStep = trace.steps.find((step) => step.token.text === '+');
    expect(plusStep?.after.length).toBe(1);
    expect(plusStep?.after[0]).toContain('x²+1');
  });
});
