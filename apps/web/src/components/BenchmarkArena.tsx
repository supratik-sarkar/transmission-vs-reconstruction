import type { BenchmarkRow } from '../lib/contracts';
import { NOT_RUN } from '../lib/contracts';

const METHOD_ORDER = [
  'causalrelay', 'provence', 'adaptive_queryselect', 'cpc', 'llmlingua2',
  'recomp_extractive', 'full_context', 'head_truncation', 'uniform_atoms', 'vanilla_relay',
];

/**
 * Benchmark arena — readiness only.
 *
 * There are no result columns because there are no results. An endpoint-only
 * method shows TRANSMISSION UNOBSERVED rather than a value inferred from
 * downstream correctness: manufacturing a pseudo-T for a latent compressed
 * state would fabricate the very quantity the project measures.
 */
export function BenchmarkArena(
  { rows, requiredWins, hasResults }:
  { rows: BenchmarkRow[]; requiredWins: number; hasResults: boolean },
) {
  const ordered = [...rows].sort(
    (a, b) => METHOD_ORDER.indexOf(a.method) - METHOD_ORDER.indexOf(b.method));
  const eligible = ordered.filter((r) => r.eligible && r.role === 'PRIMARY_CAUSAL').length;

  return (
    <>
      <p className="notice" style={{ marginBottom: 16 }}>
        <strong>{eligible} of 4</strong> primary comparators are benchmark-eligible;{' '}
        <strong>{requiredWins}</strong> are required before any comparative language is
        permitted. No comparison has been run.
      </p>
      <table>
        <caption className="sr-only">Comparator readiness</caption>
        <thead>
          <tr>
            <th scope="col">Method</th><th scope="col">Role</th><th scope="col">Status</th>
            <th scope="col" className="num">A</th>
            <th scope="col" className="num">C_comm</th>
            <th scope="col" className="num">C_recon</th>
            <th scope="col">Transmission</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((r) => {
            const endpointOnly = r.role === 'ENDPOINT_ONLY';
            return (
              <tr key={r.method}>
                <td><code>{r.method}</code></td>
                <td style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>{r.role}</td>
                <td>
                  <span className={`chip chip--${r.eligible ? 'transmitted'
                    : endpointOnly ? 'unknown' : 'lost'}`}>{r.status}</span>
                </td>
                <td className="num"><span className="unavailable">{NOT_RUN}</span></td>
                <td className="num"><span className="unavailable">{NOT_RUN}</span></td>
                <td className="num"><span className="unavailable">{NOT_RUN}</span></td>
                <td style={{ fontSize: 11.5 }}>
                  {endpointOnly
                    ? <span className="chip chip--unknown">TRANSMISSION UNOBSERVED</span>
                    : <span style={{ color: 'var(--ink-500)' }}>auditable (textual)</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!hasResults && (
        <p className="notice notice--sealed" style={{ marginTop: 16 }}>
          Result columns stay empty until a sealed final test has run under a valid
          freeze record. They are not placeholders awaiting a value — the experiment
          has not been performed.
        </p>
      )}
    </>
  );
}
