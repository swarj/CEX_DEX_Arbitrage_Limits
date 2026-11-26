# Limits to Arbitrage Between a DEX and a CEX

A small, reproducible empirical project that asks how large and how persistent price gaps are between a decentralized exchange (Uniswap v3, ETH/USDC) and a centralized exchange (Binance, ETH/USDT), and how much of that gap is explained by trading costs, especially Ethereum gas.

The design is anchored to **Makarov and Schoar (2020), "Trading and arbitrage in cryptocurrency markets," *Journal of Financial Economics* 135(2), 293-319.**

> **Status of the data.** The repository ships with a synthetic data generator so the pipeline runs immediately with no downloads or API keys. Synthetic output is for testing only and is **not** an empirical finding. To produce real results, drop in the two raw files described under [Data](#data) and run in `--mode real`.

---

## 1. Purpose and motivation

Makarov and Schoar document large, recurring price deviations for the same cryptocurrency across centralized exchanges, which are larger across countries than within them and which they link to frictions in moving capital. Their setting is centralized venues. This project asks whether the same logic of limits to arbitrage applies when one venue is an on-chain automated market maker, where the friction is different: each arbitrage trade pays a **pool fee and a gas fee**, and the pool price only updates when someone trades against it.

Questions:

1. **Size.** How large is the DEX-CEX deviation, in basis points?
2. **Net of costs.** How often does the gap exceed the round-trip cost of closing it (pool fee + CEX fee + gas)? Gross gaps overstate the opportunity.
3. **Persistence.** How fast do deviations mean-revert, and how long do profitable runs last?
4. **Determinants.** How do gas costs, pool liquidity and volatility relate to the size of the gap?

Hypothesis (from the limits-to-arbitrage logic): when gas is high, the no-arbitrage band widens, so gaps should be larger and more persistent.

## 2. What I take from the paper, and what is different here

Please verify the paper's details against the published article before citing; this is a summary of the design logic, not a quotation of its results.

| | Makarov and Schoar | This project |
|---|---|---|
| Venues compared | Centralized exchanges across countries | One CEX vs. one on-chain pool |
| Main friction | Capital controls, slow capital movement | Pool fee, gas, block-time discreteness |
| Deviation measure | Percentage price gap between venues | Same, in basis points |
| Scope | Many coins, long sample | One pair, short sample (intentionally small) |

This is a stylized extension in the spirit of the paper, not a replication of its tables.

## 3. Repository structure

```
.
├── README.md
├── requirements.txt
├── run_all.py              # one command reproduces every table and figure
├── data/raw/               # place real input files here
├── outputs/                # tables and figures are written here
├── src/
│   ├── config.py           # all assumptions (trade size, fees, gas units, cleaning rules)
│   ├── load_data.py        # Binance kline loader, DEX export loader
│   ├── clean.py            # venue alignment and logged cleaning rules
│   ├── analysis.py         # deviations, costs, AR(1) half-life, Newey-West regression, run lengths
│   ├── synthetic.py        # synthetic data generator (testing only)
│   └── plots.py            # figures
└── tests/
    └── test_analysis.py    # unit tests
```

Data flow: `load_data` -> `clean.align_venues` -> `analysis.build_analysis_frame` -> estimators -> `outputs/`.

## 4. How to run

```bash
pip install -r requirements.txt
pytest                                   # unit tests
python run_all.py --mode synthetic       # demo on synthetic data
python run_all.py --mode real \
    --cex data/raw/ETHUSDT-1m.csv \
    --dex data/raw/uniswap_eth_usdc_005.csv
```

Outputs: `outputs/summary.csv`, `outputs/determinants_regression.csv`, and three figures (deviation time series with cost band, deviation histogram, opportunity-duration histogram).

## 5. Data

**CEX.** Binance spot 1-minute klines for ETHUSDT from <https://data.binance.vision>. Concatenate the daily files into one CSV (headerless, standard 12 kline columns). The loader handles millisecond and microsecond timestamps.

**DEX.** A swap-level export for the Uniswap v3 ETH/USDC 0.05% pool from Dune or The Graph, as a CSV with columns:

| column | meaning |
|---|---|
| `timestamp` | swap or block time, UTC (ISO 8601 or unix seconds) |
| `price` | USDC per ETH implied by the pool after the swap |
| `liquidity_usd` | pool TVL (or in-range liquidity), USD |
| `gas_gwei` | gas price of the containing block, in gwei |

Swap rows are collapsed to the last observation in each minute. A one- to two-week window is plenty. Commit the small extract so reviewers can reproduce results without keys.

Note on quote currencies: Binance ETH/USDT versus a Uniswap ETH/USDC pool embeds a USDT/USDC basis. This is typically a few bps or less in calm periods but can matter in stress. Using ETH/USDC on a venue that lists it avoids the issue (see Limitations).

## 6. Implementation and design decisions

**Deviation.** `(DEX price / CEX price - 1) * 10,000` bps. Positive means the DEX is more expensive.

**Costs (the no-arbitrage band).** For a hypothetical trade of `trade_size_usd` (default $10,000):
`cost = pool fee + CEX fee + gas`, where gas in bps is
`gas_gwei * 1e-9 * gas_units * ETH/USD / trade_size * 10,000`.
Defaults in `src/config.py`: 5 bps pool fee, 1 bps CEX fee, 150,000 gas units. These are assumptions, and results should be reported under a few alternatives (e.g., $1k, $10k, $100k trades), since the gas component scales inversely with size.

**Net deviation.** `max(|deviation| - cost, 0)`: a stylized per-trade profit. It ignores price impact, slippage, inventory and execution risk, so it is an upper bound on realizable profit.

**Timestamp alignment and look-ahead.** DEX data is forward-filled onto the CEX 1-minute grid, so each minute uses only DEX information available at or before it. DEX prices older than two minutes are treated as missing, because a stale pool price would be mistaken for a price gap.

**Cleaning rules (all counted and printed).** Duplicate timestamps (keep last); non-overlapping periods; stale or missing DEX quotes; non-positive prices or liquidity; and |deviation| above 500 bps, treated as a data error. The cleaning log is printed on every run so these decisions can be reported.

**Mean reversion.** AR(1) on the deviation, `dev_t = a + phi * dev_{t-1} + e_t`, with half-life `ln(0.5) / ln(phi)` minutes.

**Determinants regression.** `|deviation|` on gas cost (bps), log pool liquidity and trailing 60-minute realized volatility, with Newey-West standard errors (60 lags) to account for strong serial dependence in minute-level data. The Newey-West estimator is implemented directly in numpy so it is auditable, and a unit test cross-checks it against `statsmodels` when that package is installed.

**Persistence of opportunities.** Run lengths of consecutive profitable minutes. The series is reindexed to a complete minute grid first, so minutes removed by cleaning are not bridged into one artificial run (this has a dedicated test).

**Tests.** Deviation sign and scale, gas-cost arithmetic, recovery of a known AR(1) coefficient, run-length logic, no-look-ahead alignment, and the Newey-West cross-check.

## 7. Limitations

- **Descriptive, not causal.** Gas, liquidity and volatility are jointly determined with arbitrage activity. The regression reports associations only.
- **Short sample, one pair.** Results may not generalize across assets, fee tiers, or market regimes.
- **Block-time discreteness.** The pool price changes only when a swap occurs. Minute-level alignment cannot resolve within-block or within-second dynamics.
- **Stylized costs.** No price impact, failed transactions, priority-fee auctions, MEV competition, or capital costs.
- **Quote-currency mismatch.** USDT vs. USDC basis (see Data).
- **Liquidity measure.** TVL is a rough proxy for depth; in-range liquidity in v3 is better but harder to obtain.
- **Synthetic mode** builds in the mechanism it is meant to illustrate and must not be read as evidence.

## 8. Possible extensions

- Repeat across fee tiers (0.05% vs. 0.3%) and trade sizes; plot the share of profitable minutes against trade size.
- Add a second CEX (e.g., Coinbase) to compare DEX-CEX gaps with CEX-CEX gaps, closer to the paper's cross-venue design.
- Event window around a volatility or gas spike, with clearly descriptive framing.
- Replace the minute grid with block-level timestamps.

## 9. Reference

Makarov, I., and Schoar, A. (2020). Trading and arbitrage in cryptocurrency markets. *Journal of Financial Economics*, 135(2), 293-319.
