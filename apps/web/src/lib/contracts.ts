/**
 * API contracts.
 *
 * These mirror the Pydantic/dataclass shapes on the Python side, which is
 * canonical. `npm run typecheck` plus the contract tests in tests/contract.test.ts
 * guard against drift; the schema_version field makes a mismatch loud rather
 * than silent.
 *
 * Optional numeric fields are `number | null`, never `number | undefined`
 * defaulting to 0. A zero and an unmeasured quantity must never render alike.
 */

export const EVENT_SCHEMA_VERSION = '1.0.0';

export type Stage =
  | 'prepare_run' | 'load_source' | 'atomize' | 'sample_focals' | 'relay'
  | 'match_transmission' | 'natural_receiver' | 'construct_interventions'
  | 'counterfactual_receiver' | 'deterministic_match' | 'estimate'
  | 'export_artifacts' | 'finalize_run';

export const STAGE_ORDER: readonly Stage[] = [
  'prepare_run', 'load_source', 'atomize', 'sample_focals', 'relay',
  'match_transmission', 'natural_receiver', 'construct_interventions',
  'counterfactual_receiver', 'deterministic_match', 'estimate',
  'export_artifacts', 'finalize_run',
] as const;

export type EventStatus = 'ok' | 'running' | 'failed' | 'skipped';

export interface ArtifactRef {
  artifact_id: string; kind: string; path: string; sha256: string; bytes: number;
}

export interface RunEvent {
  schema_version: string;
  event_id: string;
  sequence: number;
  run_id: string;
  timestamp: string;
  stage: Stage;
  event_type: string;
  status: EventStatus;
  payload: Record<string, unknown>;
  artifact_refs: ArtifactRef[];
}

export type AtomStatus = 'ESTIMATED' | 'NOT_ESTIMATED' | 'NOT_APPLICABLE';

export interface AtomView {
  atom_id: string;
  role: 'entity' | 'scope' | 'period' | 'numeric' | 'provenance';
  canonical_value: string;
  surface_form: string;
  char_start: number;
  char_end: number;
  focal: boolean;
  transmitted: number | null;
  inclusion_probability: number | null;
  r_minus: number | null;
  d_plus: number | null;
  delta_avail: number | null;
  edit_mechanism: string | null;
  status: AtomStatus;
}

export interface Decomposition {
  endpoint_fidelity: number;
  r_bar_zero: number;
  t_bar: number;
  delta_bar: number;
  volume: number;
  alignment: number;
  c_comm: number;
  c_recon: number;
  phi: number | null;
  r_observational: number | null;
  selection_bias: number | null;
  selection_bias_identity: number | null;
  selection_bias_conditional: number | null;
  selection_bias_max_discrepancy: number | null;
  prob_delta_negative: number | null;
  identity_residual: number;
  n_atoms: number;
  n_documents: number;
}

export interface RunDetail {
  run_id: string;
  kind: 'MOCK' | 'DEMO' | 'CALIBRATION' | 'DEVELOPMENT' | 'FINAL_TEST';
  mode: string;
  status: string;
  marker: string;
  evidentiary_status: 'NONE' | 'REAL';
  summary: Record<string, unknown>;
  decomposition: Decomposition | Record<string, never>;
  provider_calls: Record<string, unknown>;
  spans: string[];
  relay_message: string;
  counterfactuals: Record<string, string>;
}

export interface ProviderStatus {
  provider: string;
  state: 'CONFIGURED' | 'NOT_CONFIGURED' | 'SDK_MISSING' | 'DISABLED';
  sdk_available: boolean;
  secret_configured: boolean;   // presence only; no key material ever
  model_pinned: boolean;
  model: string | null;
  capabilities_resolved: boolean;
}

export interface BenchmarkRow {
  method: string;
  role: string;
  status: string;
  eligible: boolean;
  reason: string;
  unresolved_fields: string[];
}

export interface Capabilities {
  api_version: string;
  settings: Record<string, unknown>;
  orchestration: { stages: Stage[]; fixed: boolean; langgraph_available: boolean };
  telemetry: { otel_sdk_available: boolean };
  langsmith: { requested: boolean; enabled: boolean; reason: string };
  guardrails: { requested: boolean; enabled: boolean; reason: string };
  policy: Record<string, unknown>;
  browser_may_launch_final_test: boolean;
  browser_may_launch_synthetic_run: boolean;
  empirical_results_available: boolean;
}

/** Sentinels. The UI renders these words rather than inventing a number. */
export const NOT_OBSERVED = 'NOT OBSERVED';
export const NOT_ESTIMATED = 'NOT ESTIMATED';
export const NOT_APPLICABLE = 'NOT APPLICABLE';
export const NOT_RUN = 'NOT RUN';
export const SEALED = 'SEALED — NOT EXECUTED';
