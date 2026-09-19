# Contributing

Thanks for improving Prediction Liquidity Kit. Keep contributions narrow, reproducible, and explicit about what is observed, estimated, or synthetic.

## Local verification

Use Python 3.11+ and run the repository checks from a clean checkout:

```bash
PYTHONPATH=src python -m prediction_liquidity_kit.cli --version
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
```

Do not add credentials, live venue account access, order placement, capital mutation, or sponsor-fund mutation.

## Venue-rule contributions

A venue rule must be tied to a named program/version and an effective time window. Include source provenance, a pinned source snapshot or hash when the implementation supports it, and deterministic fixtures for representative inputs and boundaries.

Do not model a mutable "latest" formula without a version. Missing or unsupported inputs must fail explicitly rather than becoming favorable zero values. Arithmetic that changes economics should use explicit decimal semantics.

The executable venue-rule interface is being implemented under the rule-registry work before it is documented as stable here. Until that interface is present on `main`, do not invent a parallel rule API in documentation or examples.

## Economics and examples

Never label theoretical or expected reward as realized profit. Keep reward, spread capture, fills, fees, adverse selection, inventory/risk penalties, and capital cost separable where they are modeled.

Examples must say whether their inputs are synthetic or historical. Historical examples must identify the rule version and data window they bind.

## Change shape

Prefer one bounded outcome per pull request with focused tests or fixtures. Public release claims must be tied to the exact source SHA that received the required independent verification receipts.
