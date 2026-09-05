/**
 * Typed API client.
 *
 * Read-only. There is no method here that starts a real scientific stage,
 * because the backend exposes none: development execution is CLI-controlled and
 * the sealed final test is CLI plus freeze-policy controlled.
 */

import type {
  AtomView, BenchmarkRow, Capabilities, ProviderStatus, RunDetail, RunEvent,
} from './contracts';

const BASE = '/api/v1';

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    signal: signal ?? null,
    headers: { accept: 'application/json' },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { message?: string; detail?: string };
      detail = body.message ?? body.detail ?? detail;
    } catch {
      /* non-JSON error body; the status text stands */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export const api = {
  health: () => get<{ status: string; api_version: string }>('/../healthz'),
  capabilities: (s?: AbortSignal) => get<Capabilities>('/capabilities', s),
  providers: (s?: AbortSignal) => get<{ providers: ProviderStatus[] }>('/providers', s),
  runs: (s?: AbortSignal) => get<{ runs: Array<Record<string, unknown>> }>('/runs', s),
  run: (id: string, s?: AbortSignal) => get<RunDetail>(`/runs/${id}`, s),
  atoms: (id: string, s?: AbortSignal) => get<{ atoms: AtomView[] }>(`/runs/${id}/atoms`, s),
  trace: (id: string, after = 0, s?: AbortSignal) =>
    get<{ events: RunEvent[]; spans: string[] }>(`/runs/${id}/trace?after=${after}`, s),
  benchmarks: (s?: AbortSignal) =>
    get<{ methods: BenchmarkRow[]; required_wins: number; empirical_results_available: boolean }>(
      '/benchmarks', s),
  manuscriptAssets: (s?: AbortSignal) =>
    get<{ tables: unknown[]; figures: unknown[]; results_manifest_present: boolean }>(
      '/manuscript/assets', s),
  preregistration: (s?: AbortSignal) =>
    get<{ binding: boolean; accounting: Record<string, number>; unresolved: unknown[];
          models_pinned: boolean; final_test: string }>('/preregistration/status', s),

  /** DEMO_MODE only. The backend refuses via policy in research mode. */
  startDemoRun: async (seed = 2, budget = 300): Promise<{ run_id: string; marker: string }> => {
    const res = await fetch(`${BASE}/demo/runs?seed=${seed}&budget=${budget}`, {
      method: 'POST', headers: { accept: 'application/json' },
    });
    if (!res.ok) throw new ApiError(res.status, 'demo run refused');
    return (await res.json()) as { run_id: string; marker: string };
  },
};

/**
 * Live event stream with replay-from-sequence.
 *
 * On reconnect the client sends the last sequence it saw and the server replays
 * exactly what was missed. Nothing is interpolated: a gap is surfaced as a gap,
 * because a synthesised event would be indistinguishable from a real one.
 */
export function streamEvents(
  runId: string, afterSequence: number, onEvent: (e: RunEvent) => void,
): () => void {
  const source = new EventSource(`${BASE}/runs/${runId}/stream?after=${afterSequence}`);
  source.onmessage = (msg) => {
    try { onEvent(JSON.parse(msg.data) as RunEvent); } catch { /* malformed frame ignored */ }
  };
  source.onerror = () => source.close();
  return () => source.close();
}
