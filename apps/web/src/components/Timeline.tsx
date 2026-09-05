import type { RunEvent } from '../lib/contracts';

/** Canonical event log. Sequence gaps are shown, never filled. */
export function Timeline({ events }: { events: RunEvent[] }) {
  if (!events.length) return <p className="unavailable">NOT RUN — no events.</p>;
  const rows: Array<RunEvent | { gap: number }> = [];
  let expected = 1;
  for (const e of events) {
    if (e.sequence > expected) rows.push({ gap: e.sequence - expected });
    rows.push(e);
    expected = e.sequence + 1;
  }
  return (
    <div className="timeline" role="log" aria-label="Run event timeline">
      {rows.map((row, i) =>
        'gap' in row ? (
          <div key={`gap${i}`} className="row" style={{ color: 'var(--lost)' }}>
            <span className="seq">—</span>
            <span>{row.gap} event(s) missing</span>
            <span>gap</span>
            <span>not interpolated</span>
          </div>
        ) : (
          <div key={row.event_id} className="row">
            <span className="seq">{row.sequence}</span>
            <span>{row.stage}</span>
            <span>{row.event_type.replace('stage.', '')}</span>
            <span style={{ color: 'var(--ink-500)' }}>
              {Object.entries(row.payload ?? {}).slice(0, 3)
                .map(([k, v]) => `${k}=${String(v)}`).join('  ').slice(0, 90)}
            </span>
          </div>
        ),
      )}
    </div>
  );
}
