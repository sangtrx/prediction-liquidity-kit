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

## Status

Bootstrap only. Rule registry work: `sangtrx/sang-workspace#739`. MM allocator: `#740`. Sponsor optimizer/controller: `#741/#742`.

## Verify

```bash
PYTHONPATH=src python -m prediction_liquidity_kit.cli --version
PYTHONPATH=src python -m unittest discover -s tests -v
```

Apache-2.0 licensed.
