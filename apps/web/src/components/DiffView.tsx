import type { AtomView } from '../lib/contracts';

/**
 * Natural vs counterfactual handoff.
 *
 * Deletion and insertion get DIFFERENT visual semantics because they are
 * different operations with different artefact profiles. The diff is computed
 * over whole lines for display only; the intervention itself was constructed by
 * the backend editor and is never recomputed here.
 */
export function DiffView(
  { natural, counterfactual, atom }:
  { natural: string; counterfactual: string | null; atom: AtomView | null },
) {
  if (!atom) return <p className="unavailable">Select a focal atom to see its intervention.</p>;
  if (!counterfactual) {
    return (
      <p className="unavailable">
        NOT APPLICABLE — no counterfactual was constructed for this atom
        {atom.focal ? ' (the edit was rejected and recorded as a failure).' : '.'}
      </p>
    );
  }
  const a = natural.split('\n');
  const b = counterfactual.split('\n');
  const mechanism = atom.edit_mechanism === 'del' ? 'DELETION' : 'INSERTION';

  return (
    <>
      <p style={{ marginBottom: 12, fontSize: 12.5 }}>
        <strong>Mechanism</strong> <code>{mechanism}</code> ·{' '}
        {atom.edit_mechanism === 'del'
          ? 'the atom was present and every canonical-equivalent occurrence was removed'
          : 'the atom was absent and was appended; insertion overruns the budget rather than displacing'}
      </p>
      <div className="diff">
        <div>
          <h3 style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em',
                       color: 'var(--ink-500)' }}>Natural handoff</h3>
          <pre>{a.map((line, i) => (
            <div key={i}>{!b.includes(line) ? <del>{line}</del> : line}</div>
          ))}</pre>
        </div>
        <div>
          <h3 style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em',
                       color: 'var(--ink-500)' }}>Counterfactual</h3>
          <pre>{b.map((line, i) => (
            <div key={i}>{!a.includes(line) ? <ins>{line}</ins> : line}</div>
          ))}</pre>
        </div>
      </div>
    </>
  );
}
