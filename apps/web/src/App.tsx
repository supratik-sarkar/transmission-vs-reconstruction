import { useCallback, useEffect, useMemo, useState } from 'react';
import { AtomDetail, AtomInspector } from './components/AtomInspector';
import { BenchmarkArena } from './components/BenchmarkArena';
import { CausalInspector } from './components/CausalInspector';
import { DiffView } from './components/DiffView';
import { MultiHop } from './components/MultiHop';
import { Panel } from './components/Panel';
import { PipelinePane } from './components/PipelinePane';
import { Providers } from './components/Providers';
import { Provenance } from './components/Provenance';
import { SourcePane } from './components/SourcePane';
import { Timeline } from './components/Timeline';
import { api } from './lib/api';
import type {
  AtomView, BenchmarkRow, Capabilities, ProviderStatus, RunDetail, RunEvent,
} from './lib/contracts';

type View = 'workspace' | 'benchmark' | 'multihop' | 'provenance' | 'system';

const VIEWS: Array<{ id: View; label: string }> = [
  { id: 'workspace', label: 'Research workspace' },
  { id: 'benchmark', label: 'Benchmark arena' },
  { id: 'multihop', label: 'Multi-hop' },
  { id: 'provenance', label: 'Provenance' },
  { id: 'system', label: 'System' },
];

export function App() {
  const [view, setView] = useState<View>('workspace');
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [benchmarks, setBenchmarks] = useState<BenchmarkRow[]>([]);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [atoms, setAtoms] = useState<AtomView[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [sourceText, setSourceText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    Promise.allSettled([
      api.capabilities(ac.signal), api.providers(ac.signal), api.benchmarks(ac.signal),
    ]).then(([c, p, b]) => {
      if (c.status === 'fulfilled') setCaps(c.value);
      if (p.status === 'fulfilled') setProviders(p.value.providers);
      if (b.status === 'fulfilled') setBenchmarks(b.value.methods);
    });
    return () => ac.abort();
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    const [detail, atomList, trace] = await Promise.all([
      api.run(runId), api.atoms(runId), api.trace(runId, 0),
    ]);
    setRun(detail); setAtoms(atomList.atoms); setEvents(trace.events);
    setSelected(null);
    const loaded = trace.events.find((e) => e.stage === 'load_source');
    setSourceText(typeof loaded?.payload?.source_text === 'string'
      ? (loaded.payload.source_text as string) : '');
  }, []);

  const startDemo = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const { run_id } = await api.startDemoRun(2, 300);
      await loadRun(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'demo run refused');
    } finally { setBusy(false); }
  }, [loadRun]);

  const selectedAtom = useMemo(
    () => atoms.find((a) => a.atom_id === selected) ?? null, [atoms, selected]);
  const runKind = run?.kind ?? 'MOCK';
  const badgeClass = runKind === 'FINAL_TEST' ? 'badge--final'
    : runKind === 'DEVELOPMENT' ? 'badge--dev'
    : runKind === 'DEMO' ? 'badge--demo' : 'badge--mock';

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="topbar">
        <h1>Transmission&nbsp;vs&nbsp;Reconstruction</h1>
        <span className={`badge ${badgeClass}`}>
          {runKind === 'FINAL_TEST' ? '🔒 Final test — sealed' : runKind}
        </span>
        <div className="meta">
          <div>Mode<b>{caps?.settings?.mode as string ?? '—'}</b></div>
          <div>Run<b>{run?.run_id ?? '—'}</b></div>
          <div>Orchestrator<b>
            {caps?.orchestration?.langgraph_available ? 'langgraph' : 'sequential'}</b></div>
          <div>Results<b>{caps?.empirical_results_available ? 'available' : 'NOT RUN'}</b></div>
        </div>
      </header>

      <nav className="nav" aria-label="Primary">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)}
                  aria-current={view === v.id ? 'page' : undefined}>{v.label}</button>
        ))}
        <button className="action" style={{ marginLeft: 'auto', alignSelf: 'center' }}
                onClick={startDemo} disabled={busy || !caps?.browser_may_launch_synthetic_run}
                title={caps?.browser_may_launch_synthetic_run
                  ? 'Run the synthetic mock pipeline'
                  : 'Synthetic runs require DEMO_MODE'}>
          {busy ? 'Running…' : 'Run synthetic demo'}
        </button>
      </nav>

      <main id="main">
        {error && <p className="notice" style={{ marginBottom: 16, borderLeftColor: 'var(--lost)' }}>
          {error}</p>}

        {view === 'workspace' && (
          <div className="workspace">
            <Panel title="Source" area="area-source">
              <SourcePane text={sourceText} atoms={atoms} selected={selected}
                          onSelect={setSelected} />
            </Panel>
            <Panel title="Live handoff pipeline" area="area-pipeline">
              <PipelinePane events={events} />
              <div style={{ marginTop: 20 }}>
                <DiffView natural={run?.relay_message ?? ''}
                          counterfactual={selected ? run?.counterfactuals?.[selected] ?? null : null}
                          atom={selectedAtom} />
              </div>
            </Panel>
            <Panel title="Atom inspector" area="area-atoms">
              <AtomInspector atoms={atoms} selected={selected} onSelect={setSelected} />
            </Panel>
            <Panel title="Causal inspector" area="area-causal">
              <AtomDetail atom={selectedAtom} />
              <hr style={{ border: 0, borderTop: '1px solid var(--ink-100)', margin: '20px 0' }} />
              <CausalInspector decomposition={
                run && 'endpoint_fidelity' in (run.decomposition ?? {})
                  ? (run.decomposition as never) : null} />
            </Panel>
            <Panel title="Event timeline" area="area-timeline">
              <Timeline events={events} />
            </Panel>
          </div>
        )}

        {view === 'benchmark' && (
          <Panel title="Benchmark arena">
            <BenchmarkArena rows={benchmarks} requiredWins={3}
                            hasResults={caps?.empirical_results_available ?? false} />
          </Panel>
        )}

        {view === 'multihop' && (
          <Panel title="Multi-hop playback"><MultiHop atoms={atoms} /></Panel>
        )}

        {view === 'provenance' && (
          <Panel title="Provenance explorer">
            <Provenance run={run} manifestPresent={false} />
          </Panel>
        )}

        {view === 'system' && (
          <div style={{ display: 'grid', gap: 16 }}>
            <Panel title="Providers"><Providers providers={providers} /></Panel>
            <Panel title="Preregistration and final test">
              <p className="notice notice--sealed">
                <strong>{'SEALED — NOT EXECUTED'}</strong>. The sealed final test cannot be
                launched from the browser in any mode. It requires the CLI and a valid
                final-test freeze record.
              </p>
              <table style={{ marginTop: 16 }}>
                <tbody>
                  <tr><td>LangSmith</td><td className="num">
                    {caps?.langsmith?.enabled ? 'enabled' : 'disabled'}</td></tr>
                  <tr><td>NeMo Guardrails</td><td className="num">
                    {caps?.guardrails?.enabled ? 'enabled (demo perimeter)' : 'disabled'}</td></tr>
                  <tr><td>OTel SDK</td><td className="num">
                    {caps?.telemetry?.otel_sdk_available ? 'available' : 'not installed'}</td></tr>
                  <tr><td>Browser may launch final test</td><td className="num">
                    <strong>{String(caps?.browser_may_launch_final_test ?? false)}</strong></td></tr>
                </tbody>
              </table>
            </Panel>
          </div>
        )}
      </main>
    </div>
  );
}
