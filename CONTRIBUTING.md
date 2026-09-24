# Contributing

Thanks for improving Prediction Liquidity Kit. Keep contributions narrow, reproducible, and explicit about what is observed, estimated, or synthetic.

## Local verification

Use Python 3.11+ and run the repository checks from a clean checkout:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python examples/public_examples.py
python -m unittest discover -s tests -v
git diff --check
```

Do not add credentials, live venue account access, order placement, capital mutation, or sponsor-fund mutation.

## Adding a venue rule

Venue rules are source-reviewed, versioned definitions rather than runtime plugins. A bounded contribution should:

1. add or reuse one deterministic evaluator in `src/prediction_liquidity_kit/rules.py` and register its family in `_CALCULATORS`;
2. add a `RuleDefinition` to `BUILTIN_RULES` with venue, named program, immutable version, effective interval, source URL, pinned source snapshot path/SHA-256, and notes;
3. add the pinned provenance snapshot under `docs/rule-snapshots/`;
4. add deterministic arithmetic, decimal/rounding, effective-window, and unsupported-input tests in `tests/test_rules.py`;
5. add CLI coverage when the rule changes the public `rules list|inspect|evaluate` surface.

Do not add a mutable "latest" formula. Missing or unsupported inputs must fail explicitly rather than becoming favorable zero values. Arithmetic that changes economics should use explicit decimal semantics.

## Economics and examples

Never label theoretical or expected reward as realized profit. Keep reward, spread capture, fills, fees, adverse selection, inventory/risk penalties, and capital cost separable where they are modeled.

Examples must say whether inputs are synthetic, estimated, or observed. Historical examples must identify the rule version and data window they bind. Missing historical depth, fills, fees, or adverse-selection evidence stays a gap rather than being inferred.

## Change shape

Prefer one bounded outcome per pull request with focused tests or fixtures. Public release claims must be tied to the exact source SHA that received the required independent verification receipts.
