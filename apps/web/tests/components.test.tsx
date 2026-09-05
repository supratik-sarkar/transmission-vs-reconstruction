import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AtomInspector } from '../src/components/AtomInspector';
import { BenchmarkArena } from '../src/components/BenchmarkArena';
import { CausalInspector } from '../src/components/CausalInspector';
import { Providers } from '../src/components/Providers';
import { Timeline } from '../src/components/Timeline';
import type { AtomView, RunEvent } from '../src/lib/contracts';

const atom = (over: Partial<AtomView> = {}): AtomView => ({
  atom_id: 'a1', role: 'scope', canonical_value: 'north america',
  surface_form: 'North America', char_start: 0, char_end: 13, focal: true,
  transmitted: 0, inclusion_probability: 0.25, r_minus: 1, d_plus: 1,
  delta_avail: 0, edit_mechanism: 'ins', status: 'ESTIMATED', ...over,
});

describe('AtomInspector', () => {
  it('selects an atom on click', async () => {
    const onSelect = vi.fn();
    render(<AtomInspector atoms={[atom()]} selected={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByText('north america'));
    expect(onSelect).toHaveBeenCalledWith('a1');
  });

  it('shows n/a rather than 0 for an unsampled inclusion probability', () => {
    render(<AtomInspector atoms={[atom({ inclusion_probability: null, focal: false })]}
                          selected={null} onSelect={() => {}} />);
    expect(screen.getByText('n/a')).toBeInTheDocument();
  });
});

describe('CausalInspector', () => {
  it('says NOT ESTIMATED when there is no decomposition', () => {
    render(<CausalInspector decomposition={null} />);
    expect(screen.getByText(/NOT ESTIMATED/)).toBeInTheDocument();
  });
});

describe('BenchmarkArena', () => {
  it('never shows a result value before an experiment has run', () => {
    render(<BenchmarkArena requiredWins={3} hasResults={false} rows={[
      { method: 'provence', role: 'PRIMARY_CAUSAL', status: 'NOT_READY',
        eligible: false, reason: 'unresolved', unresolved_fields: ['commit'] },
    ]} />);
    expect(screen.getAllByText('NOT RUN').length).toBeGreaterThanOrEqual(3);
  });

  it('marks an endpoint-only method TRANSMISSION UNOBSERVED', () => {
    render(<BenchmarkArena requiredWins={3} hasResults={false} rows={[
      { method: 'parallelcomp', role: 'ENDPOINT_ONLY', status: 'ENDPOINT_ONLY',
        eligible: false, reason: 'latent', unresolved_fields: [] },
    ]} />);
    expect(screen.getByText('TRANSMISSION UNOBSERVED')).toBeInTheDocument();
  });
});

describe('Providers', () => {
  it('renders presence only and no key material', () => {
    const { container } = render(<Providers providers={[{
      provider: 'openai', state: 'CONFIGURED', sdk_available: true,
      secret_configured: true, model_pinned: false, model: null,
      capabilities_resolved: false,
    }]} />);
    expect(screen.getByText('configured')).toBeInTheDocument();
    expect(screen.getByText('MUST_PIN')).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/sk-|Bearer|AIza/);
  });
});

describe('Timeline', () => {
  it('surfaces a sequence gap instead of interpolating it', () => {
    const e = (sequence: number): RunEvent => ({
      schema_version: '1.0.0', event_id: `e${sequence}`, sequence, run_id: 'r',
      timestamp: '', stage: 'relay', event_type: 'stage.completed', status: 'ok',
      payload: {}, artifact_refs: [],
    });
    render(<Timeline events={[e(1), e(4)]} />);
    expect(screen.getByText(/2 event\(s\) missing/)).toBeInTheDocument();
    expect(screen.getByText('not interpolated')).toBeInTheDocument();
  });
});
