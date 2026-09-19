# Economic boundaries

Prediction Liquidity Kit is an analysis and simulation library. It does not place orders, access venue accounts, deploy market-making capital, or spend sponsor funds.

## Output classes

Keep these concepts distinct in code, fixtures, examples, and documentation:

- **Theoretical reward**: deterministic output of a selected venue/program rule for stated inputs.
- **Expected realized reward**: an estimate that may differ from theoretical reward because of eligibility, uptime, fills, competition, or other modeled uncertainty.
- **Observed outcome**: a value sourced from historical evidence for a stated time window and provenance.
- **Synthetic outcome**: a constructed fixture or scenario used to test behavior.
- **Estimated spread capture / fills / costs / risk**: modeled components, not realized PnL.

No expected or theoretical value should be described as profit without the relevant realized trading economics.

## Net economics

Where net-return scenarios are modeled, components should remain inspectable rather than collapsed into an unexplained score. Relevant components can include reward, spread capture, fills, fees, adverse selection, inventory/risk penalty, and capital cost.

Unknown required economics are not favorable zeros. A simulator or optimizer should fail closed or produce an explicit no-decision/unknown state when required inputs are missing.

## Historical replay

A historical replay binds both the market-data window and the venue-rule version effective for that period. A newer formula must not leak backward into an older replay.

Historical evidence should identify its provenance and distinguish observed fields from estimates or synthetic substitutions. Incomplete fill or adverse-selection evidence must not be used to imply profitability.

## Sponsor simulation

Sponsor optimization and control are bounded simulations. Budgets, per-market caps, rate-change caps, uncertainty, stale measurements, and degraded/no-decision states should stay visible in outputs.

A simulated incentive level is not authorization to transfer funds or mutate a live venue configuration.

## Release boundary

A clean build, passing tests, or a plausible simulation is not live-capital readiness. Public release verification establishes reproducibility and implementation correctness for the exact verified SHA only.
