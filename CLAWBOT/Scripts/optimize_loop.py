#!/usr/bin/env python3
"""
CLAWBOT Iterative Optimization Loop
=====================================
Runs backtest -> diagnose -> fix -> repeat until targets are met.
Target: Win Rate >= 80%, Return >= 50%

Strategy: Grid search key parameters, then fine-tune.
"""

import sys
import json
import copy
from pathlib import Path

import pandas as pd
import numpy as np

from backtest_engine import Config, ClawbotBacktester, print_stats, diagnose


TARGET_WR = 80.0
TARGET_RETURN = 50.0


def run_backtest(df, cfg, silent=True):
    bt = ClawbotBacktester(cfg)
    stats = bt.run(df, silent=silent)
    return stats


def grid_search(df):
    """Phase 1: Grid search to find parameter region that maximizes WR while keeping 50+ trades."""
    print("=" * 60)
    print("  PHASE 1: GRID SEARCH")
    print("=" * 60)

    results = []

    # Key parameters to search (reduced grid for speed)
    min_scores = [40, 55, 70, 85]
    min_strategies_list = [2, 3]
    adx_thresholds = [22, 28, 35]
    sl_atrs = [2.0, 3.0]
    tp_atrs_mult = [2.0, 3.0]  # as multiple of SL

    total = len(min_scores) * len(min_strategies_list) * len(adx_thresholds) * len(sl_atrs) * len(tp_atrs_mult)
    count = 0

    for ms in min_scores:
        for mst in min_strategies_list:
            for adx in adx_thresholds:
                for sl in sl_atrs:
                    for tp_m in tp_atrs_mult:
                        count += 1
                        cfg = Config()
                        cfg.min_score = ms
                        cfg.min_strategies = mst
                        cfg.adx_threshold = adx
                        cfg.sl_atr = sl
                        cfg.tp_atr = sl * tp_m
                        cfg.trail_distance = sl * 0.5
                        cfg.trail_activation = sl * 0.75
                        cfg.min_risk_reward = tp_m * 0.5
                        cfg.tp1_atr = sl * 0.5
                        cfg.dyn_max_loss_atr = sl * 0.9

                        stats = run_backtest(df, cfg, silent=True)
                        wr = stats['win_rate']
                        ret = stats['return_pct']
                        total_trades = stats['total_trades']
                        pf = stats['profit_factor']

                        # Score: prioritize WR, then return, penalize too few trades
                        trade_penalty = max(0, 30 - total_trades) * 2
                        score = wr * 2 + min(ret, 200) * 0.3 + pf * 5 - trade_penalty

                        results.append({
                            'min_score': ms, 'min_strategies': mst,
                            'adx': adx, 'sl_atr': sl, 'tp_mult': tp_m,
                            'wr': wr, 'ret': ret, 'pf': pf,
                            'trades': total_trades, 'score': score,
                            'cfg': copy.deepcopy(cfg), 'stats': stats
                        })

                        if count % 50 == 0:
                            print(f"  [{count}/{total}] Best so far: WR={max(r['wr'] for r in results):.1f}%")

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\nGrid search complete. {len(results)} configs tested.")
    print("\nTop 10 configurations:")
    print(f"  {'WR':>6} {'Ret':>7} {'PF':>5} {'Trades':>6} {'MinSc':>5} {'MinSt':>5} {'ADX':>5} {'SL':>5} {'TP_m':>5}")
    for r in results[:10]:
        print(f"  {r['wr']:5.1f}% {r['ret']:6.1f}% {r['pf']:5.2f} {r['trades']:6d} {r['min_score']:5d} {r['min_strategies']:5d} {r['adx']:5.0f} {r['sl_atr']:5.1f} {r['tp_mult']:5.1f}")

    return results


def fine_tune(df, base_cfg, base_stats):
    """Phase 2: Fine-tune around the best grid result."""
    print("\n" + "=" * 60)
    print("  PHASE 2: FINE-TUNING")
    print("=" * 60)

    best_cfg = copy.deepcopy(base_cfg)
    best_stats = base_stats
    best_score = base_stats['win_rate'] * 2 + min(base_stats['return_pct'], 200) * 0.3

    # Fine-tune individual parameters
    params_to_tune = [
        ('min_score', range(max(20, base_cfg.min_score - 15), base_cfg.min_score + 20, 3)),
        ('min_strat_score', [10, 13, 15, 18, 20, 22, 25]),
        ('adx_threshold', [base_cfg.adx_threshold - 5, base_cfg.adx_threshold - 2,
                           base_cfg.adx_threshold, base_cfg.adx_threshold + 2,
                           base_cfg.adx_threshold + 5]),
        ('sl_atr', [base_cfg.sl_atr - 0.5, base_cfg.sl_atr - 0.2, base_cfg.sl_atr,
                    base_cfg.sl_atr + 0.2, base_cfg.sl_atr + 0.5]),
        ('risk_per_trade', [0.3, 0.5, 0.8, 1.0, 1.5, 2.0]),
        ('partial_close_pct', [0.3, 0.4, 0.5, 0.6]),
        ('tp1_atr', [0.5, 0.8, 1.0, 1.3, 1.5]),
        ('cooldown_bars', [1, 2, 3, 4, 5]),
        ('cooldown_losses', [2, 3, 4, 5]),
        ('dyn_max_loss_atr', [1.0, 1.2, 1.5, 1.8, 2.0]),
        ('dyn_stale_bars', [12, 18, 24, 30]),
        ('rsi_oversold', [20, 25, 30, 35]),
        ('rsi_overbought', [65, 70, 75, 80]),
        ('bb_deviation', [1.5, 2.0, 2.5, 3.0]),
        ('max_concurrent', [1, 2, 3]),
        ('max_daily_trades', [3, 5, 8, 10]),
        ('london_end', [14, 15, 16, 17]),
        ('exit_hour', [18, 19, 20, 21]),
    ]

    for param_name, values in params_to_tune:
        improved = False
        for val in values:
            cfg = copy.deepcopy(best_cfg)
            if hasattr(cfg, param_name):
                setattr(cfg, param_name, val)
            # Keep tp_atr proportional
            if param_name == 'sl_atr':
                cfg.tp_atr = round(val * (best_cfg.tp_atr / best_cfg.sl_atr), 1)

            stats = run_backtest(df, cfg, silent=True)
            wr = stats['win_rate']
            ret = stats['return_pct']
            trades = stats['total_trades']

            trade_penalty = max(0, 30 - trades) * 3
            score = wr * 2 + min(ret, 200) * 0.3 - trade_penalty

            if score > best_score and trades >= 20:
                best_score = score
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats
                improved = True

        if improved:
            print(f"  Improved {param_name}: WR={best_stats['win_rate']:.1f}%, "
                  f"Ret={best_stats['return_pct']:.1f}%, Trades={best_stats['total_trades']}")

    return best_cfg, best_stats


def boost_returns(df, base_cfg, base_stats):
    """Phase 3: If WR target met but return is low, boost risk/trade."""
    print("\n" + "=" * 60)
    print("  PHASE 3: RETURN BOOSTING")
    print("=" * 60)

    best_cfg = copy.deepcopy(base_cfg)
    best_stats = base_stats

    if base_stats['win_rate'] >= TARGET_WR and base_stats['return_pct'] < TARGET_RETURN:
        for risk in [0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]:
            cfg = copy.deepcopy(base_cfg)
            cfg.risk_per_trade = risk

            stats = run_backtest(df, cfg, silent=True)
            wr = stats['win_rate']
            ret = stats['return_pct']
            dd = stats['max_drawdown_pct']

            print(f"  Risk={risk}%: WR={wr:.1f}%, Return={ret:.1f}%, DD={dd:.1f}%")

            if wr >= TARGET_WR and ret >= TARGET_RETURN and dd < 50:
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats
                break

            # Take best return that maintains WR
            if wr >= TARGET_WR and ret > best_stats.get('return_pct', 0) and dd < 60:
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats

    return best_cfg, best_stats


def main():
    data_path = Path(__file__).parent.parent / "Data" / "XAUUSD_H1.csv"
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} bars from {data_path}\n")

    # Phase 1: Grid search
    grid_results = grid_search(df)

    # Pick best result with at least 30 trades
    viable = [r for r in grid_results if r['trades'] >= 30]
    if not viable:
        viable = [r for r in grid_results if r['trades'] >= 10]
    if not viable:
        viable = grid_results[:5]

    best_grid = viable[0]
    print(f"\nBest grid result: WR={best_grid['wr']:.1f}%, Ret={best_grid['ret']:.1f}%, "
          f"Trades={best_grid['trades']}, PF={best_grid['pf']:.2f}")

    # Phase 2: Fine-tune
    tuned_cfg, tuned_stats = fine_tune(df, best_grid['cfg'], best_grid['stats'])

    print(f"\nAfter fine-tuning: WR={tuned_stats['win_rate']:.1f}%, "
          f"Ret={tuned_stats['return_pct']:.1f}%, Trades={tuned_stats['total_trades']}")

    # Phase 3: Boost returns if needed
    final_cfg, final_stats = boost_returns(df, tuned_cfg, tuned_stats)

    # Final report
    print("\n" + "=" * 60)
    print("  FINAL OPTIMIZED RESULTS")
    print("=" * 60)
    print_stats(final_stats)

    issues = diagnose(final_stats)
    if issues:
        print("\nRemaining issues:")
        for iss in issues:
            print(f"  [!] {iss}")

    wr = final_stats['win_rate']
    ret = final_stats['return_pct']
    if wr >= TARGET_WR and ret >= TARGET_RETURN:
        print(f"\n*** TARGETS MET! WR={wr:.1f}% >= {TARGET_WR}%, Return={ret:.1f}% >= {TARGET_RETURN}% ***")
    else:
        print(f"\n*** Targets NOT fully met. WR={wr:.1f}% (target {TARGET_WR}%), Return={ret:.1f}% (target {TARGET_RETURN}%) ***")

    # Save optimal config
    print("\nOptimal Parameters:")
    key_params = ['risk_per_trade', 'sl_atr', 'tp_atr', 'trail_activation', 'trail_distance',
                  'min_score', 'min_strategies', 'min_strat_score', 'adx_threshold',
                  'rsi_oversold', 'rsi_overbought', 'dyn_max_loss_atr', 'dyn_stale_bars',
                  'partial_close_pct', 'tp1_atr', 'max_concurrent', 'max_daily_trades',
                  'cooldown_bars', 'cooldown_losses', 'london_end', 'exit_hour',
                  'enable_trend', 'enable_momentum', 'enable_session',
                  'enable_mean_revert', 'enable_smc', 'min_risk_reward',
                  'bb_deviation']
    for p in key_params:
        print(f"  {p} = {getattr(final_cfg, p)}")

    config_out = Path(__file__).parent.parent / "Data" / "optimal_config.json"
    cfg_dict = {k: v for k, v in final_cfg.__dict__.items()}
    with open(config_out, 'w') as f:
        json.dump(cfg_dict, f, indent=2)
    print(f"\nConfig saved to: {config_out}")

    return final_stats, final_cfg


if __name__ == "__main__":
    main()
