#!/usr/bin/env python3
"""
CLAWBOT Maximum Profit Optimizer
==================================
Target: 500% return with acceptable drawdown

Strategy: Maximize returns by optimizing:
1. Risk per trade (position sizing)
2. TP/SL ratio (reward vs risk)
3. Entry selectivity (min_score, min_strategies)
4. Partial close optimization
5. Feature toggles (brain, MTF, dynamic closure)
"""

import sys, json, copy, time
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_engine import Config, ClawbotBacktester, print_stats, diagnose

TARGET_RETURN = 500.0


def run_bt(df, cfg):
    bt = ClawbotBacktester(cfg)
    return bt.run(df, silent=True)


def score_result(stats):
    """Score prioritizing maximum return with acceptable risk."""
    ret = stats['return_pct']
    pf = stats['profit_factor']
    wr = stats['win_rate']
    trades = stats['total_trades']
    dd = stats['max_drawdown_pct']

    if trades < 20:
        return -1000

    # Return is king
    if ret >= 500:
        ret_score = 500 + min(ret - 500, 2000) * 0.1
    elif ret >= 100:
        ret_score = ret * 1.0
    elif ret > 0:
        ret_score = ret * 0.5
    else:
        ret_score = ret * 2  # Heavy penalty for losses

    # PF bonus (must be > 1.0)
    if pf >= 1.0:
        pf_score = min(pf, 5) * 20
    else:
        pf_score = (pf - 1.0) * 100  # Penalty

    # WR bonus
    wr_score = wr * 0.5

    # DD penalty (want < 40%, tolerate up to 60%)
    if dd > 60:
        dd_pen = (dd - 60) * 5 + 40
    elif dd > 40:
        dd_pen = (dd - 40) * 2
    else:
        dd_pen = 0

    return ret_score + pf_score + wr_score - dd_pen


def main():
    data_path = Path(__file__).parent.parent / "Data" / "XAUUSD_H1.csv"
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} bars\n")

    # ================================================================
    # PHASE 1: Grid search for best TP/SL/Risk combination
    # ================================================================
    print("=" * 60)
    print("  PHASE 1: PROFIT-MAXIMIZING PARAMETER SEARCH")
    print("=" * 60)

    results = []
    count = 0
    t0 = time.time()

    for tp_atr in [2.0, 3.0, 4.0, 5.0, 6.0]:
        for sl_atr in [1.0, 1.5, 2.0, 2.5, 3.0]:
            for risk in [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]:
                for min_score in [30, 45, 60, 80]:
                    for min_strat in [1, 2]:
                        cfg = Config()
                        cfg.tp_atr = tp_atr
                        cfg.sl_atr = sl_atr
                        cfg.risk_per_trade = risk
                        cfg.min_score = min_score
                        cfg.min_strategies = min_strat
                        cfg.min_risk_reward = 0.5
                        cfg.trail_activation = max(sl_atr * 0.6, 0.8)
                        cfg.trail_distance = max(sl_atr * 0.4, 0.5)
                        cfg.tp1_atr = tp_atr * 0.15
                        cfg.partial_close_pct = 0.5

                        stats = run_bt(df, cfg)
                        sc = score_result(stats)
                        count += 1

                        results.append({
                            'ret': stats['return_pct'], 'wr': stats['win_rate'],
                            'pf': stats['profit_factor'], 'trades': stats['total_trades'],
                            'dd': stats['max_drawdown_pct'], 'score': sc,
                            'cfg': copy.deepcopy(cfg), 'stats': stats,
                        })

                        if count % 50 == 0:
                            best = max(results, key=lambda x: x['score'])
                            elapsed = time.time() - t0
                            print(f"  [{count}] ({elapsed:.0f}s) Best: Ret={best['ret']:.0f}%, "
                                  f"WR={best['wr']:.1f}%, PF={best['pf']:.2f}, "
                                  f"Trd={best['trades']}, DD={best['dd']:.0f}%")

    elapsed = time.time() - t0
    results.sort(key=lambda x: x['score'], reverse=True)
    print(f"\nPhase 1: {count} configs in {elapsed:.0f}s")

    print(f"\nTop 15 by profit score:")
    print(f"  {'Ret':>8} {'WR':>6} {'PF':>5} {'Trd':>4} {'DD':>5} | TP   SL  Risk  MS MST")
    for r in results[:15]:
        c = r['cfg']
        print(f"  {r['ret']:7.0f}% {r['wr']:5.1f}% {r['pf']:5.2f} {r['trades']:4d} {r['dd']:4.0f}% | "
              f"{c.tp_atr:.1f} {c.sl_atr:.1f} {c.risk_per_trade:5.1f} {c.min_score:3.0f} {c.min_strategies}")

    best_cfg = results[0]['cfg']
    best_stats = results[0]['stats']
    best_score = results[0]['score']

    # ================================================================
    # PHASE 2: Fine-tune around best result
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 2: FINE-TUNING")
    print("=" * 60)
    print(f"Starting: Ret={best_stats['return_pct']:.0f}%, WR={best_stats['win_rate']:.1f}%")

    tune_params = [
        ('tp_atr', lambda c: np.arange(max(1.0, c.tp_atr - 1.0), c.tp_atr + 1.5, 0.2).tolist()),
        ('sl_atr', lambda c: np.arange(max(0.5, c.sl_atr - 0.5), c.sl_atr + 0.8, 0.1).tolist()),
        ('risk_per_trade', lambda c: np.arange(max(0.5, c.risk_per_trade - 2), c.risk_per_trade + 3, 0.5).tolist()),
        ('min_score', lambda c: list(range(max(15, c.min_score - 15), c.min_score + 20, 3))),
        ('min_strat_score', lambda c: [5, 8, 10, 12, 15, 18, 20, 25, 30]),
        ('adx_threshold', lambda c: [15, 18, 20, 22, 25, 28, 30, 35]),
        ('min_strategies', lambda c: [1, 2, 3]),
        ('partial_close_pct', lambda c: [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]),
        ('tp1_atr', lambda c: np.arange(0.1, 1.5, 0.1).tolist()),
        ('trail_activation', lambda c: np.arange(0.3, 2.5, 0.2).tolist()),
        ('trail_distance', lambda c: np.arange(0.2, 2.0, 0.15).tolist()),
        ('dyn_max_loss_atr', lambda c: np.arange(0.5, 3.5, 0.3).tolist()),
        ('dyn_stale_bars', lambda c: [8, 12, 16, 20, 24, 30, 40]),
        ('dyn_adverse_mom', lambda c: [0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0]),
        ('cooldown_bars', lambda c: [0, 1, 2, 3, 5, 8]),
        ('cooldown_losses', lambda c: [1, 2, 3, 4, 5]),
        ('max_concurrent', lambda c: [1, 2, 3, 4, 5]),
        ('max_daily_trades', lambda c: [1, 2, 3, 5, 8, 10, 15]),
        ('rsi_oversold', lambda c: [20, 25, 30, 35, 40]),
        ('rsi_overbought', lambda c: [60, 65, 70, 75, 80]),
        ('london_end', lambda c: [14, 15, 16, 17, 18]),
        ('exit_hour', lambda c: [17, 18, 19, 20, 21]),
        ('min_risk_reward', lambda c: [0.3, 0.5, 0.8, 1.0, 1.5, 2.0]),
        ('dyn_stale_range', lambda c: [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]),
        ('avg_spread', lambda c: [10, 15, 20, 25, 30]),
    ]

    for round_num in range(4):
        round_improved = 0
        for pname, vfn in tune_params:
            vals = vfn(best_cfg)
            for val in vals:
                cfg = copy.deepcopy(best_cfg)
                if hasattr(cfg, pname):
                    setattr(cfg, pname, val)
                if pname == 'sl_atr':
                    cfg.trail_activation = max(val * 0.6, 0.8)
                    cfg.trail_distance = max(val * 0.4, 0.5)
                if pname == 'tp_atr':
                    cfg.tp1_atr = val * 0.15

                stats = run_bt(df, cfg)
                sc = score_result(stats)
                if sc > best_score:
                    best_score = sc
                    best_cfg = copy.deepcopy(cfg)
                    best_stats = stats
                    round_improved += 1

        ret = best_stats['return_pct']
        wr = best_stats['win_rate']
        pf = best_stats['profit_factor']
        dd = best_stats['max_drawdown_pct']
        trd = best_stats['total_trades']
        print(f"  Round {round_num+1}: {round_improved} improvements → "
              f"Ret={ret:.0f}%, WR={wr:.1f}%, PF={pf:.2f}, Trd={trd}, DD={dd:.0f}%")
        if round_improved == 0:
            break

    # ================================================================
    # PHASE 3: Feature toggles
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 3: FEATURE OPTIMIZATION")
    print("=" * 60)

    for flag in ['enable_trend', 'enable_momentum', 'enable_session',
                  'enable_mean_revert', 'enable_smc', 'enable_brain', 'enable_mtf',
                  'enable_dyn_closure', 'enable_dynamic_tp', 'enable_partial_close']:
        for val in [True, False]:
            cfg = copy.deepcopy(best_cfg)
            setattr(cfg, flag, val)
            stats = run_bt(df, cfg)
            sc = score_result(stats)
            if sc > best_score and stats['total_trades'] >= 20:
                old_ret = best_stats['return_pct']
                best_score = sc
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats
                print(f"  {flag}={val}: Ret {old_ret:.0f}% → {stats['return_pct']:.0f}% [IMPROVED]")

    # ================================================================
    # PHASE 4: Aggressive risk scaling
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 4: RISK SCALING FOR MAX RETURN")
    print("=" * 60)

    for risk in np.arange(1.0, 25.0, 0.5):
        cfg = copy.deepcopy(best_cfg)
        cfg.risk_per_trade = risk
        stats = run_bt(df, cfg)
        ret = stats['return_pct']
        dd = stats['max_drawdown_pct']
        pf = stats['profit_factor']
        wr = stats['win_rate']
        trd = stats['total_trades']

        if ret >= 500 and dd < 60 and trd >= 20:
            print(f"  Risk={risk:5.1f}%: Ret={ret:8.0f}%, WR={wr:.1f}%, PF={pf:.2f}, "
                  f"DD={dd:.0f}%, Trd={trd} >>> 500% TARGET MET!")
            best_cfg = copy.deepcopy(cfg)
            best_stats = stats
            break
        elif ret > best_stats.get('return_pct', 0) and dd < 65:
            sc = score_result(stats)
            if sc > best_score:
                best_score = sc
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats

        if trd >= 20:
            print(f"  Risk={risk:5.1f}%: Ret={ret:8.0f}%, WR={wr:.1f}%, PF={pf:.2f}, DD={dd:.0f}%, Trd={trd}")

    # ================================================================
    # FINAL REPORT
    # ================================================================
    print("\n" + "=" * 60)
    print("  FINAL OPTIMIZED RESULTS")
    print("=" * 60)
    print_stats(best_stats)

    issues = diagnose(best_stats)
    if issues:
        print("\nDiagnostics:")
        for iss in issues:
            print(f"  [!] {iss}")

    ret = best_stats['return_pct']
    if ret >= TARGET_RETURN:
        print(f"\n*** TARGET MET! Return={ret:.0f}% >= {TARGET_RETURN:.0f}% ***")
    else:
        print(f"\n*** Best Return: {ret:.0f}% (target {TARGET_RETURN:.0f}%) ***")

    # Save config
    print("\nOptimal Parameters:")
    key_params = [
        'risk_per_trade', 'sl_atr', 'tp_atr', 'trail_activation', 'trail_distance',
        'min_score', 'min_strategies', 'min_strat_score', 'adx_threshold',
        'rsi_oversold', 'rsi_overbought', 'dyn_max_loss_atr', 'dyn_stale_bars',
        'dyn_adverse_mom', 'partial_close_pct', 'tp1_atr', 'max_concurrent',
        'max_daily_trades', 'cooldown_bars', 'cooldown_losses',
        'london_end', 'exit_hour', 'min_risk_reward',
        'enable_trend', 'enable_momentum', 'enable_session',
        'enable_mean_revert', 'enable_smc', 'enable_brain', 'enable_mtf',
        'enable_dyn_closure', 'enable_partial_close', 'dyn_stale_range', 'avg_spread',
    ]
    for p in key_params:
        if hasattr(best_cfg, p):
            print(f"  {p} = {getattr(best_cfg, p)}")

    out = Path(__file__).parent.parent / "Data" / "optimal_config.json"
    cfg_dict = {}
    for k, v in best_cfg.__dict__.items():
        if isinstance(v, (int, float, bool, str)):
            cfg_dict[k] = v
    with open(out, 'w') as f:
        json.dump(cfg_dict, f, indent=2)
    print(f"\nSaved to: {out}")

    return best_stats, best_cfg


if __name__ == "__main__":
    main()
