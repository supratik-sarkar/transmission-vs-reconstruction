import type { RunEvent, Stage } from '../lib/contracts';
import { STAGE_ORDER } from '../lib/contracts';

const GLYPH: Record<string, string> = { ok: '●', running: '◐', failed: '✕', pending: '○' };

/**
 * Live pipeline.
 *
 * Status is derived from REAL EVENT STATE, never from a frontend timer: a stage
 * shows as running only because a `stage.started` event arrived without its
 * completion.
 */
export function PipelinePane({ events }: { events: RunEvent[] }) {
  const status = new Map<Stage, 'ok' | 'running' | 'failed' | 'pending'>();
  const detail = new Map<Stage, string>();
  for (const stage of STAGE_ORDER) status.set(stage, 'pending');
  for (const e of events) {
    if (e.event_type === 'stage.started') status.set(e.stage, 'running');
    else if (e.event_type === 'stage.completed') status.set(e.stage, 'ok');
    else if (e.event_type === 'stage.failed') status.set(e.stage, 'failed');
    const keys = Object.keys(e.payload ?? {});
    if (keys.length) {
      const summary = keys.slice(0, 2)
        .map((k) => `${k}=${String((e.payload as Record<string, unknown>)[k])}`)
        .join('  ');
      detail.set(e.stage, summary.slice(0, 60));
    }
  }

  return (
    <ol className="pipeline" aria-label="Handoff pipeline stages">
      {STAGE_ORDER.map((stage) => {
        const s = status.get(stage) ?? 'pending';
        return (
          <li key={stage} className="stage" data-status={s}
              aria-current={s === 'running' ? 'step' : undefined}>
            <span className="glyph" aria-hidden="true">{GLYPH[s]}</span>
            <span className="name">{stage}</span>
            <span className="detail">
              <span className="sr-only">{s}</span>
              {detail.get(stage) ?? ''}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
