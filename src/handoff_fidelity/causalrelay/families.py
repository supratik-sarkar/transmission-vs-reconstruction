"""Predictor families for the CausalRelay surplus model.

This module exists because two unrelated things were being called a "family",
and the collision was close to letting a provider canary resolve a
pre-registered scientific parameter.

``causalrelay.primary_family`` is the **utility-predictor estimator family**.
Its search space is a set of tabular regressors and its winner is chosen by
grouped cross-validation on DEVELOPMENT documents only. It has nothing to do
with which vendor serves the relay or the receiver. A provider canary measures
latency, cost and decode variability; none of those is evidence about which
regressor predicts atom surplus best, and none of them may touch this leaf.

The relay and receiver identities are separate concepts entirely, and live in
:class:`ModelPin` below and in the two ``must_be_pinned`` pre-registration
leaves ``models.relay_model`` and ``models.receiver_model``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PredictorFamily(StrEnum):
    """The frozen search space for ``causalrelay.primary_family``.

    Frozen now; the winner is selected at DEVELOPMENT and frozen at the
    final-test freeze. No final-test adaptation is permitted.
    """

    HIST_GRADIENT_BOOSTING = "HistGradientBoostingRegressor"
    RIDGE = "Ridge"
    EXTRA_TREES = "ExtraTreesRegressor"


#: The declared resolution stage of ``causalrelay.primary_family``.
PREDICTOR_FAMILY_RESOLUTION_STAGE = "DEVELOPMENT"

#: How the winner is chosen. Frozen; reproduced here so the rule is visible at
#: the point of use rather than only in the YAML.
PREDICTOR_FAMILY_SELECTION = "grouped_cv_by_document_on_development_only"


class PredictorFamilyResolutionError(RuntimeError):
    """Raised when something tries to resolve the predictor family illegitimately."""


class ModelRole(StrEnum):
    """Which side of the handoff a pinned model sits on."""

    RELAY = "relay"
    RECEIVER = "receiver"


@dataclass(frozen=True, slots=True)
class ModelPin:
    """A pinned LLM: vendor plus callable model string, for one role.

    Provider identity is carried here as *metadata attached to the role*, not as
    a new pre-registered leaf. The two scientific leaves remain
    ``models.relay_model`` and ``models.receiver_model``; this type is how the
    code keeps "who serves it" and "which string is called" from being conflated
    with each other, or with the predictor family.
    """

    role: ModelRole
    provider: str
    model_id: str
    version_class: str = "UNRESOLVED"

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role.value,
            "provider": self.provider,
            "model_id": self.model_id,
            "version_class": self.version_class,
        }


def resolve_predictor_family_from_provider_evidence(*_a: object, **_k: object) -> PredictorFamily:
    """Deliberately unimplemented, so the prohibition is executable.

    Provider canary results -- latency, spend, decode variance, fingerprints --
    are not evidence about which regressor predicts atom surplus. Calling this
    is a category error and raises rather than returning a plausible answer.
    """
    raise PredictorFamilyResolutionError(
        "causalrelay.primary_family is the utility-predictor estimator family "
        "(HistGradientBoostingRegressor | Ridge | ExtraTreesRegressor). It is "
        "resolved at DEVELOPMENT by grouped CV on development documents only. It "
        "is NOT an LLM provider family and must never be resolved from provider "
        "canary results, model availability, or pricing."
    )


def assert_not_a_provider_family(name: str) -> None:
    """Guard for config loaders: reject a provider name in the predictor leaf."""
    known_providers = {"openai", "anthropic", "deepseek", "gemini", "google", "mock"}
    if name.strip().lower() in known_providers:
        raise PredictorFamilyResolutionError(
            f"{name!r} is an LLM provider, not a predictor family. "
            "causalrelay.primary_family accepts only "
            f"{[f.value for f in PredictorFamily]}."
        )
