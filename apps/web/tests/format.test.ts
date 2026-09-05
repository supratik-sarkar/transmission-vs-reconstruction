import { describe, expect, it } from 'vitest';
import { fateOf, metric, signed } from '../src/lib/format';
import type { AtomView } from '../src/lib/contracts';

const base: AtomView = {
  atom_id: 'a', role: 'numeric', canonical_value: '6.2%', surface_form: '6.2%',
  char_start: 0, char_end: 4, focal: true, transmitted: null,
  inclusion_probability: null, r_minus: null, d_plus: null, delta_avail: null,
  edit_mechanism: null, status: 'NOT_ESTIMATED',
};

describe('metric formatting', () => {
  it('names a missing value instead of showing zero', () => {
    // A zero and an unmeasured quantity must never render alike.
    expect(metric(null)).toBe('NOT ESTIMATED');
    expect(metric(0)).toBe('0.0000');
    expect(metric(undefined)).toBe('NOT ESTIMATED');
    expect(metric(Number.NaN)).toBe('NOT ESTIMATED');
  });

  it('signs values explicitly', () => {
    expect(signed(0.25)).toBe('+0.2500');
    expect(signed(-0.25)).toBe('-0.2500');
    expect(signed(null)).toBe('NOT ESTIMATED');
  });
});

describe('atom fate classification', () => {
  it('is unknown when transmission was not observed', () => {
    expect(fateOf(base)).toBe('unknown');
  });

  it('reports transmitted when T = 1', () => {
    expect(fateOf({ ...base, transmitted: 1 })).toBe('transmitted');
  });

  it('distinguishes reconstruction from loss using R^- only', () => {
    expect(fateOf({ ...base, transmitted: 0, r_minus: 1 })).toBe('reconstructed');
    expect(fateOf({ ...base, transmitted: 0, r_minus: 0 })).toBe('lost');
  });

  it('never infers a fate from downstream correctness alone', () => {
    // D+ present but R^- unmeasured must stay unknown, not be inferred.
    expect(fateOf({ ...base, transmitted: 0, r_minus: null, d_plus: 1 })).toBe('unknown');
  });
});
