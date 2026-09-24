# Prediction Liquidity Kit

Public, deterministic tooling for prediction-market liquidity incentives.

The project focuses on three questions:

1. How is a venue's liquidity/reward program defined for a specific rule version?
2. What is the **estimated net** economics of allocating market-making capital after explicit costs/risks?
3. How should a sponsor test incentive budgets against liquidity targets in simulation?

It is **not** a live market-making bot and does not place orders or spend sponsor funds.

## Quickstart

Python 3.11+ is supported. From a clean checkout:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
prediction-liquidity-kit --version
python examples/public_examples.py
python -m unittest discover -s tests -v
```

The public example runs a versioned reward calculation, constrained MM capital allocation, sponsor-budget simulation, and deterministic replay hash. Its economics are synthetic/estimated and the output explicitly says so; it is not realized PnL or live-capital evidence.

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
prediction-liquidity-kit rules list
prediction-liquidity-kit rules inspect kalshi-liquidity-help-2026-09-19
prediction-liquidity-kit rules evaluate kalshi-volume-help-2026-08-05 \
  --input-json '{"contract_price":"0.50","user_eligible_contracts":"1000","total_eligible_contracts":"1000","reward_pool":"1000"}'
```

The pinned summaries under `docs/rule-snapshots/` are provenance fixtures, not substitutes for venue terms. Unsupported exceptions or unknown/missing inputs fail explicitly rather than being imputed.

## Historical evidence boundary

The checked-in public Kalshi trade/candlestick fixture is observed market evidence, but it does not establish historical order-book depth, queue priority, account-specific fills, incentive enrollment/payout, fees, or exact post-fill adverse selection. The replay manifest keeps those gaps explicit and forbids a profitability claim.

## Verify

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m prediction_liquidity_kit.cli --version
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/public_examples.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
```

## Project docs

- [Architecture](docs/ARCHITECTURE.md)
- [Economic boundaries](docs/ECONOMIC-BOUNDARIES.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog and version policy](CHANGELOG.md)
- [Security](SECURITY.md)

Apache-2.0 licensed.
