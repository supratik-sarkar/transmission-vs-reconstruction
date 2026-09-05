import type { AtomView } from '../lib/contracts';
import { atomStatusLabel, FATE_LABEL, fateOf, metric } from '../lib/format';

export function AtomInspector(
  { atoms, selected, onSelect }:
  { atoms: AtomView[]; selected: string | null; onSelect: (id: string | null) => void },
) {
  if (!atoms.length) return <p className="unavailable">NOT RUN — no atom inventory.</p>;
  return (
    <table>
      <caption className="sr-only">Atom inventory with transmission status</caption>
      <thead>
        <tr>
          <th scope="col">Role</th><th scope="col">Value</th>
          <th scope="col">Fate</th><th scope="col" className="num">π</th>
        </tr>
      </thead>
      <tbody>
        {atoms.map((atom) => {
          const fate = fateOf(atom);
          return (
            <tr key={atom.atom_id} aria-selected={selected === atom.atom_id} tabIndex={0}
                onClick={() => onSelect(selected === atom.atom_id ? null : atom.atom_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSelect(selected === atom.atom_id ? null : atom.atom_id);
                }}>
              <td><code>{atom.role}</code></td>
              <td>{atom.canonical_value}</td>
              <td><span className={`chip chip--${fate}`}>{FATE_LABEL[fate]}</span></td>
              <td className="num">
                {atom.inclusion_probability === null
                  ? <span className="unavailable">n/a</span>
                  : metric(atom.inclusion_probability, 3)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Per-atom causal detail. Missing quantities are named, never zero-filled. */
export function AtomDetail({ atom }: { atom: AtomView | null }) {
  if (!atom) return <p className="unavailable">Select an atom to see its causal record.</p>;
  return (
    <>
      <dl className="metric-grid">
        <div className="metric">
          <dt>T<sub>iz</sub></dt>
          <dd>{atom.transmitted === null ? <span className="unavailable">NOT OBSERVED</span>
                                         : atom.transmitted}</dd>
        </div>
        <div className="metric"><dt>R⁻<sub>iz</sub></dt><dd>{metric(atom.r_minus, 3)}</dd></div>
        <div className="metric"><dt>D⁺<sub>iz</sub></dt><dd>{metric(atom.d_plus, 3)}</dd></div>
        <div className="metric" data-emphasis="true">
          <dt>Δᵃᵛ<sub>iz</sub></dt><dd>{metric(atom.delta_avail, 3)}</dd>
        </div>
      </dl>
      <p style={{ marginTop: 16, fontSize: 12.5 }}>
        <strong>Status</strong> <code>{atomStatusLabel(atom)}</code>
        {atom.edit_mechanism ? <> · <strong>Mechanism</strong> <code>{atom.edit_mechanism}</code></> : null}
      </p>
    </>
  );
}
