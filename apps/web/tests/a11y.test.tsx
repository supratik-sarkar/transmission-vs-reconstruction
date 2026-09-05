import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { axe } from 'vitest-axe';
import './setup';
import { AtomInspector } from '../src/components/AtomInspector';
import { Providers } from '../src/components/Providers';

describe('accessibility', () => {
  it('atom inspector has no detectable violations', async () => {
    const { container } = render(<AtomInspector selected={null} onSelect={() => {}} atoms={[{
      atom_id: 'a1', role: 'scope', canonical_value: 'north america',
      surface_form: 'North America', char_start: 0, char_end: 13, focal: true,
      transmitted: 0, inclusion_probability: 0.25, r_minus: 1, d_plus: 1,
      delta_avail: 0, edit_mechanism: 'ins', status: 'ESTIMATED',
    }]} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('provider table has no detectable violations', async () => {
    const { container } = render(<Providers providers={[{
      provider: 'mock', state: 'CONFIGURED', sdk_available: true,
      secret_configured: false, model_pinned: true, model: 'mock-deterministic-v1',
      capabilities_resolved: true,
    }]} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
