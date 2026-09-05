# GENERATED FROM CODE by scripts/export_protocol_artifacts.py.
Do not edit by hand: a hand-edited specification can drift away from the
implementation it claims to describe.

# Numeric randomisation support

Only the `pct` subtype is randomised.

Currency magnitudes are not exchangeable across issuers: a uniformly redrawn
currency value would not be a plausible counterfactual, and implausibility would
change salience rather than prior access, which is the manipulation the design
needs to isolate.

Recognised subtypes: `pct`, `currency`, `count`, `ratio`

For `pct`, the redraw support is the plausible range at two decimals, stated per
document, with the natural value excluded. `K_eff` is therefore recorded per
document rather than globally. **PROPOSED** pending approval of the range.
