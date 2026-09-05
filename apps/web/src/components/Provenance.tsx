import type { RunDetail } from '../lib/contracts';

/**
 * Provenance explorer.
 *
 * Every displayed result must resolve to an artifact. Until real results exist
 * there is nothing to resolve, and the pane says so rather than showing an empty
 * table that looks like a pending fetch.
 */
export function Provenance(
  { run, manifestPresent }: { run: RunDetail | null; manifestPresent: boolean },
) {
  if (!run) return <p className="unavailable">NOT RUN — select a run.</p>;
  const calls = run.provider_calls as Record<string, unknown>;
  return (
    <>
      <table>
        <caption className="sr-only">Run provenance chain</caption>
        <tbody>
          <tr><td>Run ID</td><td className="num"><code>{run.run_id}</code></td></tr>
          <tr><td>Kind</td><td className="num"><code>{run.kind}</code></td></tr>
          <tr><td>Mode</td><td className="num"><code>{run.mode}</code></td></tr>
          <tr><td>Evidentiary status</td>
              <td className="num"><strong>{run.evidentiary_status}</strong></td></tr>
          <tr><td>Provider calls</td>
              <td className="num">{String(calls.total_calls ?? 0)}</td></tr>
          <tr><td>Telemetry spans</td><td className="num">{run.spans.length}</td></tr>
          <tr><td>RESULTS_MANIFEST.json</td>
              <td className="num">{manifestPresent
                ? 'present'
                : <span className="unavailable">absent — no empirical results exist</span>}</td></tr>
        </tbody>
      </table>
      <p className="notice notice--synthetic" style={{ marginTop: 16 }}>
        {run.marker}
      </p>
      <h3 style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em',
                   color: 'var(--ink-500)', marginTop: 24 }}>Telemetry spans</h3>
      <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-700)' }}>
        {run.spans.map((s) => <li key={s}>{s}</li>)}
      </ul>
    </>
  );
}
