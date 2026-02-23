import { describe, expect, it } from 'vitest';
import { analyzeSourceStackEffects, createInitialEffectDatabase } from './stack-effect';

describe('stack-effect analysis', () => {
  it('infers simple linear definitions', () => {
    const source = ': SQUARE DUP * ;';
    const result = analyzeSourceStackEffects(source, createInitialEffectDatabase());

    expect(result.definitions).toHaveLength(1);
    expect(result.definitions[0].effect.inputs).toBe(1);
    expect(result.definitions[0].effect.outputs).toBe(1);
    expect(result.definitions[0].errors).toEqual([]);
  });

  it('flags branch depth mismatches', () => {
    const source = ': BADIF ( x -- ? ) IF 1 ELSE 1 2 THEN ;';
    const result = analyzeSourceStackEffects(source, createInitialEffectDatabase());

    expect(result.definitions[0].errors.length).toBeGreaterThan(0);
    expect(result.definitions[0].errors.join(' ')).toContain('ELSE branch depth');
  });

  it('marks unknown words as opaque warnings', () => {
    const source = ': WEIRD FOO BAR ;';
    const result = analyzeSourceStackEffects(source, createInitialEffectDatabase());

    expect(result.definitions[0].effect.opaque).toBe(true);
    expect(result.definitions[0].warnings.some((warning) => warning.includes('Unknown/opaque'))).toBe(true);
  });
});
