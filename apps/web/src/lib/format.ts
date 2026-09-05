import { NOT_ESTIMATED, NOT_OBSERVED, NOT_APPLICABLE } from './contracts';
import type { AtomView } from './contracts';

/** Format a scientific quantity. A missing value is NAMED, never zero-filled. */
export function metric(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_ESTIMATED;
  return value.toFixed(digits);
}

export function signed(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_ESTIMATED;
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

export type AtomFate = 'transmitted' | 'reconstructed' | 'lost' | 'unknown';

/**
 * Classify an atom's fate from CANONICAL backend values only.
 *
 * This is presentation, not science: it reads T and R^- as delivered and never
 * derives an estimand. Anything unmeasured stays `unknown` rather than being
 * inferred from downstream correctness.
 */
export function fateOf(atom: AtomView): AtomFate {
  if (atom.transmitted === null) return 'unknown';
  if (atom.transmitted === 1) return 'transmitted';
  if (atom.r_minus === null) return 'unknown';
  return atom.r_minus > 0 ? 'reconstructed' : 'lost';
}

export const FATE_LABEL: Record<AtomFate, string> = {
  transmitted: 'TRANSMITTED',
  reconstructed: 'RECONSTRUCTED',
  lost: 'LOST',
  unknown: NOT_OBSERVED,
};

export function atomStatusLabel(atom: AtomView): string {
  switch (atom.status) {
    case 'ESTIMATED': return 'ESTIMATED';
    case 'NOT_ESTIMATED': return NOT_ESTIMATED;
    default: return NOT_APPLICABLE;
  }
}
