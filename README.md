# Prediction Liquidity Kit

Public, deterministic tooling for prediction-market liquidity incentives.

The project focuses on three questions:

1. How is a venue's liquidity/reward program defined for a specific rule version?
2. What is the **estimated net** economics of allocating market-making capital after explicit costs/risks?
3. How should a sponsor test incentive budgets against liquidity targets in simulation?

It is **not** a live market-making bot and does not place orders or spend sponsor funds.

## Principles

- Reward formulas are versioned and date-effective.
- Historical replay binds the exact rule version.
- Theoretical reward is not called profit.
- Observed, estimated, and synthetic economics are separate.
- Missing risk/cost inputs do not silently become zero.
- Money/rate arithmetic uses explicit decimal semantics where precision matters.
- Optimizers respect hard budgets/caps and expose uncertainty.

## Reward rules

The rule registry currently admits two materially different Kalshi public rule families:

- liquidity incentives: quote-size/distance scoring plus period reward share and snapshot coverage;
- volume incentives: proportional eligible volume with the published per-contract cap.

Each admitted version records an effective interval, source URL, local source-summary snapshot and SHA-256. There is intentionally no mutable `latest` alias.

```bash
PYTHONPATH=src python -m prediction_liquidity_kit.cli rules list
PYTHONPATH=src python -m prediction_liquidity_kit.cli rules inspect kalshi-liquidity-help-2026-09-19
PYTHONPATH=src python -m prediction_liquidity_kit.cli rules evaluate kalshi-volume-help-2026-08-05 \
  --input-json '{"contract_price":"0.50","user_eligible_contracts":"1000","total_eligible_contracts":"1000","reward_pool":"1000"}'
```

The pinned summaries under `docs/rule-snapshots/` are provenance fixtures, not substitutes for venue terms. Unsupported exceptions or unknown/missing inputs fail explicitly rather than being imputed.

## Status

Rule registry/calculator work is tracked in `sangtrx/sang-workspace#739`. MM allocator: `#740`. Sponsor optimizer/controller: `#741/#742`.

## Verify

```bash
PYTHONPATH=src python -m prediction_liquidity_kit.cli --version
PYTHONPATH=src python -m unittest discover -s tests -v
```

Apache-2.0 licensed.
