"""Decoder-regime classification for a provider-backed receiver.

The theory establishes results under two receiver regimes:

* **(D)** deterministic receiver -- a fixed input yields a fixed canonical outcome;
* **(S)** stochastic receiver -- a fixed input yields a draw.

Both are real theoretical cases and neither is deprecated here. What this module
enforces is the *empirical* rule: **provider documentation never assigns a
regime.** A snapshot guarantee is a statement about model weights, not about
sampling; and an undocumented ``seed`` parameter is an absence of evidence, not
evidence of stochasticity. Only the preregistered operational reproducibility
audit may promote a configuration out of :data:`DecoderRegime.NOT_AUDITED`.

The object being tested is the **canonical receiver outcome** -- the normalised
slot values that determine ``Y_iz`` -- not the raw bytes of the response and not
the provider's hidden reasoning. Byte identity is recorded alongside as an
operational diagnostic, because a configuration that is canonically stable while
being byte-unstable is worth knowing about, but it is not the scientific object.

Regime is a property of a *receiver request configuration*, not of a provider.
Two configurations of the same model can classify differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: Preregistered audit size: 100 representative receiver inputs, 10 repeats each.
#: The prompts must span the representative receiver/atom strata.
AUDIT_REQUIRED_INPUTS = 100
AUDIT_REQUIRED_REPEATS = 10

#: Candidate replication factors, in the order they are tried.
REPLICATION_GRID: tuple[int, ...] = (1, 2, 3, 5)

#: Under regime (S), the per-query decode variance must be driven below this
#: fraction of the document-level variance before it can be treated as a
#: second-order term. Frozen before any calibration data exists.
DECODE_VARIANCE_TARGET_RATIO = 0.10


class DecoderRegime(StrEnum):
    """Ternary state. A boolean here would be a category error.

    ``NOT_AUDITED`` is not "probably (S)". It is the honest statement that the
    experiment which distinguishes the two has not been run.
    """

    NOT_AUDITED = "NOT_AUDITED"
    D_CONFIRMED = "D_CONFIRMED"
    S_CONFIRMED = "S_CONFIRMED"


class RegimeAssignmentError(RuntimeError):
    """Raised when something tries to assign a regime from documentation."""


@dataclass(frozen=True, slots=True)
class ReceiverConfiguration:
    """The unit a regime is a property of.

    ``configuration_hash`` covers every request field that could change the
    output distribution: prompt template, slot schema, effort/thinking setting,
    tool set, response format, and any sampling parameter the provider accepts.
    """

    provider: str
    model_id: str
    configuration_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "configuration_hash": self.configuration_hash,
        }


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """The strongest identity evidence a provider exposes, recorded per call.

    No field is required, because providers differ in what they expose, and a
    missing field is itself evidence about how well the run can be pinned. What
    is *not* permitted is inventing a field the provider did not return.
    """

    requested_model_id: str
    returned_model_id: str | None = None
    documented_version_semantics: str | None = None
    provider_backend_version: str | None = None
    system_fingerprint: str | None = None
    request_id: str | None = None
    timestamp_utc: str | None = None
    sdk_version: str | None = None
    api_version: str | None = None
    configuration_hash: str | None = None

    @property
    def alias_drift_risk(self) -> bool:
        """True when the returned model string differs from what was requested.

        This is the observable signature of an alias resolving to something
        else, and it is the reason both strings are recorded rather than one.
        """
        return self.returned_model_id is not None and (
            self.returned_model_id != self.requested_model_id
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_model_id": self.requested_model_id,
            "returned_model_id": self.returned_model_id,
            "documented_version_semantics": self.documented_version_semantics,
            "provider_backend_version": self.provider_backend_version,
            "system_fingerprint": self.system_fingerprint,
            "request_id": self.request_id,
            "timestamp_utc": self.timestamp_utc,
            "sdk_version": self.sdk_version,
            "api_version": self.api_version,
            "configuration_hash": self.configuration_hash,
            "alias_drift_risk": self.alias_drift_risk,
        }


@dataclass(slots=True)
class ReproducibilityAudit:
    """Result of the preregistered operational reproducibility audit.

    ``inputs_with_disagreement`` counts audited inputs for which the canonical
    receiver outcomes were not unanimous across repeats. The (D) rule is strict:
    one disagreeing input anywhere is enough to classify (S). There is no
    majority vote, and there is no "mostly deterministic".
    """

    configuration: ReceiverConfiguration
    n_inputs: int = 0
    n_repeats: int = 0
    inputs_with_disagreement: int = 0
    byte_identical_repeat_rate: float | None = None
    completed: bool = False
    notes: str = ""

    def regime(self) -> DecoderRegime:
        if not self.completed:
            return DecoderRegime.NOT_AUDITED
        if self.n_inputs < AUDIT_REQUIRED_INPUTS or self.n_repeats < AUDIT_REQUIRED_REPEATS:
            # An undersized audit cannot confirm (D); it also cannot confirm (S),
            # because absence of an observed disagreement in a small sample is
            # exactly the weak evidence this module exists to refuse.
            return DecoderRegime.NOT_AUDITED
        if self.inputs_with_disagreement == 0:
            return DecoderRegime.D_CONFIRMED
        return DecoderRegime.S_CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration.to_dict(),
            "n_inputs": self.n_inputs,
            "n_repeats": self.n_repeats,
            "inputs_with_disagreement": self.inputs_with_disagreement,
            "byte_identical_repeat_rate": self.byte_identical_repeat_rate,
            "completed": self.completed,
            "regime": self.regime().value,
            "notes": self.notes,
        }


def regime_from_documentation(*_args: object, **_kwargs: object) -> DecoderRegime:
    """Deliberately unimplemented.

    It exists so that the prohibition is discoverable in the code rather than
    only in prose: documentation may not assign a regime, in either direction.
    """
    raise RegimeAssignmentError(
        "Provider documentation may not assign a decoder regime. A snapshot "
        "guarantee constrains weights, not sampling; an undocumented seed is "
        "absence of evidence, not evidence of stochasticity. Run the "
        "preregistered operational reproducibility audit."
    )


@dataclass(frozen=True, slots=True)
class ReplicationDecision:
    """Frozen output of the regime-(S) replication rule."""

    sigma2_decode: float
    sigma2_document: float
    ratio: float
    m_star: int
    criterion_met: bool
    hierarchical_bootstrap_required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "sigma2_decode": self.sigma2_decode,
            "sigma2_document": self.sigma2_document,
            "ratio": self.ratio,
            "m_star": self.m_star,
            "criterion_met": self.criterion_met,
            "hierarchical_bootstrap_required": self.hierarchical_bootstrap_required,
        }


def select_replication(sigma2_decode: float, sigma2_document: float) -> ReplicationDecision:
    """Choose the number of receiver generations per query under regime (S).

    Frozen rule, decided before any calibration data exists::

        m* = min{ m in {1,2,3,5} : sigma2_decode / m <= 0.10 * sigma2_document }

    and if no candidate satisfies it, ``m* = 5`` and the decode replicate is
    retained explicitly as a hierarchical bootstrap level.

    This changes precision, not the estimand. Under (S) a single unbiased draw
    per availability already identifies the population quantities; replication
    buys finite-sample precision and a variance estimate, and nothing else.
    """
    if sigma2_decode < 0.0 or sigma2_document < 0.0:
        raise ValueError("variances must be non-negative")
    if sigma2_document == 0.0:
        # Degenerate: no between-document variation to compare against. Take the
        # conservative branch rather than dividing by zero.
        return ReplicationDecision(
            sigma2_decode=sigma2_decode,
            sigma2_document=sigma2_document,
            ratio=float("inf") if sigma2_decode > 0.0 else 0.0,
            m_star=REPLICATION_GRID[-1] if sigma2_decode > 0.0 else REPLICATION_GRID[0],
            criterion_met=sigma2_decode == 0.0,
            hierarchical_bootstrap_required=sigma2_decode > 0.0,
        )

    threshold = DECODE_VARIANCE_TARGET_RATIO * sigma2_document
    for m in REPLICATION_GRID:
        if sigma2_decode / m <= threshold:
            return ReplicationDecision(
                sigma2_decode=sigma2_decode,
                sigma2_document=sigma2_document,
                ratio=sigma2_decode / sigma2_document,
                m_star=m,
                criterion_met=True,
                hierarchical_bootstrap_required=False,
            )
    return ReplicationDecision(
        sigma2_decode=sigma2_decode,
        sigma2_document=sigma2_document,
        ratio=sigma2_decode / sigma2_document,
        m_star=REPLICATION_GRID[-1],
        criterion_met=False,
        hierarchical_bootstrap_required=True,
    )


@dataclass(slots=True)
class RegimeLedger:
    """Per-configuration regime states. Starts empty; every lookup is NOT_AUDITED."""

    audits: dict[str, ReproducibilityAudit] = field(default_factory=dict)

    @staticmethod
    def key(configuration: ReceiverConfiguration) -> str:
        return "|".join(
            (configuration.provider, configuration.model_id, configuration.configuration_hash)
        )

    def regime_for(self, configuration: ReceiverConfiguration) -> DecoderRegime:
        audit = self.audits.get(self.key(configuration))
        return audit.regime() if audit is not None else DecoderRegime.NOT_AUDITED

    def record(self, audit: ReproducibilityAudit) -> None:
        self.audits[self.key(audit.configuration)] = audit

    def atom_level_probability_claims_permitted(
        self, configuration: ReceiverConfiguration
    ) -> tuple[bool, str]:
        """Whether atom-level statements such as ``Pr[Delta^av_iz < 0]`` may be primary.

        A single stochastic draw cannot support an atom-level probability
        statement. Such claims require ``D_CONFIRMED`` or a predeclared
        repeated-measure design carrying its own uncertainty.
        """
        regime = self.regime_for(configuration)
        if regime is DecoderRegime.D_CONFIRMED:
            return True, "D_CONFIRMED"
        if regime is DecoderRegime.NOT_AUDITED:
            return False, "regime not audited: no atom-level probability claim may be primary"
        return False, (
            "S_CONFIRMED: atom-level probability claims require a predeclared "
            "repeated-measure design with its own uncertainty, not a single draw"
        )
