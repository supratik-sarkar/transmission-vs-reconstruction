"""Atom taxonomy and the frozen vocabularies the rule-based extractor uses."""

from __future__ import annotations

from ..models import AtomRole

TIER2_ROLES: tuple[str, ...] = ("relation_strength", "certainty", "counterevidence")

#: Segment / geography labels recognised as SCOPE atoms. Frozen: adding a term
#: after a run has started changes the target population.
SCOPE_VOCABULARY: tuple[str, ...] = (
    "North America",
    "South America",
    "Latin America",
    "Europe",
    "Asia Pacific",
    "Asia-Pacific",
    "EMEA",
    "APAC",
    "Americas",
    "United States",
    "Canada",
    "Mexico",
    "China",
    "Japan",
    "India",
    "Germany",
    "France",
    "United Kingdom",
    "Brazil",
    "Australia",
    "Consumer",
    "Commercial",
    "Enterprise",
    "Industrial",
    "Retail",
    "Wholesale",
    "Products",
    "Services",
    "Software",
    "Hardware",
    "Cloud",
    "Subscription",
    "Licensing",
    "Manufacturing",
)

ENTITY_SUFFIXES: tuple[str, ...] = (
    "Inc.",
    "Inc",
    "Corporation",
    "Corp.",
    "Corp",
    "Company",
    "Co.",
    "Holdings",
    "Group",
    "Limited",
    "Ltd.",
    "Ltd",
    "PLC",
    "plc",
    "N.V.",
    "S.A.",
    "AG",
    "GmbH",
    "LLC",
    "L.P.",
    "LP",
)

#: Numeric subtypes. Only ``pct`` participates in the randomised support of
#: Experiment B: currency magnitudes are not exchangeable across issuers, so a
#: uniformly redrawn currency value would not be a plausible counterfactual.
NUMERIC_SUBTYPES: tuple[str, ...] = ("pct", "currency", "count", "ratio")

ROLE_ORDER: tuple[AtomRole, ...] = (
    AtomRole.ENTITY,
    AtomRole.SCOPE,
    AtomRole.PERIOD,
    AtomRole.NUMERIC,
    AtomRole.PROVENANCE,
)
