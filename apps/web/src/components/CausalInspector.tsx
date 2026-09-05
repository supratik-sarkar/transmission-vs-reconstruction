import type { Decomposition } from '../lib/contracts';
import { metric, signed } from '../lib/format';

/**
 * The decomposition, rendered exactly as delivered.
 *
 * Nothing is computed here. A = Rbar_0 + Tbar*Deltabar + Cov(T,Delta) is
 * displayed, and the residual the backend reports is shown alongside so the
 * identity is visibly closed rather than merely asserted.
 */
export function CausalInspector({ decomposition }: { decomposition: Decomposition | null }) {
  if (!decomposition || !('endpoint_fidelity' in decomposition)) {
    return <p className="unavailable">NOT ESTIMATED — no instrumented records in this run.</p>;
  }
  const d = decomposition;
  return (
    <>
      <dl className="metric-grid">
        <div className="metric" data-emphasis="true"><dt>A</dt><dd>{metric(d.endpoint_fidelity)}</dd></div>
        <div className="metric"><dt>R̄₀</dt><dd>{metric(d.r_bar_zero)}</dd></div>
        <div className="metric"><dt>T̄</dt><dd>{metric(d.t_bar)}</dd></div>
        <div className="metric" data-emphasis="true"><dt>C_comm</dt><dd>{signed(d.c_comm)}</dd></div>
        <div className="metric" data-emphasis="true"><dt>C_recon</dt><dd>{metric(d.c_recon)}</dd></div>
        <div className="metric"><dt>Cov(T,Δ)</dt><dd>{signed(d.alignment)}</dd></div>
      </dl>

      <table style={{ marginTop: 20 }}>
        <caption className="sr-only">Decomposition terms and diagnostics</caption>
        <tbody>
          <tr><td>Volume T̄·Δ̄</td><td className="num">{signed(d.volume)}</td></tr>
          <tr><td>Identity residual</td>
              <td className="num">{d.identity_residual.toExponential(2)}</td></tr>
          <tr><td>R<sup>obs</sup></td><td className="num">{metric(d.r_observational)}</td></tr>
          <tr><td>Selection bias</td><td className="num">{signed(d.selection_bias)}</td></tr>
          <tr><td>…max route discrepancy</td>
              <td className="num">
                {d.selection_bias_max_discrepancy === null
                  ? <span className="unavailable">NOT ESTIMATED</span>
                  : d.selection_bias_max_discrepancy.toExponential(2)}
              </td></tr>
        </tbody>
      </table>
      <p className="notice notice--synthetic" style={{ marginTop: 16 }}>
        The selection bias is computed three independent ways; the discrepancy above is
        the largest disagreement between them.
      </p>
    </>
  );
}
