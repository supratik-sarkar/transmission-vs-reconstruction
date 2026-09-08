"""Provider capability registry.

Every field defaults to UNKNOWN. Capabilities are resolved from official
provider documentation during the model-pinning phase, not guessed here -- a
wrong `seed_support` would silently change what decoder regime we believe we are
in.

Resolution pass: 2026-09-05, corrected 2026-09-06, from official documentation
only. No inference call, no model-list call and no credential access was
involved.

The distinction between NO and UNKNOWN is load-bearing:

* ``NO``      the documentation affirmatively denies the capability, either by
              stating an error or by publishing a complete request schema in
              which the parameter does not appear.
* ``UNKNOWN`` the documentation is silent. Silence is not denial, and it is not
              permission either -- it means the capability cannot be relied on
              until it is checked against the live API on a networked host.

**Version pinning is not deterministic decoding.** The two are recorded
separately and neither implies the other. A provider can document a model
string as a locked snapshot while saying nothing about whether repeated calls
produce the same output, and that is in fact the common case. Which decoder
regime a receiver is in is decided by
:mod:`handoff_fidelity.providers.regime`, from an audit, never from this file --
see :data:`REGIME_D_STATUS`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from .regime import DecoderRegime

#: Date of the documentation pass that produced the values below.
CAPABILITY_RESOLUTION_DATE = "2026-09-06"

#: Decoder-regime state for every provider-backed receiver in this project.
#:
#: This was previously a boolean asserting that regime (D) was categorically
#: unattainable. That was wrong twice over: documentation cannot establish
#: operational determinism, and it cannot rule it out either. The state is
#: ternary and starts at NOT_AUDITED. Only the preregistered operational
#: reproducibility audit may move it.
REGIME_D_STATUS: DecoderRegime = DecoderRegime.NOT_AUDITED


class Support(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class VersionClass(StrEnum):
    """How stable the thing behind a callable model string is *documented* to be.

    This taxonomy is about identity, not about sampling. Nothing here licenses a
    decoder-regime conclusion.
    """

    #: The vendor states that the dateless ID *is* the snapshot and that weights
    #: under an existing ID are never updated.
    IMMUTABLE_DATELESS_SNAPSHOT = "IMMUTABLE_DATELESS_SNAPSHOT"
    #: A YYYYMMDD-suffixed ID that never changes.
    IMMUTABLE_DATED_SNAPSHOT = "IMMUTABLE_DATED_SNAPSHOT"
    #: The canonical model ID is itself listed under the vendor's "Snapshots"
    #: section, where snapshots are documented to lock a specific model version.
    #: There is no separate dated string, and none is needed: the canonical ID is
    #: the pin the vendor offers.
    CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT = "CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT"
    #: The callable string is stable while the backend version behind it rotates;
    #: the backend version is announced but is not callable.
    MOVING_ALIAS_WITH_RECORDED_BACKEND_VERSION = "MOVING_ALIAS_WITH_RECORDED_BACKEND_VERSION"
    #: Documented as "usually" unchanging, with no commitment that weights are frozen.
    STABLE_LABEL_NO_WEIGHT_GUARANTEE = "STABLE_LABEL_NO_WEIGHT_GUARANTEE"
    #: Preview channel, deprecation on as little as two weeks' notice.
    PREVIEW_SHORT_NOTICE = "PREVIEW_SHORT_NOTICE"
    DETERMINISTIC_STUB = "DETERMINISTIC_STUB"
    UNRESOLVED = "UNRESOLVED"

    @property
    def admissible_as_primary_confirmatory(self) -> bool:
        """Whether this identity class may back the PRIMARY confirmatory role.

        A moving alias is inadmissible as the primary confirmatory relay or
        receiver unless an explicit pre-run amendment explains why its run-level
        backend identity is sufficient. It may still take a clearly labelled
        robustness role if that is preregistered before outcomes.
        """
        return self in {
            VersionClass.IMMUTABLE_DATELESS_SNAPSHOT,
            VersionClass.IMMUTABLE_DATED_SNAPSHOT,
            VersionClass.CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT,
            VersionClass.DETERMINISTIC_STUB,
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    text_generation: Support = Support.UNKNOWN
    structured_output: Support = Support.UNKNOWN
    temperature_support: Support = Support.UNKNOWN
    seed_support: Support = Support.UNKNOWN
    streaming: Support = Support.UNKNOWN
    usage_reporting: Support = Support.UNKNOWN
    request_id: Support = Support.UNKNOWN
    pinned_model_snapshots: Support = Support.UNKNOWN
    max_context_tokens: int | None = None
    version_class: VersionClass = VersionClass.UNRESOLVED
    documentation_url: str = ""
    caveat: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Support | VersionClass):
                d[k] = v.value
        return d

    @property
    def unresolved_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in self.to_dict().items() if value == Support.UNKNOWN.value
        )


#: Resolved from official documentation on 2026-09-05. Fields that the
#: documentation does not address stay UNKNOWN; populating them from memory
#: would be a guess presented as a fact.
REGISTRY: dict[str, ProviderCapabilities] = {
    "openai": ProviderCapabilities(
        provider="openai",
        text_generation=Support.YES,
        structured_output=Support.YES,
        # `temperature` and `seed` do not appear in the supported-features list
        # for the current reasoning models, and a search of the reasoning guide
        # for temperature/top_p/seed/determinism/reproducibility returned
        # nothing. Absence from a feature list is weaker than a documented
        # rejection, so this stays UNKNOWN rather than NO.
        temperature_support=Support.UNKNOWN,
        seed_support=Support.UNKNOWN,
        streaming=Support.YES,
        usage_reporting=Support.UNKNOWN,
        request_id=Support.UNKNOWN,
        # CORRECTED 2026-09-06. The previous value said NO, on the reasoning
        # that no dated snapshot exists. That misread the documentation: each
        # model page carries a Snapshots section stating "Snapshots let you lock
        # in a specific version of the model so that performance and behavior
        # remain consistent", and lists the canonical model ID itself. The
        # canonical ID *is* the offered pin. A dated string is one way to
        # express a snapshot, not the definition of one.
        pinned_model_snapshots=Support.YES,
        max_context_tokens=1_050_000,
        version_class=VersionClass.CANONICAL_ID_DOCUMENTED_AS_SNAPSHOT,
        documentation_url="https://developers.openai.com/api/docs/models",
        caveat=(
            "Version pinning is not deterministic decoding: the Snapshots wording "
            "constrains the model version, and says nothing about repeatability of "
            "a given request. Operational repeatability is unverified until the "
            "audit. One family also publishes a convenience alias alongside the "
            "canonical ID; the alias is not the snapshot and must not be the "
            "primary confirmatory string. Above 272K input tokens, input is billed "
            "at 2x and output at 1.5x. Reasoning effort is a billed output cost "
            "that the handoff budget B does not control. Promotional pricing on one "
            "model is dated and is time-stamped metadata, not a constant."
        ),
    ),
    "deepseek": ProviderCapabilities(
        provider="deepseek",
        text_generation=Support.YES,
        structured_output=Support.YES,  # response_format json_object
        temperature_support=Support.YES,  # <= 2, default 1
        # The Chat Completions API reference publishes the complete request body
        # and contains no seed parameter. This is a denial, not silence.
        seed_support=Support.NO,
        streaming=Support.YES,
        usage_reporting=Support.YES,
        request_id=Support.UNKNOWN,
        pinned_model_snapshots=Support.NO,
        max_context_tokens=None,  # pricing page canonicalises to the docs index
        version_class=VersionClass.MOVING_ALIAS_WITH_RECORDED_BACKEND_VERSION,
        documentation_url="https://api-docs.deepseek.com/api/create-chat-completion",
        caveat=(
            "deepseek-v4-flash and deepseek-v4-pro are moving aliases; the backend "
            "version (V4-Flash-0731, V4-Pro-0813) is announced but not callable, so "
            "only the per-response system_fingerprint carries backend identity. "
            "reasoning_effort='medium' and 'xhigh' are silently mapped to 'high', and "
            "frequency_penalty/presence_penalty are accepted and ignored -- the ledger "
            "must record what executed, not what was requested."
        ),
    ),
    "anthropic": ProviderCapabilities(
        provider="anthropic",
        text_generation=Support.YES,
        structured_output=Support.YES,
        # CORRECTED 2026-09-06. Previously NO, generalised from one model's page
        # to the whole vendor. Setting temperature/top_p/top_k to a non-default
        # value is documented to return 400 on the current Sonnet-tier model,
        # and that page says the constraint was introduced on the Opus 4.7
        # generation -- but the later models' own pages were not read, and a
        # lineage argument is not documentation. Provider-level state is
        # therefore UNKNOWN and must be resolved per model before pinning.
        # Exact model strings live in the private resolution matrix, not here.
        temperature_support=Support.UNKNOWN,
        seed_support=Support.UNKNOWN,  # no seed parameter is documented
        streaming=Support.YES,
        usage_reporting=Support.YES,
        request_id=Support.UNKNOWN,
        # "the dateless ID ... maps to a single, fixed model snapshot"
        pinned_model_snapshots=Support.YES,
        max_context_tokens=1_000_000,
        version_class=VersionClass.IMMUTABLE_DATELESS_SNAPSHOT,
        # The public repository forbids assistant-identifying strings (see
        # handoff_fidelity.privacy.scan), and this vendor's documentation host
        # and model IDs contain one. The URL and the exact model strings are
        # therefore recorded in the private workspace, in
        # models/FRONTIER_MODEL_CANDIDATE_MATRIX.{md,csv,json}. This is a
        # boundary decision, not an omission.
        documentation_url="PRIVATE_MATRIX: models/FRONTIER_MODEL_CANDIDATE_MATRIX.md#anthropic",
        caveat=(
            "Weights are documented as fixed per model ID, but serving "
            "infrastructure -- router, safety classifiers, SAMPLING LOGIC -- can "
            "change under a fixed ID and may produce observable behaviour "
            "differences. That is precisely why a fixed-weights guarantee cannot "
            "be read as a determinism guarantee. Adaptive thinking is on by "
            "default and counts against max_tokens. The current Sonnet-tier model "
            "uses a new tokenizer producing ~30% more tokens for the same text, so "
            "token budgets are not portable across generations."
        ),
    ),
    "gemini": ProviderCapabilities(
        provider="gemini",
        text_generation=Support.YES,
        structured_output=Support.YES,
        temperature_support=Support.YES,  # generationConfig temperature/topP/topK
        # The only documented seed is in the OpenAI-compatibility extra_body table
        # and applies to Video generation. No text seed is documented.
        seed_support=Support.UNKNOWN,
        streaming=Support.YES,
        usage_reporting=Support.YES,
        request_id=Support.UNKNOWN,
        # "Stable models usually don't change" is not a freeze guarantee.
        pinned_model_snapshots=Support.UNKNOWN,
        max_context_tokens=1_048_576,
        version_class=VersionClass.STABLE_LABEL_NO_WEIGHT_GUARANTEE,
        documentation_url="https://ai.google.dev/gemini-api/docs/models",
        caveat=(
            "'Stable models usually don't change' is not an immutability "
            "guarantee, and must not be upgraded into one; stable is nonetheless "
            "preferable to preview. Preview models carry as little as two weeks' "
            "deprecation notice and are INELIGIBLE for primary confirmatory use "
            "under the current design; a stable label may take that role. Output "
            "is priced INCLUDING thinking tokens, and reasoning cannot be disabled "
            "on the 3-series, so spend is not bounded by the handoff budget B."
        ),
    ),
    "mock": ProviderCapabilities(
        provider="mock",
        text_generation=Support.YES,
        structured_output=Support.YES,
        temperature_support=Support.NO,
        seed_support=Support.YES,
        streaming=Support.NO,
        usage_reporting=Support.YES,
        request_id=Support.YES,
        pinned_model_snapshots=Support.YES,
        max_context_tokens=1_000_000,
        version_class=VersionClass.DETERMINISTIC_STUB,
        resolved=True,
        documentation_url="in-repo deterministic stub",
        caveat="Mock output has zero evidentiary value and never enters a result.",
    ),
}


def capabilities_for(provider: str) -> ProviderCapabilities:
    return REGISTRY.get(provider.lower(), ProviderCapabilities(provider=provider))
