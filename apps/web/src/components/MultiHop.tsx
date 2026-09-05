import { useEffect, useState } from 'react';
import type { AtomView } from '../lib/contracts';
import { FATE_LABEL, fateOf } from '../lib/format';

const DEPTHS = [1, 2, 3, 5] as const;

/**
 * Multi-hop playback over synthetic fixture data.
 *
 * Shows how atoms fare across successive handoffs. No monotonicity is implied:
 * an atom reconstructed at hop h may be transmitted at h+1, so a value can
 * reappear — that is a real property of the process, not a rendering bug.
 */
export function MultiHop({ atoms }: { atoms: AtomView[] }) {
  const [depth, setDepth] = useState<number>(1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const id = window.setInterval(() => {
      setDepth((d) => {
        const i = DEPTHS.indexOf(d as (typeof DEPTHS)[number]);
        if (i >= DEPTHS.length - 1) { setPlaying(false); return d; }
        return DEPTHS[i + 1]!;
      });
    }, reduced ? 1 : 1400);
    return () => window.clearInterval(id);
  }, [playing]);

  const focal = atoms.filter((a) => a.focal);

  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        {DEPTHS.map((d) => (
          <button key={d} className="action" aria-pressed={depth === d}
                  onClick={() => { setPlaying(false); setDepth(d); }}>h = {d}</button>
        ))}
        <button className="action" onClick={() => setPlaying((p) => !p)}
                style={{ marginLeft: 'auto' }}>
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>

      <p className="notice notice--synthetic" style={{ marginBottom: 16 }}>
        Synthetic fixture data. Depth {depth} of a {DEPTHS.join(', ')} sweep. These
        trajectories are fabricated to exercise the view and carry no evidentiary status.
      </p>

      <table>
        <caption className="sr-only">Atom fate by handoff depth</caption>
        <thead>
          <tr><th scope="col">Role</th><th scope="col">Value</th><th scope="col">Fate at h={depth}</th></tr>
        </thead>
        <tbody>
          {focal.length === 0
            ? <tr><td colSpan={3}><span className="unavailable">NOT RUN</span></td></tr>
            : focal.map((atom) => {
                // Fixture behaviour: attrition with depth, except reconstructed
                // atoms which may persist — deliberately non-monotone.
                const base = fateOf(atom);
                const fate = depth === 1 || base === 'reconstructed'
                  ? base : (depth >= 3 && base === 'transmitted' ? 'reconstructed' : base);
                return (
                  <tr key={atom.atom_id}>
                    <td><code>{atom.role}</code></td>
                    <td>{atom.canonical_value}</td>
                    <td><span className={`chip chip--${fate}`}>{FATE_LABEL[fate]}</span></td>
                  </tr>
                );
              })}
        </tbody>
      </table>
    </>
  );
}
