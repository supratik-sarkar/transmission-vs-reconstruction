import { describe, expect, it } from 'vitest';
import { EVENT_SCHEMA_VERSION, STAGE_ORDER } from '../src/lib/contracts';

/**
 * Contract tests. The Python side is canonical; these assert that the
 * TypeScript mirror has not drifted from it.
 */
describe('event contract', () => {
  it('pins the schema version', () => {
    expect(EVENT_SCHEMA_VERSION).toBe('1.0.0');
  });

  it('mirrors the frozen scientific topology exactly', () => {
    expect(STAGE_ORDER).toEqual([
      'prepare_run', 'load_source', 'atomize', 'sample_focals', 'relay',
      'match_transmission', 'natural_receiver', 'construct_interventions',
      'counterfactual_receiver', 'deterministic_match', 'estimate',
      'export_artifacts', 'finalize_run',
    ]);
  });

  it('places every intervention stage after transmission is observed', () => {
    // Constructing a counterfactual before T is known would invert the design.
    expect(STAGE_ORDER.indexOf('construct_interventions'))
      .toBeGreaterThan(STAGE_ORDER.indexOf('match_transmission'));
    expect(STAGE_ORDER.indexOf('sample_focals'))
      .toBeLessThan(STAGE_ORDER.indexOf('relay'));
  });
});
