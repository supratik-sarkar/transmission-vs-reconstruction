"""Per-class slot schemas.

The receiver answers into a fixed slot so that recovery is decided by
normalised exact match rather than by a model judge. Slots also fix the
response space, which is what makes the per-class chance level 1/K_c
meaningful.

A probe must reveal enough identity/context to ask a well-defined question
while withholding the focal value. Prompts such as "Numeric = ?" are
meaningless and are explicitly forbidden: they measure prompt ambiguity, not
reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import AtomRole


@dataclass(frozen=True, slots=True)
class SlotSchema:
    role: AtomRole
    question_template: str
    answer_format: str
    constrained: bool
    k_nominal: int | None

    def render(self, **context: str) -> str:
        missing = [
            token
            for token in ("subject", "attribute")
            if "{" + token + "}" in self.question_template and token not in context
        ]
        if missing:
            raise ValueError(
                f"slot for role {self.role.value} requires context {missing}; a probe "
                "must be well-defined, not a bare role name"
            )
        return self.question_template.format(**context)


SLOT_SCHEMAS: dict[AtomRole, SlotSchema] = {
    AtomRole.ENTITY: SlotSchema(
        AtomRole.ENTITY,
        "Which company or organisation is described as {attribute}? "
        "Answer with the organisation name only.",
        "organisation-name",
        False,
        None,
    ),
    AtomRole.SCOPE: SlotSchema(
        AtomRole.SCOPE,
        "For {subject}, which business segment or geography does the statement "
        "about {attribute} apply to? Answer with the segment or geography label only.",
        "segment-label",
        True,
        None,
    ),
    AtomRole.PERIOD: SlotSchema(
        AtomRole.PERIOD,
        "For {subject}, which reporting period does the statement about "
        "{attribute} refer to? Answer as FYYYYY or FYYYYYQn.",
        "FYYYYY | FYYYYYQn",
        True,
        None,
    ),
    AtomRole.NUMERIC: SlotSchema(
        AtomRole.NUMERIC,
        "For {subject}, what is the reported value of {attribute}? "
        "Answer with the number and its unit only.",
        "number+unit",
        False,
        None,
    ),
    AtomRole.PROVENANCE: SlotSchema(
        AtomRole.PROVENANCE,
        "For {subject}, which note, item or exhibit is cited for {attribute}? "
        "Answer with the reference only.",
        "Note N | Item N | Exhibit N",
        True,
        None,
    ),
}


def k_effective(_role: AtomRole, support_size: int, *, natural_excluded: bool = True) -> int:
    """Chance reference for the randomised arm.

    The natural value is excluded from its own redraw support -- otherwise the
    randomised twin could coincide with the original -- so the operative
    denominator is K_eff = |support| - 1 when the natural value is a member of
    the support. Reporting 1/|support| would understate chance.
    """
    if support_size <= 1:
        raise ValueError("support must contain at least two values")
    return support_size - 1 if natural_excluded else support_size
