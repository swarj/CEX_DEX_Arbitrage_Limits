"""Reproduce every table and figure with one command.

    python run_all.py --mode synthetic
    python run_all.py --mode real --cex data/raw/ETHUSDT-1m.csv --dex data/raw/uniswap_eth_usdc_005.csv
"""
from __future__ import annotations

import argparse
import os

from src.analysis import (ar1_half_life, build_analysis_frame, determinants_regression,
                          opportunity_durations, summary_table)
from src.clean import align_venues
from src.config import Config
from src.load_data import load_binance_klines, load_dex_prices
from src.plots import (plot_deviation_histogram, plot_deviation_timeseries,
                       plot_duration_distribution)
from src.synthetic import make_synthetic


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["synthetic", "real"], default="synthetic")
    p.add_argument("--cex", help="Binance 1-minute kline CSV (real mode)")
    p.add_argument("--dex", help="DEX export CSV (real mode)")
    p.add_argument("--out", default="outputs")
    args = p.parse_args()

    cfg = Config()
    os.makedirs(args.out, exist_ok=True)

    # 1. Load -------------------------------------------------------------------------
    if args.mode == "synthetic":
        print("*** SYNTHETIC DATA: pipeline demo only, results are not empirical findings ***")
        cex, dex = make_synthetic(cfg=cfg)
    else:
        if not (args.cex and args.dex):
            p.error("--cex and --dex are required in real mode")
        cex, dex = load_binance_klines(args.cex), load_dex_prices(args.dex)

    # 2. Align and clean --------------------------------------------------------------
    aligned, clean_log = align_venues(cex, dex, cfg)
    print("\nCleaning log:", clean_log)

    # 3. Analyze ----------------------------------------------------------------------
    df = build_analysis_frame(aligned, cfg)
    durations = opportunity_durations(df["profitable"])
    summary = summary_table(df, durations)
    mr = ar1_half_life(df["dev_bps"], cfg.hac_lags)
    reg = determinants_regression(df, cfg)

    print("\nSummary statistics:\n", summary.round(3).to_string())
    print(f"\nMean reversion (AR(1) on deviation): phi={mr['phi']:.4f} "
          f"(NW se {mr['phi_se']:.4f}), half-life={mr['half_life_min']:.2f} min")
    print(f"\n|deviation| regression (Newey-West, {cfg.hac_lags} lags; "
          f"N={reg.attrs['n']}, R2={reg.attrs['r2']:.3f}):\n", reg.round(4).to_string())

    # 4. Save -------------------------------------------------------------------------
    summary.to_csv(f"{args.out}/summary.csv", header=["value"])
    reg.to_csv(f"{args.out}/determinants_regression.csv")
    plot_deviation_timeseries(df, f"{args.out}/fig_deviation_timeseries.png")
    plot_deviation_histogram(df, f"{args.out}/fig_deviation_histogram.png")
    plot_duration_distribution(durations, f"{args.out}/fig_opportunity_durations.png")
    print(f"\nSaved tables and figures to {args.out}/")


if __name__ == "__main__":
    main()
